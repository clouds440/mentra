"""Canonical, bounded chat read facade for the history-management module."""
from sqlalchemy import select, func, or_, and_, text
from app.core.exceptions import AppError
from .tables import conversations as c, messages as m, turns as t
from .postgres import ChatRepository


class ChatReadFacade:
    def __init__(self, repository):
        self.repository = repository

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
            if body.query:
                vector, query = func.to_tsvector('simple', m.c.content), func.websearch_to_tsquery('simple', body.query)
                hits = session.execute(base.where(vector.op('@@')(query)).order_by(func.ts_rank_cd(vector, query).desc(), m.c.created_at.desc(), m.c.id).limit(body.limit)).mappings().all()
                if not hits:
                    # Index-backed pg_trgm word similarity; no unbounded Python scans.
                    hits = session.execute(base.where(m.c.content.op('OPERATOR(public.%>)')(body.query)).order_by(func.public.word_similarity(body.query, m.c.content).desc(), m.c.id).limit(body.limit)).mappings().all()
            else:
                hits = session.execute(base.order_by(m.c.sequence.asc() if body.after_sequence is not None else m.c.sequence.desc()).limit(body.limit)).mappings().all()
            if not hits:
                return []
            ranges = [and_(m.c.conversation_id == x['conversation_id'], m.c.sequence.between(max(1, x['sequence'] - 1), x['sequence'] + 1)) for x in hits]
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
