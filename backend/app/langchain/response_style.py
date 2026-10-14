"""Translate saved preference enums into bounded, server-owned reply guidance."""

PREFERENCES = {
    'balanced': 'Answer first, then only the explanation needed for the current request.',
    'concise': 'Give the direct answer first. Prefer one short paragraph or 3-5 short bullets. Omit unsolicited background, extra examples, recaps, encouragement and follow-up offers. Stop when the request is answered.',
    'examples_first': 'When an explanation is requested, lead with one small relevant example, then explain the idea briefly.',
    'step_by_step': 'For a requested solution or procedure, use short numbered steps. Do not turn a simple fact or greeting into a lesson.',
    'conceptual': 'For a requested explanation, focus on the core idea and why it works; avoid unnecessary procedural detail.',
}
DEPTHS = {'brief': 100, 'standard': 220, 'deep': 450}


def response_style(profile):
    details = profile.get('details') or {}
    preference = details.get('learning_preference', 'balanced')
    depth = details.get('explanation_depth', 'standard')
    if preference not in PREFERENCES:
        preference = 'balanced'
    if depth not in DEPTHS:
        depth = 'standard'
    return dict(learning_preference=preference, explanation_depth=depth,
                default_word_target=min(100, DEPTHS[depth]) if preference == 'concise' else DEPTHS[depth],
                guidance=PREFERENCES[preference])
