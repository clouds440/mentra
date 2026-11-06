"""Budget-aware source windows retain original offsets and explicit coverage."""
from hashlib import sha256
from app.core.exceptions import AppError
from app.core.config import settings
from app.learner.signal_schemas import LearningSignalExtraction
from .token_policy import check_input
from .prompts import PromptSource


def capture_windows(llm,job,packet):
    config=getattr(getattr(llm,'model_factory',None),'_settings',settings)
    known=[dict(id=item.concept_id,name=item.name,context_id=item.context_id) for item in packet.concepts[:8]]
    for source in job['sources']:
        offset=0
        while offset<len(source['text']):
            length=min(2000,len(source['text'])-offset)
            while True:
                payload=dict(question_context=job['question'][:1000],question_context_truncated=len(job['question'])>1000,
                    context_ids=packet.context_ids,known_concepts=known,
                    source=dict(id=source['id'],kind=source['kind'],text=source['text'][offset:offset+length],
                        offset=offset,coverage=source.get('coverage','complete')))
                try:
                    check_input(llm.messages(PromptSource.CHAT_EVIDENCE,payload),PromptSource.CHAT_EVIDENCE,
                        tools=[LearningSignalExtraction],config=config)
                    break
                except AppError as error:
                    if error.code!='AI_CONTEXT_LIMIT': raise
                    if length>256:
                        length=max(256,length//2);continue
                    if known:
                        known=[];continue  # Identity can remain unresolved; source is preserved.
                    if payload['question_context']:
                        # Question is context, not student evidence. The current
                        # source is still processed completely across windows.
                        payload['question_context']='';payload['question_context_truncated']=True
                        check_input(llm.messages(PromptSource.CHAT_EVIDENCE,payload),PromptSource.CHAT_EVIDENCE,
                            tools=[LearningSignalExtraction],config=config)
                        break
                    raise
            key=sha256(f"{source['id']}:{source['revision']}:{offset}:{length}".encode()).hexdigest()
            yield key,payload
            if offset+length>=len(source['text']): break
            offset+=max(1,length-100)
