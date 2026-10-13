"""Keep uploads scoped to their turn; retain explicit references to older files."""
import re


def attachment_ids(query, scope):
    current = list(scope.get('attachment_ids', []))
    if current:
        return current
    rows = list(scope.get('context_rows', []))
    for row in reversed(rows):
        if scope.get('current_user_message_id') and row.get('id') == scope['current_user_message_id']:
            current = row.get('metadata', {}).get('attachments', [])
            if current:
                return [item['id'] for item in current][:4]
            break
    # A filename identifies a particular older upload, even when a newer one exists.
    text = query.casefold()
    named, seen = [], set()
    for row in reversed(rows):
        files = row.get('metadata', {}).get('attachments', [])
        for item in files:
            filename = item.get('filename', '').casefold()
            if filename and filename not in seen and re.search(r'(?<!\w)' + re.escape(filename) + r'(?!\w)', text):
                named.append(item['id']); seen.add(filename)
    if named:
        return named[:4]
    reference = re.search(r'\b(?:the|this|that|these|those|earlier|previous|last|uploaded|attached)\s+(?:(?:uploaded|attached|previous|earlier|last)\s+)?(?:images?|photos?|pictures?|screenshots?|diagrams?|files?|documents?|uploads?|attachments?)\b|\b(?:image|photo|picture|screenshot|diagram|file|document|upload|attachment)s?\s+(?:I\s+)?(?:uploaded|attached|sent|shared)\b', query, re.I)
    if reference:
        for row in reversed(rows):
            files = row.get('metadata', {}).get('attachments', [])
            if files:
                return [item['id'] for item in files][:4]
    return []
