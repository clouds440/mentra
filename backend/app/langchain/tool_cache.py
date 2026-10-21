"""One key contract for admission, batch coalescing and turn-local tool reuse."""
import json
from copy import deepcopy
from app.core.read_cache import normalized_query
from .concurrent_reads import StagedRead
from .tool_policy import is_write


REVALIDATED_READS = {'assessment_status', 'search_study_material', 'get_study_source_chunk', 'conversation_summary_search'}


def copy_result(value):
    # Keep the turn-bound projector, but never share mutable cached payloads
    # with a consumer that may assign citations or otherwise alter a result.
    if isinstance(value, StagedRead):
        return StagedRead(value.project, deepcopy(value.payload))
    return deepcopy(value)


def tool_cache_key(tool, name, arguments):
    values = arguments
    if tool is not None and not is_write(name, arguments):
        try:
            values = tool.args_schema.model_validate(arguments).model_dump(mode='json')
            if isinstance(values.get('query'), str):
                values['query'] = normalized_query(values['query'])
            for key in ('context_ids', 'document_ids', 'concept_ids'):
                if isinstance(values.get(key), list):
                    values[key] = sorted(set(values[key]))
        except (ValueError, TypeError, AttributeError):
            # Invalid inputs retain their exact fingerprint and still undergo
            # normal admission/validation; they cannot alias a valid result.
            values = arguments
    return name + ':' + json.dumps(values, sort_keys=True, default=str)
