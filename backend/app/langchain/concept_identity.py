"""Bounded model assistance for the learner domain's canonical identity resolver."""
from app.learner.schemas import ConceptSearchTerms, ConceptIdentityMatches
from .prompts import PromptSource


class ConceptIdentityResolver:
    def __init__(self, llm): self.llm = llm

    async def expand(self, labels, topic):
        return await self.llm.ainvoke(PromptSource.CONCEPT_IDENTITY,
            dict(operation='search_terms', labels=labels, topic=topic), output_schema=ConceptSearchTerms)

    async def match(self, labels, candidates, topic):
        return await self.llm.ainvoke(PromptSource.CONCEPT_IDENTITY,
            dict(operation='match', labels=labels, topic=topic,
                 candidates=[dict(id=concept.id, name=concept.canonical_name, description=(concept.description or '')[:300]) for concept in candidates]),
            output_schema=ConceptIdentityMatches)
