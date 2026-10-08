"""Retain one reminder ledger until its event is permanently removed.

The update fence from 0007 remains unchanged. A deletion fence prevents any
retention/cleanup adapter from erasing lifetime delivery history and rearming
the same event. Parent deletion still owns the canonical cascade/purge.
"""
from alembic import op

revision = '20261009_0008'
down_revision = '20261009_0007'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION hm_event_reminder_retain_ledger() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF EXISTS (SELECT 1 FROM hm_event
                       WHERE learner_id = OLD.learner_id AND id = OLD.event_id) THEN
                RAISE EXCEPTION 'A reminder ledger must remain until its event is deleted';
            END IF;
            RETURN OLD;
        END $$""")
    op.execute("""CREATE TRIGGER hm_event_reminder_retention_fence
        BEFORE DELETE ON hm_event_reminder FOR EACH ROW
        EXECUTE FUNCTION hm_event_reminder_retain_ledger()""")


def downgrade():
    op.execute('DROP TRIGGER hm_event_reminder_retention_fence ON hm_event_reminder')
    op.execute('DROP FUNCTION hm_event_reminder_retain_ledger()')
