"""Unified Cloudinary originals; intentionally requires empty legacy file stores."""
from alembic import op
import sqlalchemy as sa

revision = '20261020_0028'
down_revision = '20261017_0027'
branch_labels = None
depends_on = None


def upgrade():
    connection=op.get_bind()
    for query in ('SELECT count(*) FROM chat_attachment', 'SELECT count(*) FROM rag_document_version',
                  'SELECT count(*) FROM assessment_attempt WHERE source IS NOT NULL'):
        if connection.scalar(sa.text(query)):
            raise RuntimeError('Legacy file data exists. Preserve/backfill it or explicitly remove disposable files before this migration.')
    op.add_column('chat_attachment',sa.Column('file_id',sa.Uuid(as_uuid=False),nullable=False))
    op.add_column('chat_attachment',sa.Column('media_type',sa.Text(),nullable=False))
    op.add_column('rag_document_version',sa.Column('file_id',sa.Uuid(as_uuid=False),nullable=False))
    op.add_column('assessment_attempt',sa.Column('source_file_id',sa.Uuid(as_uuid=False)))
    op.create_unique_constraint('uq_assessment_attempt_owner_id','assessment_attempt',['learner_id','id'])
    op.create_unique_constraint('uq_chat_attachment_owner_id','chat_attachment',['learner_id','id'])
    op.create_unique_constraint('uq_rag_version_owner_id','rag_document_version',['learner_id','id'])
    op.execute("\nCREATE TABLE file_asset (\n\tid UUID NOT NULL, \n\tlearner_id UUID NOT NULL, \n\tpurpose TEXT NOT NULL, \n\trequest_key TEXT NOT NULL, \n\tfilename TEXT NOT NULL, \n\tsize_bytes BIGINT NOT NULL, \n\tsha256 TEXT NOT NULL, \n\tmedia_type TEXT NOT NULL, \n\tenvironment TEXT NOT NULL, \n\tpublic_id TEXT NOT NULL, \n\tresource_type TEXT NOT NULL, \n\tasset_id TEXT, \n\tversion BIGINT, \n\tstate TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tlease_token UUID, \n\tretry_at TIMESTAMP WITH TIME ZONE, \n\tattempts INTEGER DEFAULT '0' NOT NULL, \n\terror TEXT, \n\tCONSTRAINT pk_file_asset PRIMARY KEY (id), \n\tCONSTRAINT uq_file_asset_owner_id UNIQUE (learner_id, id), \n\tCONSTRAINT uq_file_asset_owner_key UNIQUE (learner_id, request_key), \n\tCONSTRAINT uq_file_asset_provider UNIQUE (environment, public_id, resource_type), \n\tCONSTRAINT ck_file_asset_file_size CHECK (size_bytes > 0), \n\tCONSTRAINT ck_file_asset_file_state CHECK (state IN ('UPLOADING','STAGED','ACTIVE','DELETE_PENDING','DELETED')), \n\tCONSTRAINT ck_file_asset_file_resource CHECK (resource_type IN ('image','video','raw')), \n\tCONSTRAINT fk_file_asset_learner_id_learner FOREIGN KEY(learner_id) REFERENCES learner (id)\n)\n\n")
    op.execute('CREATE INDEX idx_file_cleanup ON file_asset (state, expires_at, retry_at)')
    op.execute('\nCREATE TABLE file_speech_operation (\n\tid UUID NOT NULL, \n\tlearner_id UUID NOT NULL, \n\tresult JSONB, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlease_token UUID, \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT pk_file_speech_operation PRIMARY KEY (id), \n\tCONSTRAINT uq_file_speech_operation_learner_id UNIQUE (learner_id, id), \n\tCONSTRAINT fk_file_speech_operation_learner_id_learner FOREIGN KEY(learner_id) REFERENCES learner (id)\n)\n\n')
    op.execute('\nCREATE TABLE file_export (\n\tid UUID NOT NULL, \n\tlearner_id UUID NOT NULL, \n\tevent_id UUID NOT NULL, \n\tevent_revision BIGINT NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_file_export PRIMARY KEY (id), \n\tCONSTRAINT uq_file_export_learner_id UNIQUE (learner_id, id), \n\tCONSTRAINT fk_file_export_learner_id_hm_event FOREIGN KEY(learner_id, event_id) REFERENCES hm_event (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_file_export_learner_id_learner FOREIGN KEY(learner_id) REFERENCES learner (id)\n)\n\n')
    op.execute("\nCREATE TABLE file_binding (\n\tid UUID NOT NULL, \n\tlearner_id UUID NOT NULL, \n\tfile_id UUID NOT NULL, \n\tpurpose TEXT NOT NULL, \n\tchat_attachment_id UUID, \n\tdocument_version_id TEXT, \n\tassessment_attempt_id UUID, \n\tspeech_operation_id UUID, \n\texport_id UUID, \n\treleased_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_file_binding PRIMARY KEY (id), \n\tCONSTRAINT fk_file_binding_learner_id_file_asset FOREIGN KEY(learner_id, file_id) REFERENCES file_asset (learner_id, id), \n\tCONSTRAINT fk_file_binding_learner_id_chat_attachment FOREIGN KEY(learner_id, chat_attachment_id) REFERENCES chat_attachment (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_file_binding_learner_id_rag_document_version FOREIGN KEY(learner_id, document_version_id) REFERENCES rag_document_version (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_file_binding_learner_id_assessment_attempt FOREIGN KEY(learner_id, assessment_attempt_id) REFERENCES assessment_attempt (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_file_binding_learner_id_file_speech_operation FOREIGN KEY(learner_id, speech_operation_id) REFERENCES file_speech_operation (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_file_binding_learner_id_file_export FOREIGN KEY(learner_id, export_id) REFERENCES file_export (learner_id, id) ON DELETE CASCADE, \n\tCONSTRAINT ck_file_binding_file_binding_target CHECK (num_nonnulls(chat_attachment_id,document_version_id,assessment_attempt_id,speech_operation_id,export_id) = 1), \n\tCONSTRAINT ck_file_binding_file_binding_purpose CHECK ((purpose='chat' AND chat_attachment_id IS NOT NULL) OR (purpose='library' AND document_version_id IS NOT NULL) OR (purpose='assessment' AND assessment_attempt_id IS NOT NULL) OR (purpose='speech' AND speech_operation_id IS NOT NULL) OR (purpose='export' AND export_id IS NOT NULL))\n)\n\n")
    op.execute('CREATE INDEX idx_file_binding_asset ON file_binding (file_id, released_at)')
    op.execute('\nCREATE TABLE file_read_lease (\n\tid UUID NOT NULL, \n\tfile_id UUID NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_file_read_lease PRIMARY KEY (id), \n\tCONSTRAINT fk_file_read_lease_file_id_file_asset FOREIGN KEY(file_id) REFERENCES file_asset (id) ON DELETE CASCADE\n)\n\n')
    op.execute('CREATE INDEX idx_file_read_asset ON file_read_lease (file_id, expires_at)')
    for table,column in [('chat_attachment','file_id'),('rag_document_version','file_id'),('assessment_attempt','source_file_id')]:
        op.create_foreign_key('fk_'+table+'_learner_id_file_asset',table,'file_asset',['learner_id',column],['learner_id','id'])
    op.drop_column('chat_attachment','data')
    op.drop_column('rag_document_version','storage_key')
    op.drop_column('assessment_attempt','source')


