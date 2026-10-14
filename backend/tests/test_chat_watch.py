import asyncio
import unittest
from unittest.mock import Mock, patch
from app.chat.service import ConversationService
from app.core.exceptions import AppError


class WatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failure_does_not_disable_cross_process_stop(self):
        service = ConversationService(Mock())
        generation = asyncio.create_task(asyncio.sleep(30))
        with patch('app.chat.repositories.activity.ActivityRepository') as repository:
            repository.return_value.ensure_active.side_effect = [RuntimeError(), AppError('CHAT_ATTEMPT_EXPIRED', 'Stopped', 409)]
            await service._watch_active('owner', {}, generation)
            self.assertEqual(repository.return_value.ensure_active.call_count, 2)
        await asyncio.gather(generation, return_exceptions=True)
        self.assertTrue(generation.cancelled())

    async def test_sustained_failure_cancels_unmonitored_generation(self):
        service = ConversationService(Mock())
        generation = asyncio.create_task(asyncio.sleep(30))
        with patch('app.chat.repositories.activity.ActivityRepository') as repository:
            repository.return_value.ensure_active.side_effect = RuntimeError()
            await service._watch_active('owner', {}, generation)
            self.assertEqual(repository.return_value.ensure_active.call_count, 3)
        await asyncio.gather(generation, return_exceptions=True)
        self.assertTrue(generation.cancelled())
