"""Reproducible indexed retrieval measurement using synthetic isolated histories."""
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import event, text
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from app.chat.repositories.tables import conversations, messages
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.history_reader import ChatReadFacade
from app.history_management.repositories.postgres import MemoryRepository, fingerprint
from app.history_management.repositories.tables import memories
from app.history_management.schemas import HistoryLookup


def main():
    with PostgresSandbox() as db:
        owner, stamp = learner_id('alice'), datetime.now(timezone.utc)
        rows, chats = [], []
        needle = 'retrievalneedle'+uuid4().hex[:8]
        for chat in range(200):
            cid = str(uuid4())
            chats.append(dict(id=cid, learner_id=owner, title=f'Synthetic chat {chat}', selection={}, revision=1,
                message_count=50, created_at=stamp, updated_at=stamp))
            for sequence in range(1,51):
                rows.append(dict(id=str(uuid4()), learner_id=owner, conversation_id=cid, sequence=sequence,
                    role='user' if sequence % 2 else 'assistant', content=f'Synthetic exchange about graphs and Python {chat} {sequence}' + (' '+needle if chat == 100 and sequence == 25 else ''), metadata={}, created_at=stamp))
        facts = []
        for index in range(500):
            content = f'Synthetic preference topic{index}'
            facts.append(dict(id=str(uuid4()), learner_id=owner, content=content, fingerprint=fingerprint(content),
                category='preference', status='active', origin='manual', revision=1, conflicts=[], pinned=False,
                created_at=stamp, updated_at=stamp, confirmed_at=stamp))
        with db.engine.begin() as connection:
            connection.execute(conversations.insert(), chats)
            connection.execute(messages.insert(), rows)
            connection.execute(memories.insert(), facts)
            connection.execute(text('ANALYZE chat_message'))
            connection.execute(text('ANALYZE hm_memory'))
        # Simulate the steady state after autovacuum has flushed the bulk
        # fixture's GIN pending lists; otherwise insertion cost skews plans.
        with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql('VACUUM ANALYZE chat_message')
            connection.exec_driver_sql('VACUUM ANALYZE hm_memory')
        queries = []
        def count(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith('SELECT'):
                queries.append(statement)
        event.listen(db.engine, 'before_cursor_execute', count)
        reader = ChatReadFacade(ChatRepository(db.sessions))
        body = HistoryLookup(scope='all_chats', query=needle)
        timings = []
        counts = []
        for _ in range(20):
            start, before = time.perf_counter(), len(queries)
            windows = reader.lookup(owner, chats[0]['id'], 51, body)
            timings.append((time.perf_counter()-start)*1000)
            counts.append(len(queries)-before)
            assert windows and len(windows) <= 3
            assert sum(len(x['messages']) for x in windows) <= 9
        event.remove(db.engine, 'before_cursor_execute', count)
        memory = MemoryRepository(db.sessions)
        recalled = memory.list(owner, 'topic123', recall=True, limit=5)
        assert len(recalled['items']) == 1
        with db.engine.connect() as connection:
            plan = connection.execute(text("EXPLAIN (ANALYZE, FORMAT JSON) SELECT id FROM chat_message WHERE learner_id=:owner AND to_tsvector('simple',content) @@ websearch_to_tsquery('simple',:query) LIMIT 3"), dict(owner=owner,query=needle)).scalar()[0]
        names = []
        def indexes(node):
            if node.get('Index Name'): names.append(node['Index Name'])
            for child in node.get('Plans', []): indexes(child)
        indexes(plan['Plan'])
        assert 'idx_chat_history_fts' in names, names
        report = dict(synthetic_messages=len(rows), synthetic_conversations=len(chats), synthetic_memories=len(facts),
            history_query_count_min=min(counts), history_query_count_max=max(counts),
            cold_ms=round(timings[0],2), warm_median_ms=round(statistics.median(timings[1:]),2),
            p95_ms=round(sorted(timings)[18],2), selected_indexes=names,
            max_windows=3, max_expanded_messages=9, memory_recall_limit=5,
            note='Local dedicated PostgreSQL 17 fixture; latency is not a production SLO.')
        Path('docs/history-performance-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
