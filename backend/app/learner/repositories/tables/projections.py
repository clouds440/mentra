from sqlalchemy import Table, Column, Text, Double, Integer, Boolean, ForeignKeyConstraint, CheckConstraint
from .common import metadata, identifier, timestamp

ranking_projection = Table('learner_ranking_projection', metadata,
    identifier('learner_id', primary_key=True), Column('concept_id', Text, primary_key=True),
    Column('state_version', Integer, nullable=False), Column('policy_identity', Text, nullable=False),
    Column('base_half_life', Double, nullable=False), timestamp('anchor'),
    Column('independent_items', Integer, nullable=False), Column('retention_half_life', Double, nullable=False),
    Column('mastery',Double),Column('estimate_confidence',Double),Column('retention_confidence',Double),
    timestamp('last_demonstrated_at',nullable=True),Column('verification_required',Boolean,nullable=False),
    Column('mastery_policy_version',Text,nullable=False),Column('retention_policy_version',Text,nullable=False),
    *[Column(f'{band}_{field}', Boolean if field == 'supported' else Double, nullable=False)
      for band in ('easy','medium','hard') for field in ('amplitude','half_life','supported')],
    ForeignKeyConstraint(['learner_id','concept_id'], ['learner_concept_state.learner_id','learner_concept_state.concept_id'], ondelete='CASCADE'),
    CheckConstraint('base_half_life > 0 AND retention_half_life > 0 AND independent_items >= 0', name='ranking_projection_bounds'))
