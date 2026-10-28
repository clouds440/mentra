"""Trusted visible identities and availability, never natural-language routing."""


def visible_context(scope):
    rows = scope.get('context_rows', [])
    entities, artifacts, files = [], [], []
    for row in rows[-12:]:
        metadata = row.get('metadata') or {}
        if row.get('role') == 'assistant':
            artifacts.append(dict(message_id=str(row['id']), available=True))
            for card in metadata.get('assessment_cards', []):
                assessment = card.get('assessment') or {}
                entities.append(dict(kind='assessment', draft_id=card.get('id'), assessment_id=assessment.get('id') or card.get('assessment_id'),
                    title=assessment.get('title') or card.get('title'), generation_job_id=card.get('generation_job_id')))
        for item in metadata.get('attachments', []):
            files.append({key:item[key] for key in ('id','filename','media_type') if key in item})
    current = next((row for row in rows if str(row['id']) == scope.get('current_user_message_id')), {})
    return dict(visible_artifacts=artifacts[-8:], visible_entities=entities[-12:], visible_files=files[-12:],
        user_statement_context=dict(occurred_at=current.get('created_at'), timezone=(current.get('metadata') or {}).get('timezone')),
        event_preferences=scope.get('event_preferences'))
