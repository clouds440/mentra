"""Validated native controls persisted through the existing durable chat turn."""
from typing import Annotated, Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import BaseModel, ConfigDict, Field, model_validator, TypeAdapter

from app.interactions.schemas import ChoiceContent, ChoiceOption, selected_options
from app.core.exceptions import AppError


class TextInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['short_text', 'long_text'] = 'short_text'
    label: str = Field(min_length=1, max_length=120)
    placeholder: str = Field(default='', max_length=160)
    required: bool = True
    max_length: int = Field(default=300, ge=1, le=1000)


class ChatChoiceOption(ChoiceOption):
    input: TextInput | None = None


class ChatChoiceContent(ChoiceContent):
    options: list[ChatChoiceOption] = Field(min_length=2, max_length=10)

    @model_validator(mode='after')
    def answer_fits_turn(self):
        lengths = [len(x.id) + len(x.label) + 4 + (len(x.input.label) + x.input.max_length + 5 if x.input else 0) for x in self.options]
        maximum = sum(lengths) if self.kind == 'multiple_choice' else max(lengths)
        if len(self.question) + maximum + 12 > 4000:
            raise ValueError('Shorten the choices or attached inputs to fit a conversation response.')
        return self


class ChoiceCard(ChatChoiceContent):
    id: UUID
    selected: list[str] = Field(default_factory=list)
    option_inputs: dict[str, str] = Field(default_factory=dict)
    submitted_turn_id: UUID | None = None


