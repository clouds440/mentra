"""Run only in a disposable backend container; never installs on application startup.

Rehearses pinned candidates against Python 3.12 and existing LangChain/provider.
TEST_DATABASE_URL must point at a dedicated disposable PostgreSQL database.
"""
import inspect
import os
import subprocess
import sys
from uuid import uuid4
from typing import TypedDict

CANDIDATES = ('langgraph==0.6.11', 'langgraph-checkpoint==3.0.1',
              'langgraph-checkpoint-postgres==3.0.4', 'langchain-core==0.3.86',
              'langchain-openai==0.3.35')


def main():
    if os.environ.get('MENTRA_DISPOSABLE_REHEARSAL') != '1':
        raise RuntimeError('This script installs dependencies; use a disposable container explicitly.')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *CANDIDATES], check=True)
    from importlib.metadata import version
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.postgres import PostgresSaver
    print('Versions:', {name: version(name) for name in ('langgraph', 'langgraph-checkpoint', 'langgraph-checkpoint-postgres', 'langchain-core', 'langchain-openai')})
    print('Serializer:', inspect.signature(JsonPlusSerializer))
    print('Cleanup:', hasattr(PostgresSaver, 'delete_thread'))
    if 'allowed_msgpack_modules' not in inspect.signature(JsonPlusSerializer).parameters:
        raise RuntimeError('Candidate lacks explicit strict serializer hardening; production pinning remains blocked.')
    # Graph runtime and durable saver rehearsal follow only after hardening is available.
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt, Command
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    class State(TypedDict):
        proposal_id: str
        decision: str
    def decide(state):
        return dict(decision=interrupt(dict(proposal_id=state['proposal_id'])))
    builder = StateGraph(State)
    builder.add_node('decide', decide)
    builder.add_edge(START, 'decide')
    builder.add_edge('decide', END)
    url = os.environ['TEST_DATABASE_URL']
    schema = 'mentra_graph_test_' + uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            def connect():
                return psycopg.connect(url, autocommit=True, row_factory=dict_row, options='-csearch_path='+schema)
            config = dict(configurable=dict(thread_id='owner:'+str(uuid4())))
            with connect() as connection:
                saver = PostgresSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=None))
                saver.setup()
                graph = builder.compile(checkpointer=saver)
                result = graph.invoke(dict(proposal_id=str(uuid4())), config)
                assert '__interrupt__' in result
            with connect() as connection:
                saver = PostgresSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=None))
                graph = builder.compile(checkpointer=saver)
                assert graph.invoke(Command(resume='approve'), config)['decision'] == 'approve'
                saver.delete_thread(config['configurable']['thread_id'])
                for table in ('checkpoints', 'checkpoint_writes', 'checkpoint_blobs'):
                    count = connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()['count']
                    assert count == 0, table
            print('PASS: interrupt/restart/resume and all saver payload tables cleaned')
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    main()
