"""Isolated OpenAI HTTP fault fixture. Never register in the production app.

Run only on a private verification network, without a published port.
"""
import asyncio
import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
state = dict(mode='ok', calls=0, active=0, peak=0)


@app.post('/control')
async def control(request: Request):
    mode = (await request.json())['mode']
    if mode not in {'ok', 'rate', 'slow'}:
        return JSONResponse({}, status_code=422)
    state['mode'] = mode
    return state


@app.get('/metrics')
async def metrics():
    return state


@app.post('/v1/chat/completions')
async def completion(request: Request):
    body = await request.json()
    state['calls'] += 1
    state['active'] += 1
    state['peak'] = max(state['peak'], state['active'])
    try:
        if state['mode'] == 'rate':
            return JSONResponse({'error': {'message': 'Synthetic quota', 'type': 'rate_limit_error'}}, status_code=429, headers={'Retry-After': '1'})
        await asyncio.sleep(5 if state['mode'] == 'slow' else .1)
        message = {'role': 'assistant', 'content': 'Synthetic launch validation response.'}
        for tool in body.get('tools', []):
            name = tool['function']['name']
            if name in {'DirectNewChatReply', 'NewChatReply', 'DirectAnswer'}:
                args = dict(content=message['content'], conversation_title='Launch verification', general_query=True, needs_tools=False, uncertain=False)
                fields = tool['function']['parameters'].get('properties', {})
                args = {key: value for key, value in args.items() if key in fields}
                message = dict(role='assistant', content=None, tool_calls=[dict(id='launch-final', type='function', function=dict(name=name, arguments=json.dumps(args)))])
                break
        return dict(id='launch-fixture', object='chat.completion', created=int(time.time()), model=body.get('model', 'launch-fixture'),
                    choices=[dict(index=0, message=message, finish_reason='tool_calls' if 'tool_calls' in message else 'stop')],
                    usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120))
    finally:
        state['active'] -= 1
