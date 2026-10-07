import subprocess
import sys
import unittest
import ast
from pathlib import Path

from pydantic import ValidationError

from app.learner import (
    ConceptResolution,
    ConceptResolutionRequest,
    LearnerContextPacket,
    LearnerService,
)
from app.learner.repositories import ConceptRepository, EvidenceRepository


class LearnerContractTests(unittest.TestCase):
    def test_database_access_stays_in_repositories_and_infrastructure(self):
        app = Path(__file__).resolve().parents[2] / 'app'
        for path in app.rglob('*.py'):
            if 'repositories' in path.parts or 'db' in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                else:
                    continue
                self.assertFalse(any(module.split('.')[0] in {'sqlalchemy', 'psycopg', 'sqlite3'} for module in modules), str(path))

    def test_learner_contract_requires_internal_uuid(self):
        from app.learner import ConceptStateRequest
        from uuid import UUID
        with self.assertRaises(ValidationError):
            ConceptStateRequest(learner_id='external-student-123', concept_id='c')
        identity = UUID('E2BA227D-7165-5D43-91DB-F7185326E0C4')
        self.assertEqual(ConceptStateRequest(learner_id=identity, concept_id='c').learner_id, str(identity))

    def test_public_contracts_are_importable_without_infrastructure(self) -> None:
        self.assertIsNotNone(LearnerService)
        self.assertIsNotNone(ConceptRepository)
        self.assertIsNotNone(EvidenceRepository)
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import app.learner, sys; "
                "assert 'app.db.database' not in sys.modules; "
                "assert 'app.langchain' not in sys.modules; "
                "assert 'langchain_core' not in sys.modules; "
                "assert 'sqlalchemy' not in sys.modules; "
                "assert 'app.auth.service' not in sys.modules",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_concept_resolution_contract_validates_and_serializes(self) -> None:
        request = ConceptResolutionRequest(
            label="transitive dependencies",
            context_id="database-systems",
            learner_id="e2ba227d-7165-5d43-91db-f7185326e0c4",
        )
        response = ConceptResolution(
            status="resolved",
            concept_id="concept-1",
            canonical_name="Transitive Dependency",
            confidence=0.96,
            method="alias",
        )

        self.assertEqual(request.model_dump()["label"], "transitive dependencies")
        self.assertEqual(response.model_dump()["concept_id"], "concept-1")

    def test_confidence_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            ConceptResolution(status="resolved", confidence=1.1)

    def test_learner_context_packet_is_compact_and_serializable(self) -> None:
        packet = LearnerContextPacket.model_validate(
            {
                "active_contexts": ["Database Systems"],
                "concepts": [
                    {
                        "concept_id": "concept-1",
                        "name": "Transitive Dependency",
                        "mastery": 0.34,
                        "estimate_confidence": 0.88,
                        "misconceptions": [
                            "Confuses transitive and partial dependency"
                        ],
                    }
                ],
            }
        )

        self.assertEqual(packet.model_dump()["concepts"][0]["mastery"], 0.34)
