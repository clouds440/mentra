"""Private HTTP provider faults and real PostgreSQL admission checks, not unit tests."""
import asyncio
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.admission import Admission
from app.db.database import get_session_factory
from app.langchain.model_factory import ModelFactory


async def main():
    if (urlsplit(settings.database_url).hostname != 'mentra-launchgate-postgres'
            or urlsplit(settings.ai_base_url).hostname != 'mentra-launchgate-provider'):
        raise RuntimeError('Fault drill requires the disposable database and private provider')
    accounts = json.loads(Path('/tmp/launchgate-accounts.json').read_text())
    report = {}
    async with httpx.AsyncClient(base_url=os.environ['TEST_PROVIDER_URL']) as fault, httpx.AsyncClient(base_url=os.environ['TEST_API_URL'], timeout=30) as api:
        model = ModelFactory(settings).get_model()
        for mode in ('rate', 'slow', 'ok'):
            await fault.post('/control', json=dict(mode=mode))
            started = time.perf_counter()
            try:
                await model.ainvoke([HumanMessage(content='Synthetic connectivity check')])
                outcome = 'success'
            except Exception as error:
                outcome = type(error).__name__
            elapsed = round(time.perf_counter()-started, 3)
            assert (outcome == 'success') == (mode == 'ok')
            assert elapsed < 8
            report[mode] = dict(adapter_outcome=outcome, seconds=elapsed)
            if mode != 'ok':
                response = await api.post('/api/v1/conversations/turns', headers=accounts[0]['headers'], json=dict(conversation_id=str(uuid4()), client_turn_id=str(uuid4()), expected_revision=0, content='Hello!'))
                response.raise_for_status()
                assert response.json()['turn']['state'] == 'FAILED'
                assert 'Synthetic quota' not in json.dumps(response.json())
                report[mode]['durable_chat_state'] = 'FAILED'
        # Actual database admission controls under a held asynchronous workload.
        admission = Admission(get_session_factory(), settings=settings.model_copy(update=dict(work_global_capacity=2, work_owner_capacity=1)))
        active = peak = 0

        async def work(number):
            nonlocal active, peak
            try:
                async with admission.async_reserve('model', f'launch-fault-{number}', capacity=2, owner_capacity=1):
                    active += 1
                    peak = max(peak, active)
                    try:
                        await asyncio.sleep(.5)
                    finally:
                        active -= 1
                    return 'admitted'
            except AppError as error:
                assert error.status_code == 429
                return 'bounded-429'

        results = await asyncio.gather(*(work(number) for number in range(8)))
        assert peak <= 2 and 'bounded-429' in results
        report['admission'] = dict(peak=peak, admitted=results.count('admitted'), rejected=results.count('bounded-429'))
        await fault.post('/control', json=dict(mode='ok'))
        response = await api.post('/api/v1/conversations/turns', headers=accounts[0]['headers'], json=dict(conversation_id=str(uuid4()), client_turn_id=str(uuid4()), expected_revision=0, content='Hello!'))
        response.raise_for_status()
        assert response.json()['turn']['state'] == 'SUCCEEDED'
        report['recovery_chat'] = 'SUCCEEDED'
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
