"""Canonical, bounded chat read facade for the history-management module."""
from sqlalchemy import select, func, or_, and_, text
from app.core.exceptions import AppError
from .tables import conversations as c, messages as m, turns as t
from .postgres import ChatRepository


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class ChatReadFacade:
    def __init__(self, repository):
        self.repository = repository

    def search_saved(self, owner, query: str, offset: int = 0):
        from sqlalchemy import case, literal, union_all
        from sqlalchemy.exc import DBAPIError
        from app.chat.schemas import ChatSearchPage
        query = query.strip()
        if not query: return ChatSearchPage(items=[])
        if len(query) > 200 or '\x00' in query or not 0 <= offset <= 180:
            raise AppError('CHAT_SEARCH_QUERY_INVALID', 'Use a search of at most 200 characters.', 422)
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        content_match = m.c.content.ilike(pattern, escape='\\')
        position = func.strpos(func.lower(m.c.content), func.lower(query))
        snippet = case((position > 70, literal('…')), else_=literal('')) + func.substr(
            m.c.content, func.greatest(1, position - 70), 240)
        columns = [m.c.conversation_id, c.c.title, m.c.id.label('matched_message_id'), m.c.sequence,
            m.c.role, snippet.label('snippet'), m.c.created_at]
        base = select(*columns).join(c, and_(c.c.id==m.c.conversation_id, c.c.learner_id==m.c.learner_id)).where(
            m.c.learner_id==owner, c.c.deleted_at.is_(None), m.c.role.in_(['user','assistant']))
        order = (m.c.created_at.desc(), m.c.id.desc())
        # Separate branches keep the existing content trigram index usable. Title
        # matches contribute one latest-message hit rather than an entire transcript.
        messages = base.add_columns(literal('message').label('matched_in')).where(content_match).order_by(*order).limit(offset+21)
        titles = base.add_columns(literal('title').label('matched_in')).where(c.c.title.ilike(pattern, escape='\\'),
            m.c.sequence==c.c.message_count, ~content_match).order_by(*order).limit(offset+21)
        hits = union_all(messages, titles).subquery()
        statement = select(hits).order_by(hits.c.created_at.desc(), hits.c.matched_message_id.desc()).offset(offset).limit(21)
        try:
            with self.repository.sessions() as session:
                session.execute(text('SET LOCAL statement_timeout = 2000'))
                rows = list(session.execute(statement).mappings())
        except DBAPIError as error:
            if getattr(error.orig, 'sqlstate', None) == '57014':
                raise AppError('CHAT_SEARCH_BUSY', 'This search took too long. Try a more specific phrase.', 503) from None
            raise
        return ChatSearchPage(items=rows[:20], next_offset=offset+20 if len(rows)>20 and offset<180 else None,
            truncated=offset==180 and len(rows)>20)

    def saved_exchange(self, owner, conversation_id, message_id):
        from app.chat.schemas import SavedExchange
        # One statement binds ownership, live chat, anchor and neighboring messages
        # to the same snapshot. Search does not create a parallel transcript store.
        anchor = select(m.c.sequence).join(c, and_(c.c.id==m.c.conversation_id, c.c.learner_id==m.c.learner_id)).where(
            m.c.learner_id==owner, m.c.conversation_id==conversation_id, m.c.id==message_id,
            c.c.deleted_at.is_(None), m.c.role.in_(['user','assistant'])).cte('anchor')
        statement = select(m.c.id, m.c.role, m.c.content, m.c.created_at, c.c.title).join(c,
            and_(c.c.id==m.c.conversation_id, c.c.learner_id==m.c.learner_id)).where(m.c.learner_id==owner,
            m.c.conversation_id==conversation_id, c.c.deleted_at.is_(None), m.c.role.in_(['user','assistant']),
            m.c.sequence.between(func.greatest(1, select(anchor.c.sequence).scalar_subquery()-1),
                select(anchor.c.sequence).scalar_subquery()+1)).order_by(m.c.sequence).limit(3)
        with self.repository.sessions() as session:
            session.execute(text('SET LOCAL statement_timeout = 2000'))
            rows = list(session.execute(statement).mappings())
        if not rows or not any(row['id']==message_id for row in rows):
            raise AppError('CHAT_MESSAGE_UNAVAILABLE', 'This saved exchange is unavailable.', 404)
        return SavedExchange(conversation_id=conversation_id, title=rows[0]['title'], matched_message_id=message_id,
            messages=[{key:row[key] for key in ('id','role','content','created_at')} for row in rows])

    def evidence(self, owner, identifier):
        with self.repository.sessions() as session:
            row = session.execute(select(m).join(c, and_(c.c.id == m.c.conversation_id, c.c.learner_id == m.c.learner_id))
                .where(m.c.learner_id == owner, m.c.id == identifier, m.c.role == 'user', c.c.deleted_at.is_(None))).mappings().first()
            if not row:
                raise AppError('HISTORY_NOT_FOUND', 'User message not found.', 404)
            return dict(row)

    @staticmethod
    def _window_query():
        return select(m, t.c.state.label('exchange_status')).outerjoin(t, and_(t.c.learner_id == m.c.learner_id,
            t.c.conversation_id == m.c.conversation_id, or_(t.c.user_sequence == m.c.sequence, t.c.assistant_sequence == m.c.sequence)))

    def lookup(self, owner, current_chat, current_sequence, body, visible_ids=()):
        with self.repository.sessions() as session:
            # Common terms can produce many ranked candidates even with GIN.
            # Keep database work inside the persistent turn's finite deadline.
            session.execute(text('SET LOCAL statement_timeout = 2000'))
            if body.scope == 'current_chat':
                self.repository._conversation(session, owner, current_chat)
            ids = [current_chat] if body.scope == 'current_chat' else [str(x) for x in body.chat_ids]
            if body.scope == 'selected_chats':
                found = set(session.scalars(select(c.c.id).where(c.c.learner_id == owner, c.c.id.in_(ids), c.c.deleted_at.is_(None))))
                if found != set(ids):
                    raise AppError('HISTORY_NOT_FOUND', 'One or more conversations are unavailable.', 404)
            eligible = [m.c.learner_id == owner, c.c.deleted_at.is_(None), m.c.role.in_(['user', 'assistant']),
                or_(m.c.conversation_id != current_chat, m.c.sequence < current_sequence)]
            if ids:
                eligible.append(m.c.conversation_id.in_(ids))
            if body.before_sequence is not None:
                if body.scope != 'current_chat':
                    raise AppError('HISTORY_CURSOR_INVALID', 'Sequence anchors require current_chat scope.', 422)
                eligible.append(m.c.sequence < body.before_sequence)
            if body.after_sequence is not None:
                eligible.append(m.c.sequence > body.after_sequence)
            if body.created_after:
                eligible.append(m.c.created_at >= body.created_after)
            if body.created_before:
                eligible.append(m.c.created_at < body.created_before)
            if visible_ids:
                eligible.append(m.c.id.not_in(visible_ids))
            base = select(m.c.id, m.c.conversation_id, m.c.sequence, c.c.title).join(c,
                and_(m.c.conversation_id == c.c.id, m.c.learner_id == c.c.learner_id)).where(*eligible)
            if body.message_id:
                hits = session.execute(base.where(m.c.id == str(body.message_id)).limit(1)).mappings().all()
            elif body.query:
                vector, query = func.to_tsvector('simple', m.c.content), func.websearch_to_tsquery('simple', body.query)
                hits = session.execute(base.where(vector.op('@@')(query)).order_by(func.ts_rank_cd(vector, query).desc(), m.c.created_at.desc(), m.c.id).limit(body.limit)).mappings().all()
                if not hits:
                    # Index-backed pg_trgm word similarity; no unbounded Python scans.
                    hits = session.execute(base.where(m.c.content.op('OPERATOR(public.%>)')(body.query)).order_by(func.public.word_similarity(body.query, m.c.content).desc(), m.c.id).limit(body.limit)).mappings().all()
            else:
                hits = session.execute(base.order_by(m.c.sequence.asc() if body.after_sequence is not None else m.c.sequence.desc()).limit(body.limit)).mappings().all()
            if not hits:
                return []
            ranges = [and_(m.c.conversation_id == x['conversation_id'],
                m.c.sequence == x['sequence'] if body.message_id else m.c.sequence.between(max(1, x['sequence'] - 1), x['sequence'] + 1)) for x in hits]
            # At most three disjoint windows, expanded in one query.
            rows = [dict(x) for x in session.execute(self._window_query().where(m.c.learner_id == owner, or_(*ranges),
                m.c.role.in_(['user', 'assistant']), or_(m.c.conversation_id != current_chat, m.c.sequence < current_sequence))
                .order_by(m.c.conversation_id, m.c.sequence).limit(9)).mappings()]
            seen, windows = set(visible_ids), []
            for hit in hits:
                items = []
                for row in rows:
                    if row['conversation_id'] == hit['conversation_id'] and abs(row['sequence'] - hit['sequence']) <= 1 and row['id'] not in seen:
                        seen.add(row['id'])
                        items.append(dict(id=row['id'], role=row['role'], sequence=row['sequence'], content=row['content'],
                            exchange_status=row['exchange_status'] or 'UNKNOWN', created_at=row['created_at'].isoformat()))
                if items:
                    windows.append(dict(conversation_id=hit['conversation_id'], title=hit['title'], messages=items,
                        matched_message_id=hit['id'],
                        next_before_sequence=min(x['sequence'] for x in items), next_after_sequence=max(x['sequence'] for x in items)))
            return windows

    def window(self, owner, conversation_id, sequence):
        with self.repository.sessions() as session:
            conversation = self.repository._conversation(session, owner, conversation_id)
            rows = session.execute(self._window_query().where(m.c.learner_id == owner, m.c.conversation_id == conversation_id,
                m.c.sequence.between(max(1, sequence - 1), sequence + 1), m.c.role.in_(['user','assistant']))
                .order_by(m.c.sequence).limit(3)).mappings().all()
            return dict(title=conversation['title'], conversation_id=conversation_id,
                messages=[ChatRepository._public_message(x) for x in rows])
