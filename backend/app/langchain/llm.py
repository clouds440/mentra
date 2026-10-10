"""Shared LangChain invocation component with mandatory prompt-source selection."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, TypeAdapter

from .model_factory import ModelFactory
from .prompts import PromptSource, get_system_prompt


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'ainvoke': {'input': lambda args: dict(prompt_source=args['source'].value)},
    'ainvoke_messages': {'input': lambda args: dict(prompt_source=args['source'].value, tool_count=len(args.get('tools') or []))},
})
class MentraLLM:
    """Build and invoke every model request under an explicit internal workflow.

    Workflow code selects the source. The model/user cannot select a prompt source.
    Optional system context stays data, separate from versioned prompt instructions.
    """

    def __init__(self, model_factory: ModelFactory) -> None:
        self.model_factory = model_factory

    def messages(self, source: PromptSource, inputs: str | Mapping[str, Any], *,
                 system_context: str | None = None,
                 additional_sources: Sequence[PromptSource] = ()) -> list[BaseMessage]:
        payload = (inputs if isinstance(inputs, str) else
                   json.dumps(inputs.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
                   if isinstance(inputs, BaseModel) else
                   json.dumps(inputs, ensure_ascii=False, separators=(",", ":")))
        system = "\n\n".join(get_system_prompt(prompt_source)
                              for prompt_source in (source, *additional_sources))
        if system_context:
            system = f"{system}\n\n{system_context}"
        return [SystemMessage(content=system), HumanMessage(content=payload)]

    def _model(self, source: PromptSource, output_schema: type[BaseModel] | None):
        from .token_policy import output_budget
        model = (self.model_factory.get_model(output_tokens=output_budget(source, self.model_factory._settings),
                    model_name=self.model_factory._settings.ai_vision_model if source is PromptSource.ASSESSMENT_TRANSCRIPTION else None)
                 if isinstance(self.model_factory, ModelFactory) else self.model_factory.get_model())
        if output_schema is not None:
            return model.with_structured_output(output_schema, method="function_calling",
                **({'include_raw': True} if isinstance(self.model_factory, ModelFactory) else {}))
        return model

    async def ainvoke(self, source: PromptSource, inputs: str | Mapping[str, Any], *,
                      system_context: str | None = None,
                      additional_sources: Sequence[PromptSource] = (),
                      output_schema: type[BaseModel] | None = None):
        """Invoke the shared provider component with source-specific instructions."""
        from .token_policy import check_input, log_usage, reserve_workflow
        prepared = self.messages(source, inputs, system_context=system_context, additional_sources=additional_sources)
        config = getattr(self.model_factory, '_settings', None)
        cost = check_input(prepared, source, tools=[output_schema] if output_schema else None,
                           **({'config': config} if config else {}))
        reserve_workflow(source, cost, **({'config': config} if config else {}))
        model = self._model(source, output_schema)
        result = await model.ainvoke(prepared)
        if output_schema and isinstance(result, dict) and 'raw' in result and 'parsed' in result:
            log_usage(result['raw'], source, cost)
            if result.get('parsing_error'):
                raise result['parsing_error']
            result = result['parsed']
        else:
            log_usage(result, source, cost)
        return TypeAdapter(output_schema).validate_python(result) if output_schema is not None else result

    async def ainvoke_messages(self, source: PromptSource, messages: Sequence[BaseMessage], *,
                               output_schema: type[BaseModel] | None = None,
                               additional_sources: Sequence[PromptSource] = (),
                               system_context: str | None = None,
                               tools: Sequence | None = None, tool_choice=None, on_delta=None):
        """Use a registered source prompt with ordered chat turns and optional data."""
        system_messages = [message for message in messages if isinstance(message, SystemMessage)]
        if system_messages:
            # Existing server-owned system context (such as learner packets) is
            # retained after the selected source prompt, never instead of it.
            context = "\n\n".join(str(message.content) for message in system_messages)
            turns = [message for message in messages if not isinstance(message, SystemMessage)]
            system = "\n\n".join(get_system_prompt(prompt_source)
                                    for prompt_source in (source, *additional_sources))
            prepared: list[BaseMessage] = [SystemMessage(content=f"{system}\n\n{context}"), *turns]
        else:
            system = "\n\n".join(get_system_prompt(prompt_source)
                                    for prompt_source in (source, *additional_sources))
            if system_context:
                system = f"{system}\n\n{system_context}"
            prepared = [SystemMessage(content=system), *messages]
        from .token_policy import check_input, log_usage, reserve_workflow
        config = getattr(self.model_factory, '_settings', None)
        cost = check_input(prepared, source, tools=[*(tools or []), *([output_schema] if output_schema else [])],
                           **({'config': config} if config else {}))
        reserve_workflow(source, cost, **({'config': config} if config else {}))
        model = self._model(source, output_schema)
        if tools:
            model = model.bind_tools(tools, **({'tool_choice': tool_choice} if tool_choice is not None else {}))
        if on_delta is not None and output_schema is None and hasattr(model, 'astream'):
            from langchain_core.messages import AIMessageChunk
            from langchain_core.messages.utils import message_chunk_to_message
            aggregate, pending = None, ''
            import time
            emitted = time.monotonic()
            async for chunk in model.astream(prepared):
                if not isinstance(chunk, AIMessageChunk): continue
                aggregate = chunk if aggregate is None else aggregate + chunk
                if isinstance(chunk.content, str): pending += chunk.content
                # Only public assistant text is streamed; tool arguments and
                # provider reasoning/content blocks never enter the transport.
                if pending and (len(pending) >= 512 or time.monotonic()-emitted >= .2):
                    for start in range(0,len(pending),1000): await on_delta(pending[start:start+1000])
                    pending, emitted = '', time.monotonic()
            if aggregate is None: raise ValueError('Provider returned no response chunks')
            result = message_chunk_to_message(aggregate)
            if getattr(result,'tool_calls',None): await on_delta(None)
            elif pending:
                for start in range(0,len(pending),1000): await on_delta(pending[start:start+1000])
        else:
            result = await model.ainvoke(prepared)
        if output_schema and isinstance(result, dict) and 'raw' in result and 'parsed' in result:
            log_usage(result['raw'], source, cost)
            if result.get('parsing_error'):
                raise result['parsing_error']
            result = result['parsed']
        else:
            log_usage(result, source, cost)
        return TypeAdapter(output_schema).validate_python(result) if output_schema is not None else result
