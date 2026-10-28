"""Only explicit current-turn attachment identities are prepared automatically."""
def attachment_ids(query, scope):
    current = list(scope.get('attachment_ids', []))
    if current: return current
    if not scope.get('current_user_message_id'): return []
    for row in reversed(scope.get('context_rows', [])):
        if row.get('id') == scope.get('current_user_message_id'):
            return [item['id'] for item in (row.get('metadata') or {}).get('attachments', [])][:4]
    return []
