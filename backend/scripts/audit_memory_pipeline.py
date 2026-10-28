"""Read-only diagnostics for memory capture and summary coverage; no content dump."""
import json
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import settings

engine = create_engine(make_url(settings.database_url).set(drivername='postgresql+psycopg'))
queries = {
 'memories': 'select learner_id,status,origin,category,count(*) from hm_memory group by learner_id,status,origin,category',
 'preferences': 'select learner_id,automatic_memory,revision from hm_preferences',
 'receipts': 'select outcome,count(*) from hm_tool_receipt group by outcome',
 'conversations': 'select learner_id,count(*),sum(message_count) from chat_conversation where deleted_at is null group by learner_id',
 'memory_summaries': 'select learner_id,source_revision,published_source_revision,summary_revision,prompt_version,jsonb_array_length(blocks) blocks from hm_memory_summary_state',
 'memory_jobs': 'select learner_id,attempts,failed,error_code,queued_at,lease_until from hm_memory_summary_job',
 'chat_summaries': 'select learner_id,conversation_id,through_sequence,revision,length(content) characters from chat_summary',
 'chat_jobs': 'select learner_id,conversation_id,target_sequence,attempts,failed,error_code,queued_at from chat_summary_job',
}
with engine.connect() as connection:
    connection.execute(text('SET TRANSACTION READ ONLY'))
    for name, query in queries.items():
        print(name + ': ' + json.dumps([dict(row) for row in connection.execute(text(query)).mappings()], default=str))
