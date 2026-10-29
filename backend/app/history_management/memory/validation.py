"""Conservative admission: exact owned evidence, then bounded semantic entailment."""
import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal
from pydantic import Field
from pydantic import BaseModel
from app.langchain.prompts import PromptSource


SECRET = re.compile(r'\b(password|api[ _-]?key|secret[ _-]?key|private[ _-]?key|access[ _-]?token|credit card|cvv|social security)\b|sk-[A-Za-z0-9]{12,}|\bBearer\s+\S+|-----BEGIN[^\n]*PRIVATE KEY|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', re.I)
SENSITIVE = re.compile(r'\b(diagnos\w*|disease|medication|pregnan\w*|sexual\w*|religion|religious|political|salary|income|bank|address|phone number|trauma|depress\w*|health)\b', re.I)
CONSENT = re.compile(r'\b(remember|save (?:this|that)|store (?:this|that)|keep (?:this|that) in mind)\b', re.I)


class Admission(BaseModel):
    supported: bool
    explicit_user_statement: bool
    sensitive: bool
    explicit_remember_request: bool
    durable: bool
    contradicts_existing: bool
    profile_field: bool = False
    credential: bool = False
    consent_quote: str = Field(default='', max_length=500)
    valid_until: datetime | None = None
    conflicting_memory_ids: list[UUID] = Field(default_factory=list, max_length=5)


class RevisionAdmission(Admission):
    same_fact: bool = False
    change: Literal['enrichment','correction','change_over_time'] | None = None
    explicit_correction: bool = False


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class MemoryValidator:
    def __init__(self, llm):
        self.llm = llm

    async def validate(self, content, quote, message, existing=(), source_date=None, revision_target_id=None):
        if SECRET.search(content) or SECRET.search(quote):
            return dict(outcome='rejected', reason='Credentials and secrets cannot be saved.')
        if quote not in message:
            return dict(outcome='rejected', reason='Evidence must be an exact span of the user message.')
        try:
            import asyncio
            context = message[:4000]
            if quote not in context:
                start = message.index(quote)
                context = message[:500] + '\n[Source excerpt]\n' + message[max(0, start-500):start+2500]
            result = await asyncio.wait_for(self.llm.ainvoke(PromptSource.MEMORY_VALIDATION,
                dict(claim=content, evidence_quote=quote, user_message=context, existing=list(existing),
                    revision_target_id=revision_target_id,
                    source_date=(source_date or datetime.now(timezone.utc)).isoformat()),
                output_schema=RevisionAdmission), timeout=12)
        except Exception:
            # Do not persist a possibly sensitive candidate when validation fails.
            return dict(outcome='unavailable', reason='Memory validation was unavailable; nothing was saved.')
        decision=self.admit(content, quote, message, existing, result)
        if decision['outcome'] in ('active','pending','conflict'):decision['admission']=result.model_dump(mode='json')
        return decision

    @staticmethod
    def admit(content, quote, message, existing, result):
        if SECRET.search(content) or SECRET.search(quote) or quote not in message:
            return dict(outcome='rejected', reason='Memory requires safe exact user evidence.')
        sensitive = result.sensitive or bool(SENSITIVE.search(content + ' ' + quote))
        if result.credential:
            return dict(outcome='rejected', reason='Credentials and secrets cannot be saved.')
        consent = result.explicit_remember_request and (bool(CONSENT.search(message)) or bool(result.consent_quote and result.consent_quote in message and result.explicit_user_statement))
        if sensitive and not consent:
            return dict(outcome='rejected', reason='Sensitive information requires an explicit request to remember it.')
        if not result.supported or not result.durable or result.profile_field:
            return dict(outcome='rejected', reason='No supported durable personal information was found.')
        status = 'conflict' if result.contradicts_existing else 'active' if result.explicit_user_statement else 'pending'
        known = {str(x['id']) for x in existing}
        conflict_ids = [str(x) for x in result.conflicting_memory_ids if str(x) in known]
        if status == 'conflict' and not conflict_ids:
            return dict(outcome='unavailable', reason='The conflicting memory could not be identified. Review saved memories before storing a correction.')
        valid_until = result.valid_until if result.valid_until and result.valid_until.tzinfo else None
        return dict(outcome=status, explicit_consent=consent, valid_until=valid_until, conflict_ids=conflict_ids)
