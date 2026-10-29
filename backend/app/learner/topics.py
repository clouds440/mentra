"""Broad learning topics group existing canonical skills without copying evidence."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .schemas import LearnerSchema, LearnerContextConcept


class TopicPlacement(LearnerSchema):
    label: str = Field(min_length=1, max_length=200)
    skill_name: str | None = Field(default=None, min_length=1, max_length=200)
    skill_id: str | None = None
    topic_id: str | None = None
    topic_name: str = Field(default='', max_length=200)
    scope: str = Field(default='', max_length=1000)
    ability: str = Field(default='', max_length=1000)
    action: Literal['reuse', 'add_subskill', 'create_concept', 'defer']

    @model_validator(mode='after')
    def references(self):
        if self.action == 'reuse' and (not self.skill_id or not self.topic_id):
            raise ValueError('Reuse requires an existing skill and topic')
        if self.action == 'add_subskill' and not self.topic_id:
            raise ValueError('An additional subskill needs an existing topic')
        if self.action == 'create_concept' and (self.topic_id or self.skill_id):
            raise ValueError('New topics cannot choose canonical IDs')
        if self.action=='create_concept' and (not self.topic_name.strip() or not self.scope.strip()):
            raise ValueError('A new topic needs a name and scope')
        if self.action in ('create_concept','add_subskill') and not self.ability.strip():
            raise ValueError('A new placement needs an assessable ability')
        return self


class TopicOrganization(LearnerSchema):
    placements: list[TopicPlacement] = Field(max_length=20)
    needs_wider_lookup: bool = False
    search_terms: list[Annotated[str,Field(min_length=1,max_length=200)]] = Field(default_factory=list, max_length=6)


class LearningTopic(LearnerSchema):
    id: str
    name: str
    scope: str
    context_id: str | None = None
    subskill_count: int = 0
    checked_count: int = 0
    matching_skills: list[str] = Field(default_factory=list)
    revision: int = 1


class TopicPage(LearnerSchema):
    items: list[LearningTopic]
    total: int
    ungrouped_count: int = 0
    limit: int
    offset: int
    generated_at: datetime


class TopicSubskill(LearnerContextConcept):
    ability: str | None = None


class TopicSkillsPage(LearnerSchema):
    topic: LearningTopic
    items: list[TopicSubskill]
    total: int
    limit: int
    offset: int
    generated_at: datetime
