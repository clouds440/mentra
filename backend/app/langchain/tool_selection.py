"""Operation-level schemas with bounded discovery of real capabilities."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import StructuredTool
from .tool_policy import catalog
from .prompts.chat_ui import UI_TOPICS


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
        self.explicit = set()
        # Stable lean operations, selected by configuration/availability alone.
        core = {'web_search', 'search_study_material', 'assessment_generate', 'get_relevant_learner_context',
                'get_study_recommendations', 'event_lookup'}
        self.active = core & self.by_name.keys()
        has_assessment = bool(scope.get('chat_assessments')) or any(row.get('role')=='assistant' and any(card.get('assessment') for card in
            (row.get('metadata') or {}).get('assessment_cards',[])) for row in scope.get('context_rows',[])[-8:])
        if has_assessment:
            self.active.update({'assessment_question','assessment_revise'} & self.by_name.keys())
        self.common = {'present_questionnaire'} & self.by_name.keys()
        self.active.update(self.common)
        if 'present_visuals' in self.active:
            self.scope['_ui_topics'] = tuple(topic for topic in UI_TOPICS if topic in {*self.scope.get('_ui_topics', ()), 'bars'})
        # Only explicitly requested schemas are sticky through later discovery.
        # Unused lean defaults must not crowd out the requested specialist tool.
        self.pending = set()
        self.full_requested = False

    def selected(self):
        return [tool for tool in self.tools if tool.name in self.active]

    def complete(self, name):
        self.pending.discard(name)

    def discovery(self):
        async def enable(modules=None, tool_names=None, catalog_only=False, all_tools=False, ui=None):
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
                return dict(outcome='catalog', capabilities=self.catalog,
                    next_step='Enable exact tool names or a bounded module; loading every schema is unnecessary.')
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
            previous_explicit=set(self.explicit)
            self.explicit.update(wanted)
            def restore_topics():
                self.explicit=previous_explicit
                if previous_topics:
                    self.scope['_ui_topics'] = previous_topics
                else:
                    self.scope.pop('_ui_topics', None)
            try:
                admitted = not checker or checker([self.by_name[name] for name in proposed])
                if not admitted and not (wanted & self.common):
                    smaller=wanted | self.pending
                    if checker and checker([self.by_name[name] for name in smaller]):
                        proposed,admitted=smaller,True
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
