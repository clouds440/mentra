"""Operation-level schemas with bounded discovery of real capabilities."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import StructuredTool
from .tool_policy import catalog
from .prompts.chat_ui import COMMON_TOOLS, UI_TOPICS


class EnableModules(BaseModel):
    model_config = ConfigDict(extra='forbid')
    modules: list[Literal['history', 'memory', 'learner', 'events', 'rag', 'assessment', 'chat', 'web']] = Field(default_factory=list, max_length=3)
    tool_names: list[str] = Field(default_factory=list, max_length=6)
    catalog_only: bool = False
    all_tools: bool = False
    ui: list[Literal['charts', 'disclosures', 'color', 'bars']] = Field(default_factory=list, max_length=4)


class ToolSelection:
    def __init__(self, tools, domains, scope):
        self.tools, self.domains, self.scope = tools, domains, scope
        self.by_name = {tool.name: tool for tool in tools}
        self.catalog = catalog(tools, domains)
        plan = scope.get('execution_plan')
        if plan:
            self.active = set(plan.tool_names) & self.by_name.keys()
        else:
            enabled = scope.get('workflow_modules')
            self.active = {tool.name for tool in tools if enabled is None or domains.get(tool.name) in enabled}
        self.common = COMMON_TOOLS & self.by_name.keys()
        self.active.update(self.common)
        if 'present_visuals' in self.active:
            self.scope['_ui_topics'] = tuple(topic for topic in UI_TOPICS if topic in {*self.scope.get('_ui_topics', ()), 'bars'})
        self.pending = set(self.active)
        self.full_requested = False

    def selected(self):
        return [tool for tool in self.tools if tool.name in self.active]

    def complete(self, name):
        self.pending.discard(name)

    def discovery(self):
        async def enable(modules=None, tool_names=None, catalog_only=False, all_tools=False, ui=None):
            self.scope['direct_rejected'] = True  # Discovery means no-tool certainty was not established.
            if catalog_only:
                return dict(outcome='catalog', capabilities=self.catalog, ui_references=list(UI_TOPICS))
            wanted = set(tool_names or [])
            requested_topics = set(ui or [])
            if 'bars' in requested_topics:
                wanted.add('present_visuals')
            unavailable = [domain for domain in (modules or []) if domain not in self.catalog]
            for domain in modules or []:
                wanted.update(tool.name for tool in self.tools if self.domains.get(tool.name) == domain)
            if all_tools:
                if self.full_requested and set(self.by_name) <= self.active and not requested_topics:
                    return dict(outcome='already_enabled', tools=sorted(self.active))
                wanted.update(self.by_name)
            rejected = sorted(wanted - self.by_name.keys())
            wanted &= self.by_name.keys()
            proposed = wanted | self.pending | self.common
            previous_topics = self.scope.get('_ui_topics', ())
            topics = set(previous_topics) | requested_topics
            if 'present_visuals' in proposed:
                topics.add('bars')
            # The admission checker must account for references and schemas
            # together. Roll back both if adding them would exceed the budget.
            self.scope['_ui_topics'] = tuple(topic for topic in UI_TOPICS if topic in topics)
            checker = self.scope.get('_admit_schemas')
            def restore_topics():
                if previous_topics:
                    self.scope['_ui_topics'] = previous_topics
                else:
                    self.scope.pop('_ui_topics', None)
            try:
                admitted = not checker or checker([self.by_name[name] for name in proposed])
            except Exception:
                restore_topics()
                raise
            if not admitted:
                restore_topics()
                return dict(outcome='rejected', code='TOOL_SCHEMA_LIMIT', reason='Requested tools/UI references do not fit. Request only what is needed; preserve the current evidence.', unavailable=unavailable, rejected=rejected)
            already = sorted(wanted & self.active)
            newly = sorted(wanted - self.active)
            self.active = proposed
            self.pending.update(wanted)
            if all_tools:
                self.full_requested = True
            return dict(outcome='enabled' if wanted or requested_topics else 'unavailable', newly_enabled=newly,
                        already_enabled=already, unavailable=unavailable, rejected=rejected, tools=sorted(proposed),
                        ui_references=list(self.scope['_ui_topics']), reference_delivery='Selected UI reference instructions are included in the next model round.')
        return StructuredTool.from_function(name='enable_workflow_tools', args_schema=EnableModules,
            description='Enable missing tool_names/modules or load advanced UI references via ui (charts,disclosures,color,bars). catalog_only lists all capabilities/references. No actions or permission granted. Prefer exact names/topics; all_tools is a bounded last resort.', coroutine=enable)
