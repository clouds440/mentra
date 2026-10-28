"""Bounded owned topic search and membership, sharing learner transactions."""
from uuid import uuid4
from hashlib import sha256

from sqlalchemy import select, func, or_, update, literal, case
from sqlalchemy.dialects.postgresql import insert

from .base import PostgresRepositoryBase
from app.learner.normalization import normalize, query_terms
from app.learner.repositories.tables.topics import learning_topic as t, topic_skill as m
from app.learner.repositories.tables import concept as c, context_concept as links, learner_concept_state as states
from app.learner.exceptions import LearnerError
from app.learner.repositories.tables import learner_audit


class TopicsStore(PostgresRepositoryBase):
    def topic_registry_version(self, owner):
        with self._session() as session:
            parents = session.execute(select(func.count(), func.coalesce(func.sum(t.c.revision), 0)).where(t.c.learner_id == owner)).one()
            skills = session.scalar(select(func.count()).select_from(m).where(m.c.learner_id == owner))
            return tuple(parents) + (skills,)

    def topic_parent_ids(self, owner, context_ids):
        linked = select(links.c.concept_id).where(links.c.learner_id == owner,
            links.c.context_id.in_(context_ids), links.c.concept_id == m.c.concept_id).exists()
        with self._session() as session:
            return dict(session.execute(select(m.c.concept_id, m.c.topic_id).where(
                m.c.learner_id == owner, m.c.published.is_(True), m.c.topic_id.is_not(None), linked)).all())

    def move_topic_skill(self, owner, source, skill_id, target, operation, revision, *, undo=False):
        from app.core.exceptions import AppError
        with self._session() as session:
            receipt = session.execute(select(learner_audit.c.details_json).where(learner_audit.c.learner_id == owner,
                learner_audit.c.action == 'topic_skill_moved', learner_audit.c.details_json['operation'].as_string() == operation)
                .limit(1)).scalar_one_or_none()
            current = session.execute(select(m).where(m.c.learner_id == owner, m.c.concept_id == skill_id)).mappings().first()
            if not current:
                raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This subskill is unavailable.', 404)
            if undo:
                if not receipt or (source, target, skill_id) != (receipt['source'], receipt['target'], receipt['skill_id']):
                    raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This placement change is unavailable.', 404)
                source, target = receipt['target'], receipt['source']
                reverted = session.scalar(select(learner_audit.c.id).where(learner_audit.c.learner_id == owner,
                    learner_audit.c.action == 'topic_skill_move_undone', learner_audit.c.details_json['operation'].as_string() == operation).limit(1))
                if reverted:
                    return dict(topic_id=target, operation_id=operation)
            elif receipt:
                if (source, target, skill_id) != (receipt['source'], receipt['target'], receipt['skill_id']):
                    raise AppError('OPERATION_CONFLICT', 'This request belongs to another placement change.', 409)
                return dict(topic_id=receipt['target'], operation_id=operation)
            parents = {row['id']: dict(row) for row in session.execute(select(t).where(
                t.c.learner_id == owner, t.c.id.in_([source, target]))).mappings()}
            if len(parents) != 2:
                raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'Choose another available topic.', 404)
            expected_revision = receipt['target_revision'] if undo else revision
            if current['topic_id'] != source or parents[source]['revision'] != expected_revision:
                raise AppError('REVISION_CONFLICT', 'This placement changed. Refresh before moving it.', 409)
            session.execute(update(m).where(m.c.learner_id == owner, m.c.concept_id == skill_id).values(
                topic_id=target, resolver_version='user-placement-v1'))
            session.execute(update(t).where(t.c.learner_id == owner, t.c.id.in_([source, target])).values(revision=t.c.revision + 1))
            self.audit('topic_skill_move_undone' if undo else 'topic_skill_moved', dict(operation=operation,
                source=source, target=target, skill_id=skill_id, target_revision=parents[target]['revision'] + 1), owner, skill_id)
            return dict(topic_id=target, operation_id=operation)

    def rename_topic(self, owner, identifier, name, revision):
        from app.core.exceptions import AppError
        with self._session() as session:
            row = session.execute(select(t).where(t.c.learner_id == owner, t.c.id == identifier)).mappings().first()
            if not row:
                raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This topic is unavailable.', 404)
            if row['name'] == name:
                return dict(id=identifier, name=name, revision=row['revision'])
            if row['revision'] != revision:
                raise AppError('REVISION_CONFLICT', 'This topic changed. Refresh before renaming it.', 409)
            conflict = session.scalar(select(t.c.id).where(t.c.learner_id == owner, t.c.context_id == row['context_id'],
                t.c.scope_key == row['scope_key'], t.c.normalized_name == normalize(name), t.c.id != identifier))
            if conflict:
                raise AppError('REVISION_CONFLICT', 'A topic with this name and scope already exists.', 409)
            session.execute(update(t).where(t.c.id == identifier).values(name=name, normalized_name=normalize(name), revision=revision + 1))
            self.audit('topic_renamed', dict(topic_id=identifier, previous_name=row['name'], name=name), owner)
            return dict(id=identifier, name=name, revision=revision + 1)

    def topic_practice_skills(self, owner, context_id, topic_id, now, limit):
        from datetime import timedelta
        # Select a bounded need-aware sample in SQL rather than always repeating
        # the first alphabetical skills or loading every evidence window.
        uncertainty = 1 - func.coalesce(states.c.estimate_confidence, 0)
        risk = case((states.c.last_demonstrated_at < now - timedelta(days=30), 1),
                    else_=1 - func.coalesce(states.c.retention_confidence, 0))
        need = case((states.c.verification_required.is_(True), 1),
            (states.c.mastery.is_(None), .8),
            else_=.4 * (1 - states.c.mastery) + .2 * uncertainty + .2 * risk + .1)
        score = need * (.2 + .8 * links.c.importance)
        with self._session() as session:
            return [row['id'] for row in session.execute(select(c.c.id).join(m,
                (m.c.concept_id == c.c.id) & (m.c.learner_id == owner)).join(links,
                (links.c.concept_id == c.c.id) & (links.c.learner_id == owner) & (links.c.context_id == context_id))
                .outerjoin(states, (states.c.concept_id == c.c.id) & (states.c.learner_id == owner))
                .where(m.c.topic_id == topic_id, m.c.published.is_(True), links.c.importance > 0,
                    c.c.status == 'ACTIVE').order_by(score.desc(), states.c.last_evidence_at.asc().nulls_first(), c.c.id)
                .limit(min(20, limit))).mappings()]

    def save_topic_proposal(self, owner, payload):
        with self._session() as session:
            return session.execute(insert(learner_audit).values(learner_id=owner,
                action='topic_organization_proposed', details_json=payload).returning(learner_audit.c.id)).scalar_one()

    def topic_proposal(self, owner, identifier):
        with self._session() as session:
            row = session.execute(select(learner_audit).where(learner_audit.c.learner_id == owner,
                learner_audit.c.id == identifier, learner_audit.c.action == 'topic_organization_proposed')).mappings().first()
            return dict(row) if row else None

    def topic_change_receipt(self, owner, identifier, action):
        with self._session() as session:
            return session.execute(select(learner_audit.c.details_json).where(learner_audit.c.learner_id == owner,
                learner_audit.c.action == action, learner_audit.c.details_json['proposal_id'].as_integer() == identifier)
                .order_by(learner_audit.c.id.desc()).limit(1)).scalar_one_or_none()

    def ungroup_topic_skills(self, owner, expected, revisions=None):
        with self._session() as session:
            current = self.skill_memberships(owner, list(expected))
            if any(current.get(identifier, {}).get('topic_id') != parent for identifier, parent in expected.items()):
                raise LearnerError('This grouping has changed since it was applied')
            if revisions:
                actual = dict(session.execute(select(t.c.id, t.c.revision).where(t.c.learner_id == owner, t.c.id.in_(revisions))).all())
                if actual != revisions:
                    raise LearnerError('This grouping has changed since it was applied')
            session.execute(update(t).where(t.c.learner_id == owner, t.c.id.in_(set(expected.values()))).values(revision=t.c.revision+1))
            session.execute(update(m).where(m.c.learner_id == owner, m.c.concept_id.in_(expected)).values(
                topic_id=None, resolver_version='unclassified-v1'))

    def known_topic_labels(self, owner, context_id, labels, topic=''):
        with self._session() as session:
            rows = session.execute(select(c, m.c.label, m.c.phrases, t.c.name, t.c.scope).join(m,
                (m.c.concept_id == c.c.id) & (m.c.learner_id == owner)).join(t,
                (t.c.id == m.c.topic_id) & (t.c.learner_id == owner)).where(
                    or_(t.c.context_id == context_id, select(links.c.concept_id).where(
                        links.c.learner_id == owner, links.c.context_id == context_id, links.c.concept_id == c.c.id).exists()),
                    c.c.status == 'ACTIVE',
                    or_(*(m.c.phrases.contains('\n' + normalize(label) + '\n', autoescape=True) for label in labels)))) .mappings()
            result, ambiguous = {}, set()
            for row in rows:
                if not set(query_terms(topic)).issubset(set(query_terms(row['name'] + ' ' + row['scope']))):
                    continue  # Same wording in a different subject needs semantic advice.
                for label in labels:
                    if '\n' + normalize(label) + '\n' in row['phrases']:
                        if label in result and result[label].id != row['id']:
                            ambiguous.add(label)
                        result[label] = self._concept_from_row(row)
            return {label: value for label, value in result.items() if label not in ambiguous}

    def skill_memberships(self, owner, ids):
        with self._session() as session:
            rows = session.execute(select(m, t.c.name, t.c.scope, t.c.context_id, t.c.revision).outerjoin(t,
                (t.c.id == m.c.topic_id) & (t.c.learner_id == m.c.learner_id)).where(
                    m.c.learner_id == owner, m.c.concept_id.in_(ids))).mappings()
            return {row['concept_id']: dict(row) for row in rows}

    def topic_candidates(self, owner, context_id, query, limit=12):
        terms = query_terms(query)
        score = sum((case((or_(t.c.normalized_name.contains(term, autoescape=True),
            m.c.phrases.contains(term, autoescape=True), func.lower(m.c.label).contains(term, autoescape=True)), 1), else_=0)
            for term in terms), literal(0))
        with self._session() as session:
            # Aggregate before limiting; neither all skills nor all topics enter a prompt.
            ranked = select(t.c.id, func.max(score).label('score')).outerjoin(m,
                (m.c.topic_id == t.c.id) & (m.c.learner_id == owner)).where(t.c.learner_id == owner,
                ).group_by(t.c.id).subquery()
            rows = session.execute(select(t).join(ranked, ranked.c.id == t.c.id).order_by(
                ranked.c.score.desc(), case((t.c.context_id == context_id, 1), else_=0).desc(),
                t.c.normalized_name, t.c.id).limit(limit)).mappings().all()
            skill_score = sum((case((or_(func.lower(m.c.label).contains(term, autoescape=True),
                m.c.phrases.contains(term, autoescape=True)), 1), else_=0) for term in terms), literal(0))
            children = select(m.c.concept_id, m.c.topic_id, m.c.label, m.c.ability,
                func.row_number().over(partition_by=m.c.topic_id, order_by=(skill_score.desc(), m.c.label)).label('position')).where(
                    m.c.learner_id == owner, m.c.topic_id.in_([row['id'] for row in rows]),
                    m.c.concept_id.in_(select(c.c.id).where(c.c.status == 'ACTIVE'))).subquery()
            skills = session.execute(select(children).where(children.c.position <= 5)).mappings().all()
            result = [dict(row, subskills=[{key: skill[key] for key in ('concept_id', 'label', 'ability')}
                for skill in skills if skill['topic_id'] == row['id']]) for row in rows]
            return result

    def save_topic_membership(self, owner, context_id, skill_id, placement, *, published=False):
        with self._session() as session:
            current = session.execute(select(m).where(m.c.learner_id == owner,
                m.c.concept_id == skill_id)).mappings().first()
            if current and current['topic_id']:
                # Ordinary routing never reparents a known skill.
                if placement.topic_id and current['topic_id'] != placement.topic_id:
                    raise LearnerError('This subskill already belongs to a different topic')
                phrases = list(dict.fromkeys([*current['phrases'].splitlines(), normalize(placement.label)]))[-64:]
                session.execute(update(m).where(m.c.learner_id == owner, m.c.concept_id == skill_id).values(
                    published=published or current['published'], phrases='\n' + '\n'.join(phrase for phrase in phrases if phrase) + '\n'))
                return current['topic_id']
            topic_id = placement.topic_id
            if topic_id:
                topic = session.execute(select(t.c.id).where(t.c.learner_id == owner,
                    t.c.id == topic_id)).scalar_one_or_none()
                if not topic:
                    raise LearnerError('Topic is unavailable in this learning area')
            else:
                stmt = insert(t).values(id=str(uuid4()), learner_id=owner, context_id=context_id,
                    name=placement.topic_name, normalized_name=normalize(placement.topic_name), scope=placement.scope,
                    scope_key=sha256(normalize(placement.scope).encode()).hexdigest())
                topic_id = session.execute(stmt.on_conflict_do_update(
                    index_elements=['learner_id', 'context_id', 'normalized_name', 'scope_key'],
                    set_={'normalized_name': stmt.excluded.normalized_name}).returning(t.c.id)).scalar_one()
            stmt = insert(m).values(learner_id=owner, concept_id=skill_id, topic_id=topic_id,
                label=placement.skill_name or placement.label, ability=placement.ability, published=published,
                phrases='\n' + normalize(placement.label) + '\n', resolver_version='topic-organization-v1')
            session.execute(stmt.on_conflict_do_update(index_elements=['learner_id', 'concept_id'],
                set_=dict(topic_id=topic_id, published=published or bool(current and current['published']),
                    ability=stmt.excluded.ability, resolver_version='topic-organization-v1')))
            if published:
                session.execute(update(t).where(t.c.learner_id == owner, t.c.id == topic_id).values(revision=t.c.revision+1))
            return topic_id

    def save_ungrouped_skill(self, owner, skill_id, label):
        stmt = insert(m).values(learner_id=owner, concept_id=skill_id, topic_id=None,
            label=label, ability=label, published=False, phrases='\n' + normalize(label) + '\n',
            resolver_version='unclassified-v1')
        with self._session() as session:
            session.execute(stmt.on_conflict_do_nothing(index_elements=['learner_id', 'concept_id']))

    def publish_topic_skills(self, owner, ids):
        with self._session() as session:
            newly_visible = select(m.c.topic_id).where(m.c.learner_id == owner, m.c.concept_id.in_(ids), m.c.published.is_(False))
            session.execute(update(t).where(t.c.learner_id == owner, t.c.id.in_(newly_visible)).values(revision=t.c.revision+1))
            session.execute(update(m).where(m.c.learner_id == owner, m.c.concept_id.in_(ids)).values(published=True))
            targets = select(t.c.context_id, m.c.concept_id, m.c.learner_id).join(m,
                (m.c.topic_id == t.c.id) & (m.c.learner_id == owner)).where(m.c.concept_id.in_(ids))
            session.execute(insert(links).from_select(['context_id', 'concept_id', 'learner_id'], targets)
                .on_conflict_do_nothing(index_elements=['context_id', 'concept_id']))

    def topic_page(self, owner, context_ids, query, limit, offset):
        linked = select(links.c.concept_id).where(links.c.learner_id == owner,
            links.c.context_id.in_(context_ids), links.c.concept_id == m.c.concept_id).exists()
        filters = [m.c.learner_id == owner, m.c.published.is_(True), linked,
            m.c.concept_id.in_(select(c.c.id).where(c.c.status == 'ACTIVE'))]
        match = or_(t.c.normalized_name.contains(query, autoescape=True),
            func.lower(t.c.scope).contains(query, autoescape=True),
            func.lower(m.c.label).contains(query, autoescape=True), m.c.phrases.contains(query, autoescape=True))
        with self._session() as session:
            base = select(t.c.id, t.c.name, t.c.scope, t.c.context_id, t.c.revision,
                func.count().label('subskill_count'),
                func.sum(case((states.c.mastery.is_not(None), 1), else_=0)).label('checked_count')).join(m,
                    (m.c.topic_id == t.c.id) & (m.c.learner_id == owner)).outerjoin(states,
                    (states.c.concept_id == m.c.concept_id) & (states.c.learner_id == owner)).where(*filters).group_by(t.c.id)
            if query:
                base = base.having(func.bool_or(match))
            total = session.scalar(select(func.count()).select_from(base.subquery()))
            offset = min(offset, max(0, (total - 1) // limit) * limit)
            rows = [dict(row) for row in session.execute(base.order_by(func.lower(t.c.name), t.c.id)
                .offset(offset).limit(limit)).mappings()]
            if query and rows:
                hits = select(m.c.topic_id, m.c.label, func.row_number().over(partition_by=m.c.topic_id,
                    order_by=m.c.label).label('position')).where(m.c.learner_id == owner,
                    m.c.published.is_(True), m.c.topic_id.in_([row['id'] for row in rows]), linked,
                    or_(func.lower(m.c.label).contains(query, autoescape=True),
                        m.c.phrases.contains(query, autoescape=True))).subquery()
                matches = session.execute(select(hits).where(hits.c.position <= 3)).mappings().all()
                for row in rows:
                    row['matching_skills'] = [match['label'] for match in matches if match['topic_id'] == row['id']]
            grouped = select(m.c.concept_id).where(m.c.learner_id == owner, m.c.published.is_(True), m.c.topic_id.is_not(None))
            ungrouped = session.scalar(select(func.count(func.distinct(links.c.concept_id))).where(
                links.c.learner_id == owner, links.c.context_id.in_(context_ids), ~links.c.concept_id.in_(grouped),
                links.c.concept_id.in_(select(c.c.id).where(c.c.status == 'ACTIVE'))))
            return rows, total, ungrouped, offset

    def topic_skills(self, owner, context_ids, topic_id, query, limit, offset):
        linked = select(links.c.concept_id).where(links.c.learner_id == owner,
            links.c.context_id.in_(context_ids), links.c.concept_id == c.c.id).exists()
        with self._session() as session:
            base = select(c).where(linked, c.c.status == 'ACTIVE')
            if topic_id == 'ungrouped':
                grouped = select(m.c.concept_id).where(m.c.learner_id == owner, m.c.published.is_(True), m.c.topic_id.is_not(None))
                base = base.outerjoin(m, (m.c.concept_id == c.c.id) & (m.c.learner_id == owner) & m.c.published.is_(True)).where(~c.c.id.in_(grouped))
                topic = dict(id='ungrouped', name='Not grouped yet', scope='Existing skills are preserved. Organize them into topics when ready.')
            else:
                topic = session.execute(select(t).where(t.c.id == topic_id, t.c.learner_id == owner)).mappings().first()
                if not topic:
                    raise LearnerError('Topic is unavailable')
                base = base.join(m, (m.c.concept_id == c.c.id) & (m.c.learner_id == owner)).where(
                    m.c.topic_id == topic_id, m.c.published.is_(True))
            if query:
                conditions = [c.c.normalized_name.contains(query, autoescape=True),
                    c.c.description.contains(query, autoescape=True)]
                conditions.extend([func.lower(m.c.label).contains(query, autoescape=True),
                    m.c.phrases.contains(query, autoescape=True)])
                base = base.where(or_(*conditions))
            total = session.scalar(select(func.count()).select_from(base.subquery()))
            offset = min(offset, max(0, (total - 1) // limit) * limit)
            name = func.coalesce(m.c.label, c.c.canonical_name)
            rows = [self._concept_from_row(row) for row in session.execute(base.order_by(
                func.lower(name), c.c.id).limit(limit).offset(offset)).mappings()]
            return dict(topic), rows, total, offset

    def ungrouped_skills(self, owner, context_id, limit=10):
        grouped = select(m.c.concept_id).where(m.c.learner_id == owner, m.c.topic_id.is_not(None))
        with self._session() as session:
            from dataclasses import replace
            rows = session.execute(select(c, m.c.label).join(links,
                links.c.concept_id == c.c.id).where(links.c.learner_id == owner,
                links.c.context_id == context_id, ~c.c.id.in_(grouped), c.c.status == 'ACTIVE')
                .outerjoin(m, (m.c.concept_id == c.c.id) & (m.c.learner_id == owner)).order_by(c.c.id).limit(limit)).mappings()
            return [replace(self._concept_from_row(row), canonical_name=row['label'] or row['canonical_name']) for row in rows]
