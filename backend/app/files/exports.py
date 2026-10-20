from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from sqlalchemy import update, select
from app.db.owner_transactions import lock_owner
from .tables import exports, assets, bindings
from .service import now


def calendar_asset(files, owner, event_id, revision, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    import hashlib

    key = f"ics:{event_id}:{revision}:{int(now().timestamp()) // 3600}:{hashlib.sha256(data).hexdigest()[:12]}"
    file = files.upload(
        owner, BytesIO(data), f"mentra-event-{event_id}.ics", "export", key
    )
    with files.sessions.begin() as session:
        lock_owner(session, owner)
        binding = session.scalar(
            select(bindings.c.id).where(
                bindings.c.file_id == file["id"],
                bindings.c.learner_id == owner,
                bindings.c.released_at.is_(None),
            )
        )
        if binding:
            return file["id"], binding
        identifier = str(uuid4())
        session.execute(
            exports.insert().values(
                id=identifier,
                learner_id=owner,
                event_id=event_id,
                event_revision=revision,
                expires_at=now() + timedelta(hours=1),
            )
        )
        binding = files.bind(
            session, owner, file["id"], "export", dict(export_id=identifier)
        )
        session.execute(
            update(assets)
            .where(assets.c.id == file["id"])
            .values(expires_at=now() + timedelta(hours=1))
        )
    return file["id"], binding
