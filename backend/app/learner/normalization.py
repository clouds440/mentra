"""Conservative lookup normalization; canonical IDs never depend on labels."""

import re
import unicodedata


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def lookup_forms(value: str) -> tuple[str, ...]:
    normalized = normalize(value)
    words = normalized.split()
    if not words:
        return ()
    last = words[-1]
    singular = last
    irregular = {'analyses': 'analysis', 'hypotheses': 'hypothesis', 'indices': 'index',
                 'matrices': 'matrix', 'statuses': 'status'}
    if last in irregular:
        singular = irregular[last]
    elif last.endswith(('sses', 'xes', 'ches', 'shes', 'zzes')):
        singular = last[:-2]
    elif last.endswith("ies") and len(last) > 4:
        singular = last[:-3] + "y"
    elif last.endswith("s") and not last.endswith(("ss", "us", "is")) and len(last) > 3:
        singular = last[:-1]
    return tuple(dict.fromkeys((normalized, " ".join([*words[:-1], singular]))))


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w+#]+", normalize(value)))


def query_terms(value: str) -> list[str]:
    stopwords = {'a','an','the','is','of','to','what','how','my','i','and','in','should','study',
                 'learn','help','me','with','can','you','do','it','for','compare','explain','different',
                 'from','are','weakest','points','revise','before','exam'}
    words = re.findall(r"[\w+#]+", normalize(value))
    terms = []
    for word in words:
        if word not in stopwords:
            terms.extend(lookup_forms(word))
    return list(dict.fromkeys(terms))[:12]
