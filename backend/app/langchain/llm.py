"""Shared LangChain invocation component with mandatory prompt-source selection."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, TypeAdapter

from .model_factory import ModelFactory
from .prompts import PromptSource, get_system_prompt


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
        model = self.model_factory.get_model()
        if output_schema is not None:
            return model.with_structured_output(output_schema, method="function_calling")
        return model

    async def ainvoke(self, source: PromptSource, inputs: str | Mapping[str, Any], *,
                      system_context: str | None = None,
                      additional_sources: Sequence[PromptSource] = (),
                      output_schema: type[BaseModel] | None = None):
        """Invoke the shared provider component with source-specific instructions."""
        model = self._model(source, output_schema)
        result = await model.ainvoke(self.messages(source, inputs, system_context=system_context,
                                                    additional_sources=additional_sources))
        return TypeAdapter(output_schema).validate_python(result) if output_schema is not None else result

    async def ainvoke_messages(self, source: PromptSource, messages: Sequence[BaseMessage], *,
                               output_schema: type[BaseModel] | None = None,
                               additional_sources: Sequence[PromptSource] = (),
                               system_context: str | None = None):
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
        model = self._model(source, output_schema)
        result = await model.ainvoke(prepared)
        return TypeAdapter(output_schema).validate_python(result) if output_schema is not None else result
