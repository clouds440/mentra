"""Validated native controls; persisted in existing assistant message metadata."""
from uuid import UUID, uuid5, NAMESPACE_URL
from app.interactions.schemas import ChoiceContent, selected_options
from app.core.exceptions import AppError


from pydantic import BaseModel, ConfigDict, Field

class ChoiceCard(ChoiceContent):
    id: UUID
    selected: list[str] = Field(default_factory=list)
    submitted_turn_id: UUID | None = None

class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: UUID
    interaction_id: UUID
    selected: list[str] = Field(min_length=1, max_length=10)



def resolve_choice(cards, response):
    card = next((x for x in cards if x['id'] == str(response.interaction_id)), None)
    if not card:
        raise AppError('INTERACTION_NOT_FOUND', 'This interaction is unavailable.', 404)
    value = ChoiceCard.model_validate(card)
    ordered = selected_options(value.options, value.kind, response.selected)
    content = f'{value.question}\nSelected: ' + '; '.join(f'{x.id}: {x.label}' for x in ordered)
    return card, content


def create_interaction_tools(owner, scope, budget):
    from langchain_core.tools import StructuredTool
    async def present(**arguments):
        budget.call(True)
        value = ChoiceContent(**arguments)
        cards = scope.setdefault('interactions', [])
        identifier = uuid5(NAMESPACE_URL, f"choice:{owner}:{scope['current_user_message_id']}:{value.model_dump_json()}")
        card = ChoiceCard(id=identifier, **value.model_dump()).model_dump(mode='json')
        if not any(x['id'] == card['id'] for x in cards):
            if len(cards) >= 3:
                raise AppError('INTERACTION_LIMIT', 'Use at most three interactions per response.', 422)
            cards.append(card)
        return dict(interaction_id=card['id'], outcome='displayed', next_step='Wait for the student selection; do not select on their behalf.')
    return [StructuredTool.from_function(name='present_choices', args_schema=ChoiceContent,
        description='Present native clickable single or multiple selections for clarification, preferences or learning topics. No executable code. Use assessment_generate for quizzes with grading.', coroutine=present)]
