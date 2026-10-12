"""Operation-level schemas with bounded discovery of real capabilities."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import StructuredTool
from .tool_policy import catalog


class EnableModules(BaseModel):
    model_config = ConfigDict(extra='forbid')
    modules: list[Literal['history', 'memory', 'learner', 'events', 'rag', 'assessment', 'chat', 'web']] = Field(default_factory=list, max_length=3)
    tool_names: list[str] = Field(default_factory=list, max_length=6)
    catalog_only: bool = False
    all_tools: bool = False


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
        if 'web_search' in self.by_name:
            self.active.add('web_search')
        if 'web_research' in self.by_name:
            self.active.add('web_research')
        self.pending = set(self.active)
        self.full_requested = False

    def selected(self):
        return [tool for tool in self.tools if tool.name in self.active]

    def complete(self, name):
        self.pending.discard(name)

    def discovery(self):
        async def enable(modules=None, tool_names=None, catalog_only=False, all_tools=False):
            self.scope['direct_rejected'] = True  # Discovery means no-tool certainty was not established.
            if catalog_only:
                return dict(outcome='catalog', capabilities=self.catalog)
            wanted = set(tool_names or [])
            unavailable = [domain for domain in (modules or []) if domain not in self.catalog]
            for domain in modules or []:
                wanted.update(tool.name for tool in self.tools if self.domains.get(tool.name) == domain)
            if all_tools:
                if self.full_requested:
                    return dict(outcome='already_enabled', tools=sorted(self.active))
                wanted.update(self.by_name)
            rejected = sorted(wanted - self.by_name.keys())
            wanted &= self.by_name.keys()
            proposed = wanted | self.pending
            checker = self.scope.get('_admit_schemas')
            if checker and not checker([self.by_name[name] for name in proposed]):
                return dict(outcome='rejected', code='TOOL_SCHEMA_LIMIT', reason='The requested schemas do not fit. Request only the exact tool needed; preserve the current evidence.', unavailable=unavailable, rejected=rejected)
            already = sorted(wanted & self.active)
            newly = sorted(wanted - self.active)
            self.active = proposed
            if all_tools:
                self.full_requested = True
            return dict(outcome='enabled' if wanted else 'unavailable', newly_enabled=newly,
                        already_enabled=already, unavailable=unavailable, rejected=rejected, tools=sorted(proposed))
        return StructuredTool.from_function(name='enable_workflow_tools', args_schema=EnableModules,
            description='Discover real capabilities or bind exact tool_names/modules missing from this subset. Does not execute actions or grant permission. Prefer exact names; catalog_only lists capabilities, all_tools is a bounded last resort.', coroutine=enable)
