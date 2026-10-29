"""Bounded model assistance for the learner domain's canonical identity resolver."""
from app.learner.schemas import ConceptSearchTerms, ConceptIdentityMatches
from .prompts import PromptSource
from app.learner.exceptions import ConceptAssistanceUnavailable
from app.core.logging import workflow_logger


class ConceptIdentityResolver:
    def __init__(self, llm): self.llm = llm

    async def _invoke(self, payload, schema):
        # This is the optional model-advice boundary, never a persistence/write
        # boundary. Cancellation must still propagate to Chat Stop.
        try:
            return await self.llm.ainvoke(PromptSource.CONCEPT_IDENTITY, payload, output_schema=schema)
        except Exception as error:
            workflow_logger.event('concept.assistance_unavailable', error_type=type(error).__name__)
            raise ConceptAssistanceUnavailable('Semantic advice unavailable.') from error

    async def expand(self, labels, topic):
        return await self._invoke(dict(operation='search_terms', labels=labels, topic=topic), ConceptSearchTerms)

    async def match(self, labels, candidates, topic):
        return await self._invoke(
            dict(operation='match', labels=labels, topic=topic,
                 candidates=[dict(id=concept.id, name=concept.canonical_name, description=(concept.description or '')[:300]) for concept in candidates]),
            ConceptIdentityMatches)

    async def organize(self, labels, topic, context, candidates, existing):
        from app.learner.topics import TopicOrganization
        payload = dict(labels=labels, topic=topic, context=context, existing_ungrouped=existing,
                candidates=[dict(id=candidate['id'],name=candidate['name'],scope=candidate['scope'][:300],
                    scope_truncated=len(candidate['scope'])>300,
                    subskills_truncated=candidate.get('subskills_truncated',False),
                    subskills=[dict(concept_id=skill['concept_id'],label=skill['label'],ability=skill['ability'][:160])
                        for skill in candidate['subskills']]) for candidate in candidates])
        # Account for the actual provider envelope, rather than sending an
        # entire registry or failing valid work when candidate descriptions grow.
        if hasattr(self.llm,'messages'):
            from .token_policy import check_input
            from app.core.config import settings
            from app.core.exceptions import AppError
            config=getattr(getattr(self.llm,'model_factory',None),'_settings',settings)
            while True:
                try:
                    check_input(self.llm.messages(PromptSource.TOPIC_ORGANIZATION,payload),
                        PromptSource.TOPIC_ORGANIZATION,tools=[TopicOrganization],config=config)
                    break
                except AppError as error:
                    if error.code!='AI_CONTEXT_LIMIT': raise
                    large=[item for item in payload['candidates'] if len(item['subskills'])>1]
                    if large:
                        for item in large:
                            item['subskills']=item['subskills'][:max(1,len(item['subskills'])//2)]
                            item['subskills_truncated']=True
                    elif len(payload['candidates'])>1:
                        payload['candidates']=payload['candidates'][:max(1,len(payload['candidates'])//2)]
                        payload['candidates_truncated']=True
                    else: raise
        return await self.llm.ainvoke(PromptSource.TOPIC_ORGANIZATION,payload,output_schema=TopicOrganization)
