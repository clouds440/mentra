"""Bounded catalog and sequential-source persistence, scoped to authorized IDs."""
from sqlalchemy import select, or_
from .tables import documents, chunks, generations

class DocumentReadStore:
    def __init__(self, sessions):
        self.sessions = sessions

    def find(self, owner, identifiers, terms):
        with self.sessions() as session:
            statement = select(
                documents.c.id, documents.c.title, documents.c.filename
            ).where(
                documents.c.learner_id == owner,
                documents.c.id.in_(identifiers),
            )
            for term in terms:
                statement = statement.where(
                    or_(
                        documents.c.title.icontains(term, autoescape=True),
                        documents.c.filename.icontains(term, autoescape=True),
                    )
                )
            rows = [
                dict(row)
                for row in session.execute(
                    statement.order_by(
                        documents.c.updated_at.desc(), documents.c.id
                    ).limit(13)
                ).mappings()
            ]
        return rows

    def read(self, owner, generation_id):
        with self.sessions() as session:
            source = (
                session.execute(
                    select(
                        generations.c.version_id,
                        generations.c.warnings,
                        documents.c.title,
                        documents.c.filename,
                    )
                    .join(documents, generations.c.document_id == documents.c.id)
                    .where(
                        generations.c.id == generation_id,
                        generations.c.learner_id == owner,
                    )
                )
                .mappings()
                .one()
            )
            rows = [
                dict(row)
                for row in session.execute(
                    select(chunks)
                    .where(
                        chunks.c.learner_id == owner,
                        chunks.c.generation_id == generation_id,
                    )
                    .order_by(chunks.c.ordinal)
                    .limit(5001)
                ).mappings()
            ]
        return dict(source), rows
