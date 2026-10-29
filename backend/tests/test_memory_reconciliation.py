"""Real PostgreSQL checks for evidence, atomic capture, chronology and forgetting."""

import asyncio
import unittest
from uuid import uuid4

from app.auth.repositories.tables import learner
from app.chat.repositories.postgres import ChatRepository
from app.chat.schemas import SendTurn
from app.core.exceptions import AppError
from app.history_management.memory.capture import AutomaticMemories
from app.history_management.memory.capture_schemas import CapturedMemory, MemoryCapture
from app.history_management.memory.semantic import MemorySemanticLookup
from app.history_management.memory.validation import Admission
from app.history_management.repositories.memory_capture import MemoryCaptureRepository
from app.history_management.repositories.memory_reconciliation import MemoryReconciler
from app.history_management.repositories.memory_summaries import MemorySummaryRepository
from app.history_management.repositories.postgres import (
    MemoryRepository,
    fingerprint,
    now,
)
from app.history_management.repositories.tables import (
    capture_jobs as j,
)
from app.history_management.repositories.tables import (
    evidence as e,
)
from app.history_management.repositories.tables import (
    memory_vectors as v,
)
from app.history_management.repositories.tables import (
    revisions as r,
)
from app.history_management.repositories.tables import (
    suppression as s,
)
from app.history_management.schemas import MemoryEdit, MemoryRestore, PreferencesEdit
from app.langchain.llm import MentraLLM
from app.summarization.execution import SummaryDeferred
from sqlalchemy import func, select, update
from testing.postgres import PostgresSandbox


def admission(**changes):
    return Admission(
        **dict(
            supported=True,
            explicit_user_statement=True,
            sensitive=False,
            explicit_remember_request=False,
            durable=True,
            contradicts_existing=False,
            **changes,
        )
    )


class MemoryReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.owner = str(uuid4())
        self.other = str(uuid4())
        with self.db.sessions.begin() as session:
            session.execute(
                learner.insert(), [dict(id=self.owner), dict(id=self.other)]
            )
        self.repo = MemoryRepository(self.db.sessions)
        self.jobs = MemoryCaptureRepository(self.db.sessions)
        self.chat = ChatRepository(self.db.sessions)
        self.summaries = MemorySummaryRepository(self.db.sessions)

    def tearDown(self):
        with self.db.sessions.begin() as session:
            session.execute(
                update(j)
                .where(j.c.learner_id == self.owner)
                .values(completed_at=now(), lease_token=None, lease_until=None)
            )

    def memory(self, content="My current phone is an iPhone.", **values):
        return self.repo.write(
            self.owner,
            content,
            "fact",
            str(uuid4()),
            origin=values.pop("origin", "ai"),
            **values,
        )["memory"]

    def source(self, text="I replaced my iPhone with a Pixel."):
        job = self.chat.begin_turn(
            self.owner,
            SendTurn(
                conversation_id=uuid4(),
                client_turn_id=uuid4(),
                expected_revision=0,
                content=text,
            ),
        )
        self.chat.finish(self.owner, job, dict(content="Understood."))
        claim = self.jobs.claim()
        self.assertEqual(claim["learner_id"], self.owner)
        return claim, self.jobs.packet(claim)

    def item(self, packet, target=None, **changes):
        values = dict(
            content="My current phone is a Pixel.",
            category="fact",
            evidence_quote=packet["text"],
            admission=admission(),
        )
        if target:
            values.update(
                action="update",
                target_memory_id=target["id"],
                expected_revision=target["revision"],
                same_fact=True,
                change="change_over_time",
            )
        values.update(changes)
        return CapturedMemory(**values)

    def apply(self, claim, packet, items, existing=(), fence=None):
        return MemoryReconciler(self.repo).apply(
            self.owner,
            claim,
            packet,
            items,
            list(existing),
            fence or self.summaries.context(self.owner)[1],
        )

    def test_stable_id_history_support_and_summary_replacement(self):
        old = self.memory()
        claim, packet = self.source()
        result = self.apply(claim, packet, [self.item(packet, old)], [old])
        self.assertEqual(result, dict(updated=1))
        current = self.repo.detail(self.owner, old["id"])
        self.assertEqual(
            (current["revision"], current["content"]),
            (2, "My current phone is a Pixel."),
        )
        self.assertEqual(
            [value["quote"] for value in current["evidence"]], [packet["text"]]
        )
        history = self.repo.revision_page(self.owner, old["id"])["items"]
        self.assertEqual(
            [value["snapshot"]["content"] for value in history],
            [current["content"], old["content"]],
        )
        self.assertEqual(history[1]["evidence"][0]["quote"], old["content"])
        context = self.summaries.context(self.owner)[0]["content"]
        self.assertIn("Pixel", context)
        self.assertNotIn("iPhone", context)
        with self.db.sessions() as session:
            self.assertIsNotNone(
                session.scalar(
                    select(j.c.completed_at).where(
                        j.c.message_id == claim["message_id"]
                    )
                )
            )

    def test_enrichment_and_reaffirm_preserve_relevant_support(self):
        old = self.memory()
        claim, packet = self.source("My iPhone is a 17 Pro.")
        self.apply(
            claim,
            packet,
            [
                self.item(
                    packet,
                    old,
                    content="My current phone is an iPhone 17 Pro.",
                    change="enrichment",
                )
            ],
            [old],
        )
        new = self.repo.detail(self.owner, old["id"])
        self.assertEqual(len(new["evidence"]), 2)
        claim, packet = self.source("I still use the iPhone 17 Pro.")
        self.apply(
            claim,
            packet,
            [
                self.item(
                    packet, new, content=new["content"], action="reaffirm", change=None
                )
            ],
            [new],
        )
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 3)
        self.assertEqual(len(self.repo.list(self.owner)["items"]), 1)

    def test_additional_fact_in_same_topic_is_separate(self):
        old = self.memory()
        claim, packet = self.source("I also use a Pixel for work.")
        self.apply(
            claim, packet, [self.item(packet, content="I use a Pixel for work.")], [old]
        )
        self.assertEqual(len(self.repo.list(self.owner)["items"]), 2)
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 1)

    def test_manual_memory_requires_explicit_correction_and_pinning_keeps_origin(self):
        old = self.memory(origin="manual")
        claim, packet = self.source("I am thinking about a Pixel.")
        self.apply(claim, packet, [self.item(packet, old)], [old])
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 1)
        self.assertEqual(len(self.repo.list(self.owner, status="conflict")["items"]), 1)
        claim, packet = self.source(
            "Actually, correct my saved phone: I replaced it with a Samsung."
        )
        self.apply(
            claim,
            packet,
            [
                self.item(
                    packet,
                    old,
                    content="My current phone is a Samsung.",
                    explicit_correction=True,
                )
            ],
            [old],
        )
        self.assertEqual(
            self.repo.detail(self.owner, old["id"])["content"],
            "My current phone is a Samsung.",
        )
        ai = self.memory("I study Arabic every evening.")
        pinned = self.repo.edit(
            self.owner, ai["id"], MemoryEdit(expected_revision=1, pinned=True)
        )
        self.assertEqual(pinned["origin"], "ai")
        claim, packet = self.source("I now study Arabic in the morning.")
        self.apply(
            claim,
            packet,
            [self.item(packet, pinned, content="I study Arabic in the morning.")],
            [pinned],
        )
        self.assertTrue(self.repo.detail(self.owner, ai["id"])["pinned"])

    def test_older_source_cannot_overwrite_newer_fact(self):
        claim, packet = self.source()
        old = self.memory()
        self.apply(claim, packet, [self.item(packet, old)], [old])
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 1)

    def test_newer_genuine_reversal_allowed_but_forgetting_blocks_all_versions(self):
        old = self.memory()
        claim, packet = self.source()
        self.apply(claim, packet, [self.item(packet, old)], [old])
        new = self.repo.detail(self.owner, old["id"])
        claim, packet = self.source("I switched back to an iPhone.")
        self.apply(
            claim, packet, [self.item(packet, new, content=old["content"])], [new]
        )
        current = self.repo.detail(self.owner, old["id"])
        self.assertEqual(current["content"], old["content"])
        self.repo.remove(self.owner, old["id"], current["revision"])
        claim, packet = self.source("My current phone is a Pixel.")
        self.apply(claim, packet, [self.item(packet, content=packet["text"])])
        self.assertEqual(self.repo.list(self.owner)["items"], [])
        with self.db.sessions() as session:
            for table in (r, e, v):
                self.assertEqual(
                    session.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(table.c.memory_id == old["id"])
                    ),
                    0,
                )
            self.assertEqual(
                session.scalar(
                    select(s.c.reason).where(
                        s.c.learner_id == self.owner,
                        s.c.fingerprint == fingerprint("My current phone is a Pixel."),
                    )
                ),
                "forgotten",
            )

    def test_plan_failure_rolls_back_all_items_and_cursor(self):
        claim, packet = self.source("I use a Pixel and study Arabic.")
        valid = self.item(packet)
        invalid = self.item(packet, dict(id=str(uuid4()), revision=1))
        with self.assertRaises(AppError):
            self.apply(claim, packet, [valid, invalid])
        self.assertEqual(self.repo.list(self.owner)["items"], [])
        with self.db.sessions() as session:
            self.assertIsNone(
                session.scalar(
                    select(j.c.completed_at).where(
                        j.c.message_id == claim["message_id"]
                    )
                )
            )

    def test_edited_candidate_or_changed_summary_defers_entire_plan(self):
        old = self.memory()
        claim, packet = self.source()
        fence = self.summaries.context(self.owner)[1]
        self.repo.edit(
            self.owner,
            old["id"],
            MemoryEdit(expected_revision=1, content="I use a Nokia."),
        )
        with self.assertRaises(SummaryDeferred):
            self.apply(claim, packet, [self.item(packet, old)], [old], fence)
        self.assertEqual(
            self.repo.detail(self.owner, old["id"])["content"], "I use a Nokia."
        )

    def test_opt_out_and_deleted_chat_cancel_capture(self):
        claim, packet = self.source()
        prefs = self.repo.preferences(self.owner)
        self.repo.set_preferences(
            self.owner,
            PreferencesEdit(
                automatic_memory=False, expected_revision=prefs["revision"]
            ),
        )
        with self.assertRaises(AppError):
            self.apply(claim, packet, [self.item(packet)])
        self.assertEqual(self.repo.list(self.owner)["items"], [])

    def test_private_or_inferred_updates_never_persist(self):
        old = self.memory()
        claim, packet = self.source("Maybe my current phone is a Pixel.")
        inferred = admission()
        inferred.explicit_user_statement = False
        inferred.contradicts_existing = True
        self.apply(claim, packet, [self.item(packet, old, admission=inferred)], [old])
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 1)
        claim, packet = self.source("My salary is 1000.")
        sensitive = admission()
        sensitive.sensitive = True
        self.apply(
            claim,
            packet,
            [self.item(packet, content=packet["text"], admission=sensitive)],
        )
        self.assertEqual(len(self.repo.list(self.owner)["items"]), 1)

    def test_restore_is_new_manual_version_owner_scoped_and_fenced(self):
        old = self.memory()
        self.repo.edit(
            self.owner,
            old["id"],
            MemoryEdit(expected_revision=1, content="I use a Nokia."),
        )
        with self.assertRaises(AppError):
            self.repo.revision_page(self.other, old["id"])
        with self.assertRaises(AppError):
            self.repo.restore_revision(
                self.owner,
                old["id"],
                MemoryRestore(expected_revision=1, restore_revision=1),
            )
        restored = self.repo.restore_revision(
            self.owner,
            old["id"],
            MemoryRestore(expected_revision=2, restore_revision=1),
        )
        self.assertEqual(
            (restored["revision"], restored["content"], restored["origin"]),
            (3, old["content"], "manual"),
        )
        self.assertEqual(
            self.repo.revision_page(self.owner, old["id"], limit=1)["next_before"], 3
        )
        self.assertEqual(
            self.repo.revision_page(self.owner, old["id"], before=3)["items"][0][
                "revision"
            ],
            2,
        )

    def test_worker_uses_single_combined_model_call_and_finishes_atomically(self):
        old = self.memory()
        job = self.chat.begin_turn(
            self.owner,
            SendTurn(
                conversation_id=uuid4(),
                client_turn_id=uuid4(),
                expected_revision=0,
                content="I replaced my iPhone with a Pixel.",
            ),
        )
        self.chat.finish(self.owner, job, dict(content="Okay."))
        parent = self

        class Model:
            messages = MentraLLM.messages
            calls = 0

            async def ainvoke(self, source, payload, **kwargs):
                self.calls += 1
                parent.assertEqual(payload["existing"][0]["id"], old["id"])
                return MemoryCapture(
                    items=[
                        CapturedMemory(
                            content="My current phone is a Pixel.",
                            category="fact",
                            evidence_quote=payload["user_message"],
                            admission=admission(),
                            action="update",
                            target_memory_id=old["id"],
                            expected_revision=1,
                            same_fact=True,
                            change="change_over_time",
                        )
                    ]
                )

        model = Model()
        worker = AutomaticMemories(self.db.sessions, model)
        self.assertTrue(asyncio.run(worker.run_once()))
        self.assertEqual(model.calls, 1)
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 2)
        self.assertFalse(asyncio.run(worker.run_once()))
        worker.close()

    def test_semantic_lookup_revision_fence_owner_isolation_and_delete(self):
        first = self.memory()
        self.memory("I study music.")
        self.repo.write(self.other, "Other phone", "fact", str(uuid4()))
        lookup = MemorySemanticLookup(self.db.sessions, FakeEmbedding())
        rows, ready = lookup.related(self.owner, "هاتف جديد")
        self.assertTrue(ready)
        self.assertEqual(rows[0]["id"], first["id"])
        self.assertEqual(len(rows), 2)
        self.repo.edit(
            self.owner,
            first["id"],
            MemoryEdit(expected_revision=1, content="I study painting."),
        )
        lookup.related(self.owner, "painting")
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(
                    select(v.c.revision).where(v.c.memory_id == first["id"])
                ),
                2,
            )
        self.repo.remove(self.owner, first["id"], 2)
        rows, _ = lookup.related(self.owner, "phone")
        self.assertNotIn(first["id"], [row["id"] for row in rows])
        with self.db.sessions() as session:
            self.assertIsNone(
                session.scalar(
                    select(v.c.memory_id).where(v.c.memory_id == first["id"])
                )
            )

    def test_foreground_revise_uses_same_atomic_reconciliation(self):
        from app.chat.repositories.history_reader import ChatReadFacade
        from app.history_management.budgets import ToolBudget
        from app.history_management.memory.validation import (
            MemoryValidator,
            RevisionAdmission,
        )
        from app.history_management.schemas import MemoryToolInput
        from app.history_management.service import HistoryManagement

        old = self.memory()
        job = self.chat.begin_turn(
            self.owner,
            SendTurn(
                conversation_id=uuid4(),
                client_turn_id=uuid4(),
                expected_revision=0,
                content="I replaced my iPhone with a Pixel.",
            ),
        )
        row = self.chat.context_rows(
            self.owner, job["conversation_id"], job["user_sequence"]
        )[-1]
        scope = dict(
            job,
            evidence_ids={row["id"]},
            memory_references=[],
            _memory_summary_fence=self.summaries.context(self.owner)[1],
        )

        class Verifier:
            async def ainvoke(self, *args, **kwargs):
                return RevisionAdmission(
                    **admission().model_dump(),
                    same_fact=True,
                    change="change_over_time",
                    explicit_correction=True,
                )

        service = HistoryManagement(
            self.repo, ChatReadFacade(self.chat), MemoryValidator(Verifier())
        )
        body = MemoryToolInput(
            action="revise",
            content="My current phone is a Pixel.",
            category="fact",
            evidence_message_id=row["id"],
            evidence_quote=row["content"],
            memory_id=old["id"],
            expected_revision=1,
        )
        budget=ToolBudget()
        result = asyncio.run(service.memory(self.owner, scope, body, budget))
        import json
        json.dumps(budget.cache)  # Recovery checkpoints must remain serializable.
        self.assertEqual(result["outcome"], "updated")
        self.assertEqual(
            (result["memory"]["id"], result["memory"]["revision"]), (old["id"], 2)
        )
        self.assertTrue(
            self.summaries.fence_current(self.owner, scope["_memory_summary_fence"])
        )
        again = asyncio.run(service.memory(self.owner, scope, body, ToolBudget()))
        self.assertEqual(again["outcome"], "updated")
        self.assertEqual(self.repo.detail(self.owner, old["id"])["revision"], 2)
        self.chat.finish(self.owner, job, dict(content="Updated."))

    def test_multiple_updates_share_fence_and_current_support_is_bounded(self):
        first = self.memory()
        second = self.memory("I study Arabic in the evening.")
        claim, packet = self.source("I use a Pixel now. I study Arabic in the morning.")
        result = self.apply(
            claim,
            packet,
            [
                self.item(packet, first),
                self.item(packet, second, content="I study Arabic in the morning."),
            ],
            [first, second],
        )
        self.assertEqual(result, dict(updated=2))
        first = self.repo.detail(self.owner, first["id"])
        for _ in range(6):
            claim, packet = self.source("I still use a Pixel.")
            self.apply(
                claim,
                packet,
                [
                    self.item(
                        packet,
                        first,
                        action="reaffirm",
                        change=None,
                        content=first["content"],
                    )
                ],
                [first],
            )
            first = self.repo.detail(self.owner, first["id"])
        self.assertEqual(len(first["evidence"]), 5)
        history = self.repo.revision_page(self.owner, first["id"])["items"]
        self.assertEqual(
            history[-1]["snapshot"]["content"], "My current phone is an iPhone."
        )

    def test_semantic_backfill_is_bounded_and_outage_defers(self):
        for index in range(35):
            self.memory(f"I study subject {index}.")
        lookup = MemorySemanticLookup(self.db.sessions, FakeEmbedding())
        _, ready = lookup.related(self.owner, "music")
        self.assertFalse(ready)
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(v)
                    .where(v.c.learner_id == self.owner)
                ),
                32,
            )
        rows, ready = lookup.related(self.owner, "music")
        self.assertTrue(ready)
        self.assertEqual(len(rows), 8)

        class Broken(FakeEmbedding):
            def embed_similarity(self, texts):
                raise RuntimeError("Synthetic outage")

        lookup = MemorySemanticLookup(self.db.sessions, Broken())
        _, ready = lookup.related(self.owner, "music")
        self.assertFalse(ready)
        _, ready = lookup.related(self.owner, "music")
        self.assertFalse(ready)

    def test_deleted_source_and_expired_lease_leave_no_memory(self):
        claim, packet = self.source()
        revision = self.chat.status(self.owner, claim["conversation_id"])[
            "conversation"
        ]["revision"]
        self.chat.edit(self.owner, claim["conversation_id"], revision, remove=True)
        with self.assertRaises(AppError):
            self.apply(claim, packet, [self.item(packet)])
        self.assertEqual(self.repo.list(self.owner)["items"], [])
        claim, packet = self.source()
        from datetime import timedelta

        with self.db.sessions.begin() as session:
            session.execute(
                update(j)
                .where(j.c.message_id == claim["message_id"])
                .values(lease_until=now() - timedelta(seconds=1))
            )
        with self.assertRaises(AppError):
            self.apply(claim, packet, [self.item(packet)])
        self.assertEqual(self.repo.list(self.owner)["items"], [])


class FakeEmbedding:
    model_name = "synthetic"
    model_version = "v1"
    dimension = 3

    def embed_similarity(self, texts):
        return [
            [1.0, 0.0, 0.0] if "phone" in text or "هاتف" in text else [0.0, 1.0, 0.0]
            for text in texts
        ]
