"""Cheap candidate hints, never authorization or a language allowlist."""
import re


def supplied_content_task(text: str) -> bool:
    """A transformation of pasted content is not a request to retrieve its words."""
    match = re.match(r'\s*(?:rewrite|rephrase|translate|summari[sz]e|edit|format|proofread|debug|explain|analy[sz]e)\b([^:\n]*)(?::|\n)([\s\S]+)', text, re.I)
    return bool(match and match[2].strip() and not re.search(
        r'\b(?:earlier|previous|uploaded|attached|from (?:my|the) (?:library|file|document)|search|look up)\b', match[1], re.I))


def practice_request(text: str) -> bool:
    """High-confidence assessment request, not every conversational question.

    This hint can require a native assessment receipt. Ambiguous practice,
    onboarding and Socratic questions stay model-directed conversation; the
    model can discover assessment tools in any language when actually requested.
    """
    text = text.strip().casefold()
    if re.search(r'\b(?:do not|don.t|never)\s+(?:create|give|generate|make|start|quiz|test)\b', text):
        return False
    if re.match(r'^(?:explain|define|what (?:is|are)|rewrite|translate|summari[sz]e|edit|debug)\b', text):
        return False
    if re.search(r'\b(?:unit tests?|test suite|test cases?|pytest)\b', text):
        return False
    subject = bool(re.search(r'\b(?:quiz|test|assessment|mock (?:paper|exam))\b|کوئز|اختبار|مسابقة|cuestionario|évaluation', text))
    formal = r'(?:quiz|test|assessment|mock (?:paper|exam))'
    # Keep a creation verb tied to its object within one clause. Asking for
    # advice/options about an upcoming test is not asking us to create one.
    prefix = (r'(?:^|[.!?;]\s+)(?:please\s+)?(?:give|generate|create|make|build|prepare|start)\b|'
              r'\b(?:i (?:want|need)|(?:can|could|would) you (?:give|generate|create|make|build|prepare|start)|'
              r'please (?:give|make|create)|let.s (?:do|take|start))\b')
    request = any(not re.search(r'\b(?:about|for|with|advice|help|options|learn|study)\b', match[1])
                  for match in re.finditer(r'(?:'+prefix+r')([^.!?;]{0,100}?)\b'+formal+r'\b', text))
    request = request or bool(subject and re.search(
        r'\b(?:mujhe|chahiye|poocho)\b|(?:دیں|دو|پوچھ|بنائیں)|^(?:hazme|crée|pose)', text))
    return (subject and request or bool(re.search(
        r'\b(?:quiz|test|assess) me\b|\btest (?:if|whether|how (?:well|much)) i (?:understand|know|learned)|'
        r'\btest my (?:understanding|knowledge)\b', text))
        or bool(re.fullmatch(r'(?:a |an )?(?:quiz|mcq|assessment|practice test)[.!? ]*', text)))


def assessment_mentioned(text: str) -> bool:
    return bool(re.search(r'\b(?:assessment|quiz|mock paper|mock exam|answer sheet|test)\b|کوئز|اختبار|cuestionario', text, re.I))


def web_request(text: str) -> bool:
    return bool(re.search(r'\b(?:search (?:the )?(?:web|internet)|look up|browse|verify|research|latest|current|today.s|weather|news|price|exchange rate)\b', text, re.I)
                or re.search(r'https?://', text))


def response_edit_source(query, rows):
    """Conservative visible-artifact edit hint; missing originals need discovery."""
    if not re.match(r'\s*(?:please\s+)?(?:make|change|revise|rewrite|edit|update|shorten|expand|simplify|add|remove|replace|refactor|convert|translate|format|keep)\b', query, re.I):
        return None
    if re.search(r'\b(?:search|browse|verify|latest|current|look up|my profile|my preferences|remember|remind|reschedule|appointment|my agenda|my schedule|my calendar|upload|attached|from my library|using my notes|based on my notes)\b', query, re.I):
        return None
    if practice_request(query):
        return None
    previous = next((row for row in reversed(rows) if row.get('role') == 'assistant' and row.get('content', '').strip()), None)
    if not previous or not previous.get('id') or any((previous.get('metadata') or {}).get(key) for key in ('assessment_cards', 'event_references', 'interactions')):
        return None
    # Internal evidence markers need their domain provenance, not a text-only
    # shortcut. Ordinary Markdown links and complete supplied artifacts are fine.
    if re.search(r'\[\[(?:S|H|M)\d+\]\]', previous['content']):
        return None
    if re.search(r'\[\[W\d+\]\]', previous['content']):
        from app.web_search.citations import edit_web_links
        if edit_web_links(previous['content'], previous.get('metadata') or {}) is None:
            return None
    return previous
