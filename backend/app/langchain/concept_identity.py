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
        return await self.llm.ainvoke(PromptSource.TOPIC_ORGANIZATION,
            dict(labels=labels, topic=topic, context=context, existing_ungrouped=existing,
                candidates=[{key: value for key, value in candidate.items()
                    if key in ('id', 'name', 'scope', 'subskills')} for candidate in candidates]),
            output_schema=TopicOrganization)
