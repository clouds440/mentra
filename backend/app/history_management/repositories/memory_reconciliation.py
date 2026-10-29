"""Apply one capture plan and its source cursor in an owner-locked transaction."""

from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.core.config import settings
from app.core.exceptions import AppError

from .memory_history import archive_evidence, suppress
from .tables import evidence as e
from .tables import memories as m
from .tables import receipts as rc
from .tables import suppression as s


class TransactionSessions:
    """Private adapter: nested domain methods participate in this write only."""

    def __init__(self, session):
        self.session = session

    @contextmanager
    def __call__(self):
        yield self.session

    @contextmanager
    def begin(self):
        yield self.session


class MemoryReconciler:
    def __init__(self, repository):
        self.repository = repository

    def apply(
        self,
        owner,
        claim,
        packet,
        items,
        existing,
        fence,
        foreground_scope=None,
        operation_key=None,
    ):
        from app.summarization.execution import SummaryDeferred

        from ..memory.validation import MemoryValidator
        from .memory_capture import MemoryCaptureRepository
        from .postgres import (
            MemoryRepository,
            conflict,
            fingerprint,
            now,
            source_fingerprint,
        )

        scope = (
            dict(foreground_scope)
            if foreground_scope is not None
            else dict(
                _capture_claim=claim,
                _memory_summary_fence=fence,
                turn_id=claim["turn_id"],
                conversation_id=claim["conversation_id"],
            )
        )
        source = packet["source"]
        known = {str(row["id"]): row for row in existing}
        targets = [
            str(item.target_memory_id)
            for item in items
            if item.target_memory_id and item.action != "skip"
        ]
        if len(targets) != len(set(targets)):
            raise AppError(
                "MEMORY_PLAN_INVALID",
                "Combine changes to each memory before saving.",
                422,
            )
        outcomes = {}
        with self.repository._write_transaction(
            foreground_scope if foreground_scope is not None else scope
        ) as session:
            repository = MemoryRepository(
                TransactionSessions(session),
                self.repository.active_limit,
                self.repository.pending_limit,
            )
            repository._lock(session, owner)
            repository._fence(session, owner, scope)
            from app.chat.repositories.tables import messages

            if not session.scalar(
                select(messages.c.id).where(
                    messages.c.learner_id == owner,
                    messages.c.id == source["id"],
                    messages.c.role == "user",
                    messages.c.conversation_id == source["conversation_id"],
                )
            ):
                raise AppError(
                    "MEMORY_SOURCE_DELETED",
                    "The supporting user message is no longer available.",
                    409,
                )
            # All candidates must still be current: a missing/edited candidate
            # could turn an intended update into a false "new" fact.
            live = {
                str(row["id"]): row
                for row in session.execute(
                    select(m.c.id, m.c.revision).where(
                        m.c.learner_id == owner, m.c.id.in_(known)
                    )
                ).mappings()
            }
            if any(
                key not in live or live[key]["revision"] != row["revision"]
                for key, row in known.items()
            ):
                if foreground_scope is not None:
                    raise conflict()
                raise SummaryDeferred()
            for item in items:
                if (
                    item.action == "skip"
                    or item.equivalent_memory_id
                    or item.evidence_quote not in packet["text"]
                ):
                    continue
                target = str(item.target_memory_id) if item.target_memory_id else None
                if target and (
                    target not in known
                    or item.expected_revision != known[target]["revision"]
                ):
                    raise AppError(
                        "MEMORY_PLAN_INVALID",
                        "Use only supplied memory IDs and revisions.",
                        422,
                    )
                admission = item.admission
                if target and admission.contradicts_existing:
                    admission = admission.model_copy(
                        update={
                            "conflicting_memory_ids": list(
                                dict.fromkeys(
                                    [UUID(target), *admission.conflicting_memory_ids]
                                )
                            )
                        }
                    )
                decision = MemoryValidator.admit(
                    item.content,
                    item.evidence_quote,
                    source["content"],
                    existing,
                    admission,
                )
                if decision["outcome"] not in ("active", "conflict"):
                    continue
                if not admission.explicit_user_statement:
                    continue
                token = target or item.category + ":" + fingerprint(item.content)
                operation = (
                    operation_key
                    or sha256(
                        f"capture-v2:{claim['message_id']}:{claim['content_offset']}:{token}".encode()
                    ).hexdigest()
                )
                previous = session.scalar(
                    select(rc.c.outcome).where(
                        rc.c.learner_id == owner, rc.c.operation_key == operation
                    )
                )
                if previous:
                    continue
                row = repository._get(session, owner, target) if target else None
                if row and row["revision"] != item.expected_revision:
                    raise conflict()
                if (
                    row
                    and row.get("source_at")
                    and source["created_at"] <= row["source_at"]
                ):
                    repository._receipt(
                        session, owner, operation, "outdated_source", target, scope
                    )
                    continue
                blocked = list(
                    session.execute(
                        select(s).where(
                            s.c.learner_id == owner,
                            s.c.fingerprint.in_(
                                [
                                    fingerprint(item.content),
                                    source_fingerprint(source["id"]),
                                ]
                            ),
                        )
                    ).mappings()
                )
                if any(
                    value["reason"] == "forgotten"
                    or value["created_at"] >= source["created_at"]
                    or not target
                    for value in blocked
                ):
                    repository._receipt(
                        session, owner, operation, "rejected", None, scope
                    )
                    continue
                days = {
                    "fact": settings.memory_fact_days,
                    "goal": settings.memory_goal_days,
                    "preference": settings.memory_preference_days,
                }[item.category]
                expiry = source["created_at"] + timedelta(days=days)
                if decision.get("valid_until"):
                    expiry = min(expiry, decision["valid_until"])
                if expiry <= now():
                    continue
                evidence = dict(
                    conversation_id=claim["conversation_id"],
                    message_id=source["id"],
                    quote=item.evidence_quote,
                    source_date=source["created_at"],
                    source_deleted=False,
                    explicit_consent=decision["explicit_consent"],
                )
                review = (
                    item.action == "review"
                    or bool(
                        target
                        and any(
                            key != target for key in decision.get("conflict_ids", [])
                        )
                    )
                    or bool(
                        row
                        and (
                            row["status"] != "active"
                            or row["origin"] == "manual"
                            and item.action == "update"
                            and not item.explicit_correction
                        )
                    )
                )
                if item.action == "create" or review:
                    status = (
                        "conflict"
                        if review or decision["outcome"] == "conflict"
                        else "active"
                    )
                    result = repository.write(
                        owner,
                        item.content,
                        item.category,
                        operation,
                        origin="ai",
                        status=status,
                        evidence=evidence,
                        scope=scope,
                        expires_at=expiry,
                        conflict_ids=list(
                            dict.fromkeys([target, *decision.get("conflict_ids", [])])
                        )
                        if target
                        else decision.get("conflict_ids", []),
                    )
                    outcome = result["outcome"]
                else:
                    if not row:
                        raise AppError(
                            "MEMORY_PLAN_INVALID",
                            "A reconciliation target is required.",
                            422,
                        )
                    content = (
                        row["content"] if item.action == "reaffirm" else item.content
                    )
                    new_hash = fingerprint(content)
                    collision = session.scalar(
                        select(m.c.id).where(
                            m.c.learner_id == owner,
                            m.c.fingerprint == new_hash,
                            m.c.id != target,
                        )
                    )
                    if collision:
                        repository._receipt(
                            session, owner, operation, "needs_review", collision, scope
                        )
                        outcomes["needs_review"] = outcomes.get("needs_review", 0) + 1
                        continue  # Never silently merge independently saved records.
                    revision = row["revision"] + 1
                    if item.action == "update" and item.change != "enrichment":
                        archive_evidence(session, owner, target, row["revision"])
                    else:
                        # Keep the current support packet bounded; archived
                        # quotes remain attached to their historical versions.
                        prior = list(
                            session.scalars(
                                select(e.c.id)
                                .where(
                                    e.c.learner_id == owner,
                                    e.c.memory_id == target,
                                    e.c.valid_until_revision.is_(None),
                                )
                                .order_by(e.c.source_date.desc())
                            )
                        )
                        if len(prior) > 4:
                            session.execute(
                                update(e)
                                .where(e.c.learner_id == owner, e.c.id.in_(prior[4:]))
                                .values(valid_until_revision=row["revision"])
                            )
                    if new_hash != row["fingerprint"]:
                        suppress(
                            session,
                            owner,
                            [row["fingerprint"]],
                            source["created_at"],
                            reason="outdated",
                        )
                    session.execute(
                        e.insert().values(
                            id=str(uuid4()),
                            learner_id=owner,
                            memory_id=target,
                            valid_from_revision=revision,
                            **evidence,
                        )
                    )
                    values = dict(
                        content=content,
                        fingerprint=new_hash,
                        revision=revision,
                        source_at=source["created_at"],
                        updated_at=now(),
                        confirmed_at=source["created_at"],
                    )
                    # A protected manual memory retains its retention settings;
                    # pinning is never changed by automatic reconciliation.
                    if row["origin"] == "ai":
                        values["expires_at"] = expiry
                    if item.action == "update":
                        values["category"] = item.category
                    session.execute(
                        update(m)
                        .where(m.c.learner_id == owner, m.c.id == target)
                        .values(**values)
                    )
                    repository._revision(session, owner, target, revision, "ai", row)
                    outcome = "updated" if item.action == "update" else "reaffirmed"
                    repository._receipt(
                        session, owner, operation, outcome, target, scope
                    )
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                if session.info.get("committed_memory_fence"):
                    scope["_memory_summary_fence"] = session.info[
                        "committed_memory_fence"
                    ]
            if foreground_scope is None and not MemoryCaptureRepository(
                TransactionSessions(session)
            ).finish(claim, packet=packet):
                raise SummaryDeferred()
        return outcomes
