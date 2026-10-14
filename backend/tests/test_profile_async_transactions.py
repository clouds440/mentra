import asyncio
import threading
import time
import unittest
from unittest.mock import Mock

from app.student_profile.evidence_service import ProfileEvidenceService
from app.student_profile.calibration.service import CalibrationService


class ProfileAsyncTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluation_claim_does_not_block_event_loop(self):
        service = ProfileEvidenceService(Mock(), Mock())
        loop_thread = threading.get_ident()
        threads = []
        profile = object()

        def claim(*args):
            threads.append(threading.get_ident())
            time.sleep(.15)
            return profile, None

        service._claim = claim
        task = asyncio.create_task(service.evaluate('owner', 'evidence'))
        await asyncio.sleep(.03)
        self.assertFalse(task.done())
        self.assertIs(await task, profile)
        self.assertNotEqual(threads[0], loop_thread)

    async def test_completion_offloads_entire_transaction_before_evaluation(self):
        evidence = Mock(id='evidence', status='applied')
        profile = object()
        service = CalibrationService(Mock(), Mock())
        threads = []

        def complete(*args):
            threads.append(threading.get_ident())
            time.sleep(.15)
            return profile, evidence

        service._complete_transaction = complete
        from unittest.mock import patch
        with patch('app.student_profile.calibration.service.CalibrationResult', side_effect=lambda **kw: kw):
            task = asyncio.create_task(service.complete('owner', 'attempt', Mock()))
            await asyncio.sleep(.03)
            self.assertFalse(task.done())
            result = await task
        self.assertIs(result['profile'], profile)
        self.assertNotEqual(threads[0], threading.get_ident())