class InputField(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    kind: Literal['short_text', 'long_text', 'number', 'select'] = 'short_text'
    label: str = Field(min_length=1, max_length=120)
    placeholder: str = Field(default='', max_length=160)
    required: bool = True
    max_length: int = Field(default=300, ge=1, le=1000)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    options: list[ChoiceOption] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def valid_field(self):
        if self.kind == 'select' and (not self.options or len({x.id for x in self.options}) != len(self.options)):
            raise ValueError('Select fields require unique options.')
        if self.kind == 'select' and any(len(x.id) > self.max_length for x in self.options):
            raise ValueError('Select option identifiers must fit the field length.')
        if self.kind != 'select' and self.options:
            raise ValueError('Only select fields accept options.')
        if self.kind != 'number' and (self.minimum is not None or self.maximum is not None):
            raise ValueError('Only number fields accept numeric bounds.')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('Invalid number bounds.')
        return self


class InputContent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['text_input', 'form']
    question: str = Field(min_length=1, max_length=1000)
    fields: list[InputField] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def valid_fields(self):
        if len({x.id for x in self.fields}) != len(self.fields):
            raise ValueError('Field identifiers must be unique.')
        if self.kind == 'text_input' and (len(self.fields) != 1 or self.fields[0].kind not in ('short_text', 'long_text')):
            raise ValueError('Text input requires exactly one text field.')
        if len(self.question) + sum(len(x.label) + max(x.max_length, max((len(option.label) for option in x.options), default=0)) + 5 for x in self.fields) > 4000:
            raise ValueError('Shorten this form to fit a conversation response.')
        return self


class InputCard(InputContent):
    id: UUID
    values: dict[str, str] = Field(default_factory=dict)
    submitted_turn_id: UUID | None = None


class ValueBar(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=120)
    value: float = Field(ge=0, allow_inf_nan=False)
    max: float = Field(gt=0, allow_inf_nan=False)
    unit: str = Field(default='', max_length=40)
    note: str = Field(default='', max_length=240)
    group: str = Field(default='', max_length=80)
    series: str = Field(default='', max_length=80)
    color: Literal['blue', 'purple', 'green', 'amber', 'red', 'neutral'] | None = None

    @model_validator(mode='after')
    def within_scale(self):
        if self.value > self.max:
            raise ValueError('Value exceeds its scale.')
        if bool(self.group) != bool(self.series):
            raise ValueError('Comparison bars need both group and series.')
        return self


class ValueBarsContent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['value_bars'] = 'value_bars'
    question: str = Field(min_length=1, max_length=200)
    bars: list[ValueBar] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def comparable_groups(self):
        groups = {}
        colors = {}
        for bar in self.bars:
            if not bar.group:
                continue
            group = groups.setdefault(bar.group, [])
            if any(item.series == bar.series for item in group):
                raise ValueError('Comparison series must be unique within a group.')
            if group and (bar.max != group[0].max or bar.unit != group[0].unit):
                raise ValueError('Compared bars must share a scale and unit.')
            group.append(bar)
            if bar.color:
                if bar.series in colors and colors[bar.series] != bar.color:
                    raise ValueError('Keep comparison-series colors consistent.')
                colors[bar.series] = bar.color
        return self


class ValueBarsCard(ValueBarsContent):
    id: UUID


InteractionCard = Annotated[ChoiceCard | InputCard | ValueBarsCard, Field(discriminator='kind')]
_card_adapter = TypeAdapter(InteractionCard)


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: UUID
    interaction_id: UUID
    selected: list[Annotated[str, Field(max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')]] = Field(default_factory=list, max_length=10)
    option_inputs: dict[Annotated[str, Field(max_length=40)], Annotated[str, Field(max_length=1000)]] = Field(default_factory=dict, max_length=10)
    values: dict[Annotated[str, Field(max_length=40)], Annotated[str, Field(max_length=1000)]] = Field(default_factory=dict, max_length=4)


def _invalid():
    raise AppError('INTERACTION_INVALID_ANSWER', 'Review the fields and try again.', 422)


def _value(field, raw):
    if len(raw) > field.max_length or (field.required and not raw.strip()):
        _invalid()
    if not raw.strip():
        return ''
    if isinstance(field, InputField):
        if field.kind == 'number':
            import math
            try:
                number = float(raw)
            except ValueError:
                _invalid()
            if not math.isfinite(number) or (field.minimum is not None and number < field.minimum) or (field.maximum is not None and number > field.maximum):
                _invalid()
        elif field.kind == 'select' and raw not in {x.id for x in field.options}:
            _invalid()
    return raw


def resolve_choice(cards, response):
    """Backward-compatible name; resolves all native chat inputs server-side."""
    card = next((x for x in cards if x['id'] == str(response.interaction_id)), None)
    if not card:
        raise AppError('INTERACTION_NOT_FOUND', 'This interaction is unavailable.', 404)
    value = _card_adapter.validate_python(card)
    if isinstance(value, ValueBarsCard):
        _invalid()
    if isinstance(value, ChoiceCard):
        ordered = selected_options(value.options, value.kind, response.selected)
        allowed = {x.id for x in ordered if x.input}
        if response.values or set(response.option_inputs) - allowed:
            _invalid()
        labels = []
        for option in ordered:
            label = f'{option.id}: {option.label}'
            if option.input:
                entered = _value(option.input, response.option_inputs.get(option.id, ''))
                label += f' — {option.input.label}: {entered}'
            labels.append(label)
        content = f'{value.question}\nSelected: ' + '; '.join(labels)
    else:
        if response.selected or response.option_inputs or set(response.values) - {x.id for x in value.fields}:
            _invalid()
        lines = []
        for field in value.fields:
            entered = _value(field, response.values.get(field.id, ''))
            if field.kind == 'select' and entered:
                entered = next(x.label for x in field.options if x.id == entered)
            lines.append(f'{field.label}: {entered}')
        content = value.question + '\n' + '\n'.join(lines)
    if len(content) > 4000:
        _invalid()
    return card, content


def create_interaction_tools(owner, scope, budget):
    from langchain_core.tools import StructuredTool

    def stage(value, card_type):
        budget.call(True)
        cards = scope.setdefault('interactions', [])
        identifier = uuid5(NAMESPACE_URL, f"choice:{owner}:{scope['current_user_message_id']}:{value.model_dump_json()}")
        card = card_type(id=identifier, **value.model_dump()).model_dump(mode='json')
        if not any(x['id'] == card['id'] for x in cards):
            if len(cards) >= 3:
                raise AppError('INTERACTION_LIMIT', 'Use at most three interactions per response.', 422)
            cards.append(card)
        next_step = ('Continue the explanation; these static visuals require no user input.' if isinstance(value, ValueBarsContent)
                     else 'Wait for the student input; do not answer on their behalf.')
        return dict(interaction_id=card['id'], outcome='displayed', next_step=next_step)

    async def present(**arguments):
        return stage(ChatChoiceContent(**arguments), ChoiceCard)

    async def request(**arguments):
        return stage(InputContent(**arguments), InputCard)

    async def visualize(**arguments):
        return stage(ValueBarsContent(**arguments), ValueBarsCard)

    return [StructuredTool.from_function(name='present_choices', args_schema=ChatChoiceContent,
        description='Display native single/multiple choices. Options may attach an input for a custom answer. Use assessment tools for graded questions.', coroutine=present),
        StructuredTool.from_function(name='request_input', args_schema=InputContent,
        description='Collect missing user information in a native text_input (one text field) or form (up to four fields). Not graded answers or authorization for domain mutations.', coroutine=request),
        StructuredTool.from_function(name='present_visuals', args_schema=ValueBarsContent,
        description='Display static value bars for difficulty, ratings, amounts, progress or comparisons. Supply labels, values and scales; label estimates in note. No live tracking or response markup needed.', coroutine=visualize)]
