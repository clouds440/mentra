"""Owner-scoped content history. Restoring is a new explicit user assertion."""

import json

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert

from .tables import evidence as e
from .tables import revisions as r
from .tables import suppression as s


def snapshot(row):
    fields = (
        "content",
        "category",
        "status",
        "origin",
        "pinned",
        "expires_at",
        "confirmed_at",
        "source_at",
    )
    return json.loads(
        json.dumps(
            {key: row.get(key) for key in fields},
            default=lambda value: value.isoformat(),
        )
    )


def archive_evidence(session, owner, identifier, revision):
    session.execute(
        update(e)
        .where(
            e.c.learner_id == owner,
            e.c.memory_id == identifier,
            e.c.valid_until_revision.is_(None),
        )
        .values(valid_until_revision=revision)
    )


def suppress(session, owner, keys, stamp, reason="forgotten"):
    for key in set(keys):
        stmt = insert(s).values(
            learner_id=owner, fingerprint=key, created_at=stamp, reason=reason
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["learner_id", "fingerprint"],
                set_={"reason": reason, "created_at": stamp},
                **(
                    {"where": s.c.reason != "forgotten"}
                    if reason != "forgotten"
                    else {}
                ),
            )
        )


class MemoryHistory:
    def revision_page(self, owner, identifier, before=None, limit=20):
        with self.sessions() as session:
            self._get(session, owner, identifier)
            query = select(r).where(
                r.c.learner_id == owner, r.c.memory_id == identifier
            )
            if before:
                query = query.where(r.c.revision < before)
            rows = list(
                session.execute(
                    query.order_by(r.c.revision.desc()).limit(limit + 1)
                ).mappings()
            )
            more = len(rows) > limit
            rows = rows[:limit]
            quotes = list(
                session.execute(
                    select(e)
                    .where(
                        e.c.learner_id == owner,
                        e.c.memory_id == identifier,
                        e.c.valid_from_revision
                        <= max((row["revision"] for row in rows), default=0),
                        or_(
                            e.c.valid_until_revision.is_(None),
                            e.c.valid_until_revision
                            >= min((row["revision"] for row in rows), default=0),
                        ),
                    )
                    .order_by(e.c.source_date.desc())
                    .limit(200)
                ).mappings()
            )
            items = []
            for row in rows:
                support = [
                    {
                        key: value
                        for key, value in quote.items()
                        if key
                        not in (
                            "learner_id",
                            "valid_from_revision",
                            "valid_until_revision",
                        )
                    }
                    for quote in quotes
                    if quote["valid_from_revision"] <= row["revision"]
                    and (
                        quote["valid_until_revision"] is None
                        or quote["valid_until_revision"] >= row["revision"]
                    )
                ][:5]
                items.append(
                    dict(
                        revision=row["revision"],
                        actor=row["actor"],
                        created_at=row["created_at"],
                        snapshot=row["snapshot"],
                        evidence=support,
                    )
                )
            return dict(items=items, next_before=rows[-1]["revision"] if more else None)

    def restore_revision(self, owner, identifier, body):
        from app.core.exceptions import AppError

        from ..schemas import MemoryEdit

        with self.sessions() as session:
            self._get(session, owner, identifier)
            value = session.scalar(
                select(r.c.snapshot).where(
                    r.c.learner_id == owner,
                    r.c.memory_id == identifier,
                    r.c.revision == body.restore_revision,
                )
            )
        if not value:
            raise AppError(
                "MEMORY_HISTORY_UNAVAILABLE",
                "This older memory content is unavailable.",
                404,
            )
        return self.edit(
            owner,
            identifier,
            MemoryEdit(
                expected_revision=body.expected_revision,
                content=value["content"],
                category=value["category"],
            ),
        )
