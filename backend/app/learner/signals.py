"""Validate exact source spans and preserve uncertainty without promoting skills."""
from hashlib import sha256
from collections import Counter
from .normalization import normalize


def admit_signals(extraction,sources,question,concepts,context_ids):
    accepted=[]; rejected=Counter(); by_id={source['id']:source for source in sources}; seen=set()
    for item in extraction.signals:
        source=by_id.get(item.source_id)
        if source is None:
            rejected['unknown_source']+=1;continue
        text=source['text']
        start=item.start
        if start is None:
            start=text.find(item.quote)
            if start<0 or text.find(item.quote,start+1)>=0:
                rejected['missing_or_ambiguous_quote']+=1;continue
        end=item.end if item.end is not None else start+len(item.quote)
        if text[start:end]!=item.quote:
            rejected['invalid_span']+=1;continue
        pending=item.confidence<.85
        if pending: rejected['pending_low_confidence']+=1
        copied=item.authorship=='quoted' or (len(item.quote)>=20 and item.quote in question)
        kind='encounter' if copied else item.kind
        concept=concepts.get(item.concept_id)
        context=item.context_id if item.context_id in context_ids else context_ids[0] if len(context_ids)==1 else None
        if concept:
            context=concept.context_id if concept.context_id in context_ids else None
        # A model label cannot establish canonical identity or importance.
        # Source claims remain useful even before an owned context is available.
        label=concept.name if concept else item.label
        topic=item.topic
        fingerprint=sha256(f'{source["id"]}:{source["revision"]}:{start}:{end}:{kind}:{normalize(topic)}:{normalize(label)}'.encode()).hexdigest()
        if fingerprint in seen: continue
        seen.add(fingerprint)
        accepted.append(dict(kind=kind,label=label,normalized_label=normalize(label),topic=topic,status='pending' if pending else 'active',
            concept_id=concept.concept_id if concept else None,context_id=context,
            source_id=source['id'],source_kind=source['kind'],source_revision=source['revision'],
            quote=item.quote,span_start=start,span_end=end,confidence=item.confidence,fingerprint=fingerprint,
            details=dict(authorship='quoted' if copied else item.authorship,
                assistance=item.assistance,task_quote=item.task_quote if item.task_quote in question else '',
                task_supported=bool(item.task_quote and item.task_quote in question),
                note=item.note,scoring='not_admitted',identity='owned_known' if concept else 'unresolved',
                source_coverage=source.get('coverage','complete'),classification='pending_review' if pending else 'unverified_source_supported',policy='chat-learning-signals-v2')))
    return accepted,dict(rejected)
