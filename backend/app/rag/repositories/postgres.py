"""All SQL, ownership checks, job leases and publication transactions live here."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import re
from sqlalchemy import select, update, delete, func, or_, and_, cast, ARRAY, Text, exists
from app.auth.repositories.tables import learner
from app.rag.repositories.tables import documents, associations, versions, generations, chunks, jobs, chunk_concepts, document_concepts
from app.rag.errors import not_found, conflict
from app.core.exceptions import AppError


def now():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class RAGRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def _document(self, session, owner, document_id, *, lock=False, deleted=False):
        query = select(documents).where(documents.c.learner_id == owner, documents.c.id == document_id)
        if not deleted:
            query = query.where(documents.c.deleted_at.is_(None))
        if lock:
            query = query.with_for_update()
        row = session.execute(query).mappings().first()
        if row is None:
            raise not_found()
        return dict(row)

    def _job(self, owner, document_id, generation_id, operation, key, request_hash, revision):
        return dict(id=new_id(), learner_id=owner, document_id=document_id, generation_id=generation_id,
                    operation=operation, state='QUEUED', idempotency_key=key, request_hash=request_hash,
                    expected_revision=revision, attempts=0, stage='queued', next_attempt_at=now(),
                    created_at=now(), updated_at=now())

    def _associations(self, session, owner, document_id, context_ids):
        session.execute(delete(associations).where(associations.c.learner_id == owner, associations.c.document_id == document_id))
        session.execute(associations.insert(), [dict(learner_id=owner, document_id=document_id, context_id=c) for c in context_ids])

    def accept(self, owner, *, title, filename, context_ids, blob, key, request_hash, config, quota,
               document_id=None, expected_revision=None):
        with self.sessions.begin() as session:
            # Serializes quota, exact duplicates and idempotency for this owner only.
            session.execute(select(learner.c.id).where(learner.c.id == owner).with_for_update()).scalar_one()
            existing = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.idempotency_key == key)).mappings().first()
            if existing:
                if existing['request_hash'] != request_hash:
                    raise AppError('RAG_IDEMPOTENCY_CONFLICT', 'This upload key was already used for different material.', 409)
                return dict(document_id=existing['document_id'], generation_id=existing['generation_id'], job_id=existing['id'], duplicate=True)
            if document_id is None:
                latest = versions.alias('latest_upload')
                latest_id = select(latest.c.id).where(latest.c.document_id == documents.c.id).order_by(
                    latest.c.created_at.desc(), latest.c.id.desc()).limit(1).scalar_subquery()
                duplicate = session.execute(select(versions.c.document_id).join(documents, versions.c.document_id == documents.c.id).where(
                    versions.c.learner_id == owner, versions.c.file_hash == blob['file_hash'],
                    versions.c.id == latest_id, documents.c.deleted_at.is_(None), documents.c.context_ids == context_ids).limit(1)).scalar_one_or_none()
                if duplicate:
                    old = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.document_id == duplicate,
                        jobs.c.operation == 'INGEST').order_by(jobs.c.created_at.desc()).limit(1)).mappings().first()
                    return dict(document_id=duplicate, generation_id=old['generation_id'], job_id=old['id'], duplicate=True)
            used = session.execute(select(func.coalesce(func.sum(versions.c.size_bytes), 0)).join(documents,
                versions.c.document_id == documents.c.id).where(versions.c.learner_id == owner, documents.c.purged_at.is_(None))).scalar_one()
            if used + blob['size_bytes'] > quota:
                raise AppError('RAG_QUOTA_EXCEEDED', 'Your material storage quota is full.', 413)
            pending = session.execute(select(jobs.c.id).where(jobs.c.learner_id == owner, jobs.c.operation == 'INGEST',
                jobs.c.state.in_(['QUEUED', 'RUNNING', 'RETRY_WAIT']))).first()
            if pending:
                raise AppError('RAG_INGESTION_BUSY', 'Wait for your current material to finish processing before adding another.', 409)
            if document_id:
                doc = self._document(session, owner, document_id, lock=True)
                if doc['revision'] != expected_revision or doc['archived']:
                    raise conflict()
                revision = doc['revision'] + 1
                context_ids = doc['context_ids']
                session.execute(update(documents).where(documents.c.id == document_id).values(revision=revision, updated_at=now()))
            else:
                document_id, revision = new_id(), 1
                session.execute(documents.insert().values(id=document_id, learner_id=owner, title=title, filename=filename,
                    context_ids=context_ids, archived=False, revision=revision, created_at=now(), updated_at=now()))
                self._associations(session, owner, document_id, context_ids)
            version_id, generation_id = new_id(), new_id()
            session.execute(versions.insert().values(id=version_id, learner_id=owner, document_id=document_id,
                filename=filename, created_at=now(), **blob))
            session.execute(generations.insert().values(id=generation_id, learner_id=owner, document_id=document_id,
                version_id=version_id, state='PENDING', config=config, warnings=[], chunk_count=0, created_at=now()))
            job = self._job(owner, document_id, generation_id, 'INGEST', key, request_hash, revision)
            session.execute(jobs.insert().values(**job))
            return dict(document_id=document_id, generation_id=generation_id, job_id=job['id'], duplicate=False)

    def list_documents(self, owner, offset=0, limit=25, archived=None, context_id=None):
        with self.sessions() as session:
            condition = [documents.c.learner_id == owner, documents.c.deleted_at.is_(None)]
            if archived is not None:
                condition.append(documents.c.archived == archived)
            if context_id is not None:
                condition.append(documents.c.context_ids.has_any(cast([context_id], ARRAY(Text))))
            count = session.execute(select(func.count()).select_from(documents).where(*condition)).scalar_one()
            rows = [dict(row) for row in session.execute(select(documents).where(*condition)
                .order_by(documents.c.created_at.desc(), documents.c.id).offset(offset).limit(limit)).mappings()]
            return dict(items=self._list_details(session, owner, rows), total=count, offset=offset, limit=limit)

    def _list_details(self, session, owner, rows):
        """Fetch bounded Library summaries in batches, independent of page size."""
        if not rows:
            return []
        by_id = {row['id']: dict(row, versions=[], version_count=0, generations=[], jobs=[]) for row in rows}
        ids = list(by_id)

        def recent(table, count, active_ids=()):
            ranked = select(table, func.row_number().over(partition_by=table.c.document_id,
                order_by=(table.c.created_at.desc(), table.c.id.desc())).label('_position')).where(
                    table.c.learner_id == owner, table.c.document_id.in_(ids)).subquery()
            condition = ranked.c._position <= count
            if active_ids:
                condition = or_(condition, ranked.c.id.in_(active_ids))
            query = select(ranked).where(condition).order_by(ranked.c.document_id, ranked.c._position)
            result = []
            for row in session.execute(query).mappings():
                item = dict(row)
                item.pop('_position')
                result.append(item)
            return result

        latest_versions = recent(versions, 1)
        self._attach_published_versions(session, owner, latest_versions)
        for version in latest_versions:
            # Match the public version-page contract; never leak storage keys.
            by_id[version['document_id']]['versions'].append({key: version[key] for key in
                ('id', 'filename', 'media_type', 'size_bytes', 'created_at', 'generation_id', 'warnings')})
        for document_id, count in session.execute(select(versions.c.document_id, func.count()).where(
            versions.c.learner_id == owner, versions.c.document_id.in_(ids)).group_by(versions.c.document_id)):
            by_id[document_id]['version_count'] = count
        active = [row['active_generation_id'] for row in rows if row['active_generation_id']]
        for generation in recent(generations, 1, active):
            by_id[generation['document_id']]['generations'].append(generation)
        for job in recent(jobs, 10):
            by_id[job['document_id']]['jobs'].append(self._public_job(job))
        return [by_id[row['id']] for row in rows]

    def _version_page(self, session, owner, document_id, offset=0, limit=25):
        rows = [dict(r) for r in session.execute(select(versions.c.id, versions.c.filename, versions.c.media_type,
            versions.c.size_bytes, versions.c.created_at).where(versions.c.learner_id == owner,
                versions.c.document_id == document_id).order_by(versions.c.created_at.desc(), versions.c.id.desc())
            .offset(offset).limit(limit)).mappings()]
        self._attach_published_versions(session, owner, rows)
        return rows

    def _attach_published_versions(self, session, owner, rows):
        if not rows:
            return
        published = session.execute(select(generations.c.version_id, generations.c.id, generations.c.warnings).where(
            generations.c.learner_id == owner, generations.c.version_id.in_([r['id'] for r in rows]),
            generations.c.indexed_at.is_not(None)).distinct(generations.c.version_id)
            .order_by(generations.c.version_id, generations.c.created_at.desc())).mappings()
        latest = {}
        for row in published:
            latest.setdefault(row['version_id'], row)
        for row in rows:
            generation = latest.get(row['id'])
            row['generation_id'] = generation['id'] if generation else None
            row['warnings'] = generation['warnings'] if generation else []

    def list_versions(self, owner, document_id, offset=0, limit=25):
        with self.sessions() as session:
            self._document(session, owner, document_id)
            count = session.execute(select(func.count()).select_from(versions).where(
                versions.c.learner_id == owner, versions.c.document_id == document_id)).scalar_one()
            return dict(items=self._version_page(session, owner, document_id, offset, limit), total=count, offset=offset, limit=limit)

    def _detail(self, session, owner, document_id, history_limit=25):
        doc = self._document(session, owner, document_id)
        doc['versions'] = self._version_page(session, owner, document_id, limit=history_limit)
        doc['version_count'] = session.execute(select(func.count()).select_from(versions).where(
            versions.c.learner_id == owner, versions.c.document_id == document_id)).scalar_one()
        doc['generations'] = [dict(r) for r in session.execute(select(generations).where(generations.c.learner_id == owner,
            generations.c.document_id == document_id).order_by(generations.c.created_at.desc()).limit(history_limit)).mappings()]
        if doc['active_generation_id'] and not any(g['id'] == doc['active_generation_id'] for g in doc['generations']):
            doc['generations'].append(dict(session.execute(select(generations).where(generations.c.learner_id == owner,
                generations.c.id == doc['active_generation_id'])).mappings().one()))
        doc['jobs'] = [self._public_job(r) for r in session.execute(select(jobs).where(jobs.c.learner_id == owner,
            jobs.c.document_id == document_id).order_by(jobs.c.created_at.desc()).limit(10)).mappings()]
        return doc

    def get_document(self, owner, document_id):
        with self.sessions() as session:
            return self._detail(session, owner, document_id)

    def document_metadata(self, owner, document_ids):
        with self.sessions() as session:
            rows = [dict(row) for row in session.execute(select(documents).where(documents.c.learner_id == owner,
                documents.c.id.in_(document_ids), documents.c.deleted_at.is_(None))).mappings()]
            if {row['id'] for row in rows} != set(document_ids):
                raise not_found()
            return rows

    def update_document(self, owner, document_id, request):
        with self.sessions.begin() as session:
            doc = self._document(session, owner, document_id, lock=True)
            if doc['revision'] != request.expected_revision:
                raise conflict()
            values = dict(revision=doc['revision'] + 1, updated_at=now())
            for field in ('title', 'archived', 'context_ids'):
                value = getattr(request, field)
                if value is not None:
                    values[field] = value
            session.execute(update(documents).where(documents.c.id == document_id).values(**values))
            if request.context_ids is not None:
                self._associations(session, owner, document_id, request.context_ids)
            # The authoritative scope changes immediately; refresh is performed by
            # reconciliation. Search selects explicit eligible generation IDs.
        return self.get_document(owner, document_id)

    def request_delete(self, owner, document_id):
        with self.sessions.begin() as session:
            doc = self._document(session, owner, document_id, lock=True, deleted=True)
            if doc['deleted_at'] is None:
                session.execute(update(documents).where(documents.c.id == document_id).values(deleted_at=now(),
                    active_generation_id=None, revision=doc['revision'] + 1, updated_at=now()))
                session.execute(update(jobs).where(jobs.c.learner_id == owner, jobs.c.document_id == document_id,
                    jobs.c.operation == 'INGEST', jobs.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT'])).values(state='CANCELLED', lease_token=None))
                session.execute(jobs.insert().values(**self._job(owner, document_id, None, 'DELETE', 'delete:' + document_id, '', doc['revision'] + 1)))
            return dict(document_id=document_id, state='purged' if doc['purged_at'] else 'delete_requested')

    def reindex(self, owner, document_id, request, config):
        with self.sessions.begin() as session:
            session.execute(select(learner.c.id).where(learner.c.id == owner).with_for_update()).scalar_one()
            doc = self._document(session, owner, document_id, lock=True)
            existing = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.idempotency_key == request.idempotency_key)).mappings().first()
            request_hash = f'reindex:{document_id}:{request.expected_revision}'
            if existing:
                if existing['request_hash'] != request_hash:
                    raise conflict()
                return self._public_job(existing)
            if doc['revision'] != request.expected_revision or doc['archived']:
                raise conflict()
            if session.execute(select(jobs.c.id).where(jobs.c.learner_id == owner, jobs.c.operation == 'INGEST',
                jobs.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT']))).first():
                raise AppError('RAG_INGESTION_BUSY', 'Material is already being processed.', 409)
            version_id = session.execute(select(versions.c.id).where(versions.c.document_id == document_id,
                versions.c.learner_id == owner).order_by(versions.c.created_at.desc()).limit(1)).scalar_one()
            generation_id = new_id()
            session.execute(generations.insert().values(id=generation_id, learner_id=owner, document_id=document_id,
                version_id=version_id, state='PENDING', config=config, warnings=[], chunk_count=0, created_at=now()))
            revision = doc['revision'] + 1
            session.execute(update(documents).where(documents.c.id == document_id).values(revision=revision, updated_at=now()))
            job = self._job(owner, document_id, generation_id, 'INGEST', request.idempotency_key, request_hash, revision)
            session.execute(jobs.insert().values(**job))
            return self._public_job(job)

    def queue_rebuild(self, owner, run_id, config, dry_run=True):
        with self.sessions.begin() as session:
            session.execute(select(learner.c.id).where(learner.c.id == owner).with_for_update()).scalar_one()
            rows = [dict(r) for r in session.execute(select(documents).where(documents.c.learner_id == owner,
                documents.c.deleted_at.is_(None), documents.c.archived.is_(False), documents.c.active_generation_id.is_not(None))
                .order_by(documents.c.id).with_for_update()).mappings()]
            if dry_run:
                return dict(dry_run=True, ready_materials=len(rows), run_id=run_id)
            if session.execute(select(jobs.c.id).where(jobs.c.learner_id == owner, jobs.c.operation == 'INGEST',
                jobs.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT']))).first():
                raise AppError('RAG_INGESTION_BUSY', 'Wait for existing ingestion jobs before rebuilding.', 409)
            queued = []
            for doc in rows:
                key = f'rebuild:{run_id}:{doc["id"]}'
                old = session.execute(select(jobs.c.id).where(jobs.c.learner_id == owner, jobs.c.idempotency_key == key)).scalar_one_or_none()
                if old:
                    queued.append(old)
                    continue
                version_id = session.execute(select(generations.c.version_id).where(generations.c.id == doc['active_generation_id'])).scalar_one()
                generation_id = new_id()
                session.execute(generations.insert().values(id=generation_id, learner_id=owner, document_id=doc['id'],
                    version_id=version_id, state='PENDING', config=config, warnings=[], chunk_count=0, created_at=now()))
                revision = doc['revision'] + 1
                session.execute(update(documents).where(documents.c.id == doc['id']).values(revision=revision, updated_at=now()))
                job = self._job(owner, doc['id'], generation_id, 'INGEST', key, 'rebuild:' + run_id, revision)
                session.execute(jobs.insert().values(**job)); queued.append(job['id'])
            return dict(dry_run=False, run_id=run_id, job_ids=queued)

    @staticmethod
    def _public_job(row):
        return {k: row.get(k) for k in ('id','document_id','generation_id','operation','state','stage','attempts','error','created_at','updated_at')}

    def get_job(self, owner, job_id):
        with self.sessions() as session:
            row = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.id == job_id)).mappings().first()
            if row is None:
                raise not_found()
            return self._public_job(row)

    def retry(self, owner, job_id):
        with self.sessions.begin() as session:
            row = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.id == job_id)).mappings().first()
            if not row:
                raise not_found()
            doc = self._document(session, owner, row['document_id'], lock=True)
            row = session.execute(select(jobs).where(jobs.c.learner_id == owner, jobs.c.id == job_id).with_for_update()).mappings().one()
            if row['state'] in ('QUEUED', 'RUNNING', 'RETRY_WAIT'):
                return self._public_job(row)
            if row['state'] != 'FAILED' or doc['archived'] or doc['revision'] != row['expected_revision']:
                raise conflict()
            session.execute(update(jobs).where(jobs.c.id == job_id).values(state='QUEUED', attempts=0, error=None,
                lease_token=None, lease_until=None, next_attempt_at=now(), updated_at=now()))
        return self.get_job(owner, job_id)

    def claim(self, lease_seconds):
        with self.sessions.begin() as session:
            row = session.execute(select(jobs).where(or_(and_(jobs.c.state.in_(['QUEUED','RETRY_WAIT']),
                jobs.c.next_attempt_at <= now()), and_(jobs.c.state == 'RUNNING', jobs.c.lease_until < now())))
                .order_by(jobs.c.created_at).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if row is None:
                return None
            claimed = dict(row, lease_token=new_id(), state='RUNNING', attempts=row['attempts'] + 1,
                           lease_until=now() + timedelta(seconds=lease_seconds), updated_at=now())
            session.execute(update(jobs).where(jobs.c.id == row['id']).values(**{k: claimed[k] for k in
                ('lease_token','state','attempts','lease_until','updated_at')}))
            return claimed

    def _lease(self, session, job):
        row = session.execute(select(jobs).where(jobs.c.id == job['id'], jobs.c.learner_id == job['learner_id']).with_for_update()).mappings().one()
        if row['state'] != 'RUNNING' or row['lease_token'] != job['lease_token'] or row['lease_until'] < now():
            raise AppError('RAG_LEASE_LOST', 'Ingestion lease was superseded.', 409)

    def stage(self, job, stage, lease_seconds):
        with self.sessions.begin() as session:
            self._lease(session, job)
            session.execute(update(jobs).where(jobs.c.id == job['id']).values(stage=stage, updated_at=now(),
                lease_until=now() + timedelta(seconds=lease_seconds)))

    def work_source(self, job):
        with self.sessions() as session:
            doc = self._document(session, job['learner_id'], job['document_id'])
            generation = dict(session.execute(select(generations).where(generations.c.id == job['generation_id'],
                generations.c.learner_id == job['learner_id'])).mappings().one())
            version = dict(session.execute(select(versions).where(versions.c.id == generation['version_id'],
                versions.c.learner_id == job['learner_id'])).mappings().one())
            return doc, generation, version

    def save_chunks(self, job, items, warnings):
        with self.sessions.begin() as session:
            self._lease(session, job)
            session.execute(delete(chunks).where(chunks.c.generation_id == job['generation_id'], chunks.c.learner_id == job['learner_id']))
            session.execute(chunks.insert(), items)
            links = [dict(chunk_id=c['id'], concept_id=concept) for c in items for concept in c['concept_ids']]
            if links:
                session.execute(chunk_concepts.insert(), links)
            session.execute(update(generations).where(generations.c.id == job['generation_id']).values(
                state='PROCESSING', chunk_count=len(items), warnings=warnings))

    def resume_chunks(self, job, expected_count):
        if expected_count <= 0:
            return []
        with self.sessions() as session:
            items = [dict(row) for row in session.execute(select(chunks).where(
                chunks.c.learner_id == job['learner_id'], chunks.c.generation_id == job['generation_id'])
                .order_by(chunks.c.ordinal)).mappings()]
            return items if len(items) == expected_count and all(c['ordinal'] == i for i, c in enumerate(items)) else []

    def publish(self, job):
        with self.sessions.begin() as session:
            # Consistent lock order: document before job, matching delete/retry.
            doc = self._document(session, job['learner_id'], job['document_id'], lock=True, deleted=True)
            self._lease(session, job)
            if doc['deleted_at'] or doc['archived'] or doc['revision'] != job['expected_revision']:
                session.execute(update(jobs).where(jobs.c.id == job['id']).values(state='CANCELLED', lease_token=None))
                session.execute(update(generations).where(generations.c.id == job['generation_id']).values(state='SUPERSEDED'))
                return False
            old = doc['active_generation_id']
            if old:
                session.execute(update(generations).where(generations.c.id == old).values(state='SUPERSEDED'))
            session.execute(update(generations).where(generations.c.id == job['generation_id']).values(state='READY', indexed_at=now()))
            session.execute(update(documents).where(documents.c.id == doc['id']).values(active_generation_id=job['generation_id'],
                revision=doc['revision'] + 1, updated_at=now()))
            session.execute(update(jobs).where(jobs.c.id == job['id']).values(state='SUCCEEDED', stage='ready', lease_token=None, updated_at=now()))
            return True

    def fail(self, job, error, retryable):
        with self.sessions.begin() as session:
            try:
                self._lease(session, job)
            except AppError:
                return
            retry = retryable and job['attempts'] < 3
            session.execute(update(jobs).where(jobs.c.id == job['id']).values(state='RETRY_WAIT' if retry else 'FAILED',
                error=error, lease_token=None, lease_until=None, next_attempt_at=now() + timedelta(seconds=10 * job['attempts']), updated_at=now()))
            if job['generation_id']:
                session.execute(update(generations).where(generations.c.id == job['generation_id']).values(state='PENDING' if retry else 'FAILED'))

    def deletion_sources(self, job):
        with self.sessions() as session:
            return list(session.execute(select(versions.c.storage_key).where(versions.c.learner_id == job['learner_id'],
                versions.c.document_id == job['document_id'])).scalars())

    def complete_delete(self, job):
        with self.sessions.begin() as session:
            self._lease(session, job)
            session.execute(delete(chunks).where(chunks.c.learner_id == job['learner_id'], chunks.c.document_id == job['document_id']))
            session.execute(delete(document_concepts).where(document_concepts.c.document_id == job['document_id']))
            session.execute(update(versions).where(versions.c.learner_id == job['learner_id'],
                versions.c.document_id == job['document_id']).values(filename='Deleted material', file_hash='purged'))
            session.execute(update(documents).where(documents.c.id == job['document_id']).values(purged_at=now(),
                title='Deleted material', filename='Deleted material', concept_ids=[]))
            session.execute(update(jobs).where(jobs.c.id == job['id']).values(state='SUCCEEDED', stage='purged', lease_token=None, updated_at=now()))

    def eligible(self, owner, context_ids, document_ids, include_archived):
        with self.sessions() as session:
            query = select(documents).where(documents.c.learner_id == owner, documents.c.deleted_at.is_(None),
                documents.c.active_generation_id.is_not(None))
            if not include_archived:
                query = query.where(documents.c.archived.is_(False))
            if document_ids is not None:
                query = query.where(documents.c.id.in_(document_ids))
            if context_ids is not None:
                query = query.where(documents.c.context_ids.has_any(cast(context_ids, ARRAY(Text))))
            return [dict(r) for r in session.execute(query).mappings()]

    def hydrate(self, owner, ids, eligible_ids):
        if not ids or not eligible_ids:
            return []
        with self.sessions() as session:
            query = select(chunks, generations.c.version_id, generations.c.warnings, documents.c.title,
                versions.c.filename, versions.c.media_type).join(generations,
                chunks.c.generation_id == generations.c.id).join(documents, chunks.c.document_id == documents.c.id).join(
                versions, generations.c.version_id == versions.c.id).where(
                chunks.c.learner_id == owner, chunks.c.id.in_(ids), generations.c.state == 'READY',
                chunks.c.generation_id.in_(eligible_ids), documents.c.active_generation_id == chunks.c.generation_id,
                documents.c.deleted_at.is_(None))
            return [dict(r) for r in session.execute(query).mappings()]

    def lexical(self, owner, generation_ids, query, limit=40):
        if not generation_ids:
            return []
        with self.sessions() as session:
            vector = func.to_tsvector('simple', chunks.c.content)
            # Natural-language questions rarely occur verbatim in a passage.
            # Bound values and the websearch parser keep identifiers safe while
            # matching any query term; dense ranking supplies semantic relevance.
            words = re.findall(r'\w+', query, flags=re.UNICODE)
            if not words:
                return []
            terms = func.websearch_to_tsquery('simple', ' OR '.join(words))
            return list(session.execute(select(chunks.c.id).where(chunks.c.learner_id == owner,
                chunks.c.generation_id.in_(generation_ids), vector.op('@@')(terms))
                .order_by(func.ts_rank_cd(vector, terms).desc(), chunks.c.id).limit(limit)).scalars())

    def source(self, owner, document_id, version_id):
        with self.sessions() as session:
            doc = self._document(session, owner, document_id)
            row = session.execute(select(versions).where(versions.c.learner_id == owner,
                versions.c.document_id == document_id, versions.c.id == version_id)).mappings().first()
            if row is None:
                raise not_found()
            return doc, dict(row)

    def source_chunks(self, owner, document_id, version_id, limit=100, offset=0, generation_id=None):
        with self.sessions() as session:
            query = select(generations.c.id).where(generations.c.learner_id == owner,
                generations.c.document_id == document_id, generations.c.version_id == version_id,
                generations.c.indexed_at.is_not(None), generations.c.state.in_(['READY','SUPERSEDED']))
            if generation_id is not None:
                query = query.where(generations.c.id == generation_id)
            generation_id = session.execute(query.order_by(generations.c.created_at.desc()).limit(1)).scalar_one_or_none()
            return [dict(r) for r in session.execute(select(chunks.c.id, chunks.c.content, chunks.c.heading_path, chunks.c.spans)
                .where(chunks.c.learner_id == owner, chunks.c.generation_id == generation_id).order_by(chunks.c.ordinal).offset(offset).limit(limit)).mappings()]

    def get_chunk(self, owner, chunk_id):
        with self.sessions() as session:
            row = session.execute(select(chunks, generations.c.version_id).join(generations,
                chunks.c.generation_id == generations.c.id).where(chunks.c.learner_id == owner,
                chunks.c.id == chunk_id, generations.c.indexed_at.is_not(None),
                generations.c.state.in_(['READY','SUPERSEDED']))).mappings().first()
            if row is None:
                raise not_found()
            self._document(session, owner, row['document_id'])
            return dict(row)

    def reconciliation_targets(self, age_seconds, limit=100):
        with self.sessions() as session:
            pending = exists(select(jobs.c.id).where(jobs.c.generation_id == generations.c.id,
                jobs.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT'])))
            query = select(generations.c.id, generations.c.learner_id, generations.c.document_id, generations.c.state,
                documents.c.deleted_at, documents.c.active_generation_id).join(documents,
                generations.c.document_id == documents.c.id).where(
                    generations.c.created_at < now() - timedelta(seconds=age_seconds),
                    or_(documents.c.deleted_at.is_not(None), generations.c.state == 'SUPERSEDED',
                        and_(generations.c.state == 'FAILED', ~pending)))
            query = query.order_by(generations.c.reconciled_at.asc().nulls_first(), generations.c.created_at, generations.c.id).limit(limit)
            return [dict(r) for r in session.execute(query).mappings()]

    def mark_reconciled(self, generation_id):
        with self.sessions.begin() as session:
            session.execute(update(generations).where(generations.c.id == generation_id).values(reconciled_at=now()))

    def storage_keys(self):
        with self.sessions() as session:
            return set(session.execute(select(versions.c.storage_key)).scalars())

    def index_health(self, owner=None, limit=100):
        """Bounded operator metadata; never returns source names or content."""
        with self.sessions() as session:
            job_scope = [jobs.c.learner_id == owner] if owner else []
            states = {state: count for state, count in session.execute(select(jobs.c.state, func.count())
                .where(*job_scope).group_by(jobs.c.state))}
            pending = job_scope + [jobs.c.state.in_(['QUEUED','RUNNING','RETRY_WAIT'])]
            oldest = session.execute(select(func.min(jobs.c.created_at)).where(*pending)).scalar_one()
            cleanup_oldest = session.execute(select(func.min(jobs.c.created_at)).where(*pending, jobs.c.operation == 'DELETE')).scalar_one()
            scope = [documents.c.deleted_at.is_(None), documents.c.active_generation_id.is_not(None)]
            if owner:
                scope.append(documents.c.learner_id == owner)
            count = session.execute(select(func.count()).select_from(documents).where(*scope)).scalar_one()
            ready = [dict(row) for row in session.execute(select(generations.c.id, generations.c.learner_id,
                generations.c.chunk_count, generations.c.config).join(documents,
                    documents.c.active_generation_id == generations.c.id).where(*scope)
                .order_by(generations.c.id).limit(limit)).mappings()]
            return dict(job_states=states, oldest_pending_seconds=(now() - oldest).total_seconds() if oldest else 0,
                oldest_cleanup_seconds=(now() - cleanup_oldest).total_seconds() if cleanup_oldest else 0,
                active_generation_count=count, checked_generation_limit=limit, active_generations=ready)

    def record_usage(self, owner, document_ids):
        if document_ids:
            with self.sessions.begin() as session:
                session.execute(update(documents).where(documents.c.learner_id == owner, documents.c.id.in_(document_ids),
                    documents.c.deleted_at.is_(None)).values(last_used_at=now()))

    def resume_cleanup(self):
        with self.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.operation == 'DELETE', jobs.c.state == 'FAILED').values(
                state='RETRY_WAIT', attempts=0, next_attempt_at=now() + timedelta(seconds=60), updated_at=now()))

    def tag_document(self, owner, document_id, expected_revision, concept_ids):
        with self.sessions.begin() as session:
            doc = self._document(session, owner, document_id, lock=True)
            if doc['revision'] != expected_revision:
                raise conflict()
            session.execute(update(documents).where(documents.c.id == document_id).values(concept_ids=concept_ids,
                revision=doc['revision'] + 1, updated_at=now()))
            session.execute(delete(document_concepts).where(document_concepts.c.document_id == document_id))
            if concept_ids:
                session.execute(document_concepts.insert(), [dict(document_id=document_id, concept_id=c) for c in concept_ids])
            ids = list(session.execute(select(chunks.c.id).where(chunks.c.learner_id == owner,
                chunks.c.generation_id == doc['active_generation_id'])).scalars())
            if ids:
                session.execute(update(chunks).where(chunks.c.id.in_(ids)).values(concept_ids=concept_ids))
                session.execute(delete(chunk_concepts).where(chunk_concepts.c.chunk_id.in_(ids)))
                if concept_ids:
                    session.execute(chunk_concepts.insert(), [dict(chunk_id=i, concept_id=c) for i in ids for c in concept_ids])
        return self.get_document(owner, document_id)
