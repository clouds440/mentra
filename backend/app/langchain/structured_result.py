"""Strict recovery when a provider emits schema JSON outside its function call."""
import json
from langchain_core.exceptions import OutputParserException
from pydantic import TypeAdapter, ValidationError


class InvalidStructuredAssessment(OutputParserException):
    def __init__(self,candidate,violations):
        super().__init__('Assessment output did not match its schema.')
        self.candidate=candidate  # Private, in-memory repair data. Never log or return it.
        self.violations=violations


def candidate(raw,schema):
    if getattr(raw,'response_metadata',{}).get('finish_reason') in ('length','content_filter'):
        raise OutputParserException('Provider structured response is incomplete.')
    if getattr(raw,'invalid_tool_calls',None):
        raise OutputParserException('Provider returned malformed structured arguments.')
    calls=getattr(raw,'tool_calls',[]) or []
    if calls:
        if len(calls)==1 and calls[0].get('name')==schema.__name__ and isinstance(calls[0].get('args'),dict):
            return calls[0]['args']
        raise OutputParserException('Provider returned unexpected structured calls.')
    text=getattr(raw,'content',None)
    if not isinstance(text,str) or len(text)>1_000_000:
        raise OutputParserException('Provider omitted structured output.')
    text=text.strip().replace('\r\n','\n')
    if text.startswith('```json\n') and text.endswith('\n```'):text=text[8:-4]
    elif text.startswith('```\n') and text.endswith('\n```'):text=text[4:-4]
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate structured key')
            result[key]=value
        return result
    try:value=json.loads(text,object_pairs_hook=unique)
    except ValueError:raise OutputParserException('Provider omitted valid structured JSON.') from None
    if not isinstance(value,dict):raise OutputParserException('Expected one structured JSON object.')
    return value


def validate(value,schema,*,assessment=False):
    try:return TypeAdapter(schema).validate_python(value)
    except ValidationError as error:
        if not assessment:raise
        violations=[dict(location=list(item['loc']),type=item['type'],
            **{key:item['ctx'][key] for key in ('max_length','min_length','actual_length') if key in (item.get('ctx') or {})})
            for item in error.errors(include_input=False,include_url=False)[:20]]
        raise InvalidStructuredAssessment(value,violations) from None
