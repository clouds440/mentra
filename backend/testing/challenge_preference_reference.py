"""Executable design reference only: not connected to live learner state."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Scope:
    owner: str
    context: str
    skill: str
    language: str = 'en'
    answer_mode: str = 'single_choice'


@dataclass(frozen=True)
class Outcome:
    scope: Scope
    family: str
    session: str
    direction: str
    score: float | None
    items: int = 3
    first_exposure: bool = True
    assisted: bool = False
    valid: bool = True
    served: bool = True
    grade_confidence: float = 1


def suggest(events, scope, *, baseline=.5, explicit_direction=None):
    if not isfinite(baseline) or not 0 <= baseline <= 1:
        raise ValueError('Expected a finite normalized baseline.')
    if explicit_direction not in (None, 'easier', 'harder'):
        raise ValueError('Unsupported direction.')
    # Most recent family observation wins, including withdrawal/invalidity.
    families = {}
    for event in reversed(events):
        if event.scope == scope:
            families.setdefault(event.family, event)
    window = list(families.values())[:32]
    eligible = [event for event in window if event.valid and event.served and event.first_exposure
        and not event.assisted and event.items >= 3 and event.score is not None
        and isfinite(event.score) and 0 <= event.score <= 1 and event.grade_confidence >= .8]
    harder = [event for event in eligible if event.direction == 'harder']
    easier = [event for event in eligible if event.direction == 'easier']
    supported = lambda group: len(group) >= 3 and len({event.session for event in group}) >= 2
    mean = lambda group: sum(event.score for event in group) / len(group) if group else None
    offset = 0
    flags = []
    if supported(harder) and mean(harder) >= .8:
        offset = .1
        if supported(easier) and mean(easier) < .5:
            flags.append('harder_success_easier_struggle: inspect item fit, engagement and grading')
    elif supported(easier):
        offset = -.1
        if mean(easier) < .5:
            flags.append('still_struggling: offer diagnostic and scaffolding')
    elif supported(harder) and mean(harder) < .5:
        flags.append('harder_not_supported: offer diagnostic, preserve explicit choice')
    # A fresh explicit choice wins this request; it does not mutate learned fit.
    requested = .1 if explicit_direction == 'harder' else -.1 if explicit_direction == 'easier' else offset
    return dict(target=max(.1, min(.9, baseline + requested)), learned_offset=offset,
        basis='explicit_request' if explicit_direction else 'provisional_observed_fit' if offset else 'insufficient_evidence',
        eligible_families=len(eligible), window_families=len(window), flags=flags)
