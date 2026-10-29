"""Resolve saved teaching defaults locally; never add a model or discovery call."""

PREFERENCES = {
    'balanced': 'Answer first; choose the explanation structure that fits this task.',
    'concise': 'Give the direct answer first. Prefer one short paragraph or 3-5 short bullets. Omit unsolicited background, extra examples, recaps, encouragement and follow-up offers. Stop when answered.',
    'examples_first': 'For teaching, lead with one small relevant example, then explain the underlying idea.',
    'step_by_step': 'For solutions or procedures, use short ordered steps; simple facts still get direct answers.',
    'conceptual': 'For teaching, explain the core idea, relationships and why it works before procedural detail.',
    'interactive': 'Answer first; choose the explanation structure that fits this task.',
}
DEPTHS = {'brief': 100, 'standard': 220, 'deep': 450}
DETAIL_GUIDANCE = {
    'brief': 'Keep essentials and at most one small example; omit extended derivations unless requested.',
    'standard': '',
    'deep': 'Develop the reasoning with supporting examples and useful nuance within the requested topic.',
}
PARTICIPATION = {
    'adaptive': 'Use participation selectively under the shared UI policy; a follow-up exercise is not a default ending.',
    'interactive': 'Within an eligible learning exchange, favor a useful prediction, choice or short exercise only when it advances the current learning goal. Follow the shared UI participation policy; Interactive is not an obligation to append checks.',
    'mostly_explanations': 'Prefer complete explanations without unsolicited exercises or comprehension checks; still clarify consequential missing input.',
}
VISUALS = {
    'adaptive': '',
    'prefer_visuals': 'Prefer a relevant visual when it makes an explanation or comparison clearer; follow the shared UI policy and discover advanced references when useful.',
    'mostly_text': 'Prefer prose, lists and simple tables; avoid unsolicited diagrams/charts unless essential to the task. Native input controls remain available.',
}
PURPOSES = {
    'general': '',
    'fundamentals': 'For relevant lesson plans or next steps, build core ideas and prerequisites.',
    'apply': 'For relevant teaching and plans, connect concepts to practical tasks and worked applications.',
    'exam': 'For relevant plans, focus on exam-relevant skills, revision and practice; do not create a saved assessment without a request.',
    'explore': 'For relevant teaching and plans, explain connections and useful directions to explore without expanding unrelated answers.',
}


def teaching_policy(profile):
    details = profile.get('details') or {}
    preference = details.get('learning_preference', 'balanced')
    depth = details.get('explanation_depth', 'standard')
    if preference not in PREFERENCES:
        preference = 'balanced'
    if depth not in DEPTHS:
        depth = 'standard'
    participation = details.get('participation', 'adaptive')
    visuals = details.get('visual_support', 'adaptive')
    purpose = details.get('learning_purpose', 'general')
    if participation not in PARTICIPATION:
        participation = 'adaptive'
    if preference == 'interactive' and participation == 'adaptive':
        participation = 'interactive'
    if visuals not in VISUALS:
        visuals = 'adaptive'
    if purpose not in PURPOSES:
        purpose = 'general'
    return dict(learning_preference=preference, explanation_depth=depth,
                participation=participation, visual_support=visuals, learning_purpose=purpose,
                default_word_target=min(100, DEPTHS[depth]) if preference == 'concise' else DEPTHS[depth],
                guidance=' '.join(filter(None, (PREFERENCES[preference], DETAIL_GUIDANCE['brief' if preference == 'concise' else depth], PARTICIPATION[participation],
                                               VISUALS[visuals], PURPOSES[purpose]))))


# Preserve the existing chat context key and callers.
response_style = teaching_policy