def downgrade():
    # Empty installations can roll back safely. Once any file exists, schema
    # rollback cannot reconstruct its original bytes and must refuse to proceed.
    connection = op.get_bind()
    for query in ('SELECT count(*) FROM file_asset', 'SELECT count(*) FROM chat_attachment',
                  'SELECT count(*) FROM rag_document_version',
                  'SELECT count(*) FROM assessment_attempt WHERE source_file_id IS NOT NULL'):
        if connection.scalar(sa.text(query)):
            raise RuntimeError('Original bytes cannot be reconstructed by schema downgrade. Restore a pre-migration snapshot or run a verified reverse export.')
    for table in ('chat_attachment', 'rag_document_version', 'assessment_attempt'):
        op.drop_constraint('fk_'+table+'_learner_id_file_asset', table, type_='foreignkey')
    for table in ('file_read_lease', 'file_binding', 'file_export', 'file_speech_operation', 'file_asset'):
        op.drop_table(table)
    for table, constraint in (('chat_attachment', 'uq_chat_attachment_owner_id'),
                              ('rag_document_version', 'uq_rag_version_owner_id'),
                              ('assessment_attempt', 'uq_assessment_attempt_owner_id')):
        op.drop_constraint(constraint, table, type_='unique')
    op.add_column('chat_attachment', sa.Column('data', sa.LargeBinary(), nullable=False))
    op.add_column('rag_document_version', sa.Column('storage_key', sa.Text(), nullable=False))
    op.add_column('assessment_attempt', sa.Column('source', sa.LargeBinary()))
    op.drop_column('chat_attachment', 'file_id')
    op.drop_column('chat_attachment', 'media_type')
    op.drop_column('rag_document_version', 'file_id')
    op.drop_column('assessment_attempt', 'source_file_id')
