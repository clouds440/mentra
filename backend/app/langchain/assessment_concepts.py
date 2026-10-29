"""Resolve generated concept labels through the learner facade, never invent IDs."""
from app.learner.schemas import GeneratedConceptsRequest

def concept_label(label):
    from hashlib import sha256
    value = ' '.join(label.split())
    return value if len(value) <= 200 else value[:176] + ' [' + sha256(value.encode()).hexdigest()[:16] + ']'

async def resolve_question_concepts(learner, owner, request, questions, targets):
    if request.concept_ids:
        # Exact targets have already been validated, including model attribution.
        # Never let extra generated labels create or substitute an identity.
        for question in questions:
            question.concept_names = []
        return
    known = {item['id']: item['name'] for item in targets}
    by_name = {item['name'].casefold(): item['id'] for item in targets}
    pending = {}
    for question in questions:
        resolved, labels = [], list(question.concept_names)
        for value in question.concept_ids:
            if value in known:
                resolved.append(value)
            elif value.casefold() in by_name:
                resolved.append(by_name[value.casefold()])
            else:
                # An unknown opaque ID is not evidence of identity. Prefer the
                # explicit concept names; ask the same domain to resolve a label.
                from uuid import UUID
                try: UUID(value)
                except ValueError: labels.append(value)
        # Supplied, validated target IDs are authoritative attribution. The
        # generator's optional prose labels must not create parallel skills.
        labels = [] if resolved else [label for label in labels if label.strip()]
        if not resolved and not labels:
            # The generator omitted attribution; use its assessment topic, never
            # an arbitrary ID or unrelated historical weakness.
            labels = [request.topic]
        question.concept_ids = list(dict.fromkeys(resolved))
        pending[id(question)] = list(dict.fromkeys(concept_label(label) for label in labels if label.strip()))
    labels = list(dict.fromkeys(label for values in pending.values() for label in values))
    # The learner API intentionally resolves small packets. It owns aliases,
    # candidate promotion, canonical identity and context membership.
    for start in range(0, len(labels), 5):
        batch = labels[start:start+5]
        if hasattr(learner, 'resolve_generated_concept_labels'):
            bindings = await learner.resolve_generated_concept_labels(GeneratedConceptsRequest(
                learner_id=owner, context_id=request.context_id, topic=request.topic, labels=batch, permissive=True))
            by_name.update({label.casefold():identifier for label,identifier in bindings.items()})
            continue
        concepts = await learner.resolve_generated_concepts(GeneratedConceptsRequest(
            learner_id=owner, context_id=request.context_id, topic=request.topic, labels=batch, permissive=True))
        for concept in concepts:
            by_name[concept.canonical_name.casefold()] = concept.id
        # The facade may merge aliases. Resolve each unmatched label via the same
        # public service, whose result is unambiguous for a single requested label.
        for label in batch:
            if label.casefold() not in by_name:
                value = await learner.resolve_generated_concepts(GeneratedConceptsRequest(
                    learner_id=owner, context_id=request.context_id, topic=request.topic, labels=[label], permissive=True))
                if value: by_name[label.casefold()] = value[0].id
    for question in questions:
        question.concept_ids = list(dict.fromkeys([*question.concept_ids,
            *(by_name[label.casefold()] for label in pending[id(question)] if label.casefold() in by_name)]))
        if not question.concept_ids:
            from app.core.exceptions import AppError
            raise AppError('ASSESSMENT_TARGETS_REQUIRED','A question needs a verified learning target. Please retry.',422)
        question.concept_names = []
