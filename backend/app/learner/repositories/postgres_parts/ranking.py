"""Bounded candidate selection over a replaceable scalar index, never the ledger."""
from sqlalchemy import select, func, case, literal, and_, or_, union,union_all
from .base import PostgresRepositoryBase
from ..tables import concept, context_concept as links, concept_relation as relations
from ..tables import learner_concept_state as raw_states
from ..tables.projections import ranking_projection as projection
from ..tables.topics import topic_skill


class RankingStore(PostgresRepositoryBase):
    def ranking_candidates(self, owner, contexts, now, mastery, retention, ranking, supported_only=False):
        from app.learner.ranking import WeightedRankingPolicy
        from app.learner.scoring.retention import ExponentialRetentionPolicy
        ids = [c.id for c in contexts]
        if not ids:
            return []
        # Custom policies cannot borrow the standard policy's exact-index claim.
        # Their explicit Plan B is bounded oldest/unseen practice, not a full scan.
        if type(ranking) is not WeightedRankingPolicy or type(retention) is not ExponentialRetentionPolicy:
            with self._session() as session:
                return list(session.scalars(select(concept.c.id).join(links,links.c.concept_id==concept.c.id)
                    .outerjoin(raw_states,and_(raw_states.c.learner_id==owner,raw_states.c.concept_id==concept.c.id))
                    .where(links.c.learner_id==owner,links.c.context_id.in_(ids),concept.c.status=='ACTIVE')
                    .group_by(concept.c.id,raw_states.c.last_evidence_at)
                    .order_by(raw_states.c.last_evidence_at.asc().nullsfirst(),concept.c.id).limit(256)))
        relevance = case({c.id: c.relevance_score if c.relevance_score is not None else .5 for c in contexts}, value=links.c.context_id)
        scoped = select(links.c.concept_id,links.c.importance,links.c.target_difficulty,links.c.context_id,
            relevance.label('relevance')).where(links.c.learner_id==owner,links.c.context_id.in_(ids))\
            .distinct(links.c.concept_id).order_by(links.c.concept_id,(links.c.importance*relevance).desc(),
                links.c.target_difficulty.desc(),links.c.context_id).cte('ranking_scope')
        prereqs = select(relations.c.source_concept_id.label('concept_id'),func.count().label('count')).where(
            relations.c.relation_type=='PREREQUISITE_OF',relations.c.confidence>=.8,
            select(links.c.context_id).where(links.c.learner_id==owner,links.c.context_id.in_(ids),
                links.c.concept_id==relations.c.target_concept_id).exists()).group_by(relations.c.source_concept_id).cte('ranking_prereqs')
        states=projection
        current = and_(
            projection.c.policy_identity==getattr(mastery,'identity',mastery.version),
            states.c.mastery_policy_version==mastery.version,states.c.retention_policy_version==retention.version,
            projection.c.base_half_life==retention.base_half_life_days,projection.c.anchor<=now)
        def band_value(field):
            return case((scoped.c.target_difficulty<.35,projection.c[f'easy_{field}']),
                (scoped.c.target_difficulty<.7,projection.c[f'medium_{field}']),else_=projection.c[f'hard_{field}'])
        supported = and_(current,band_value('supported'))
        age = func.greatest(0,func.extract('epoch',literal(now)-projection.c.anchor)/86400.0)
        expected = .5 + band_value('amplitude') * func.power(2.0,-age/band_value('half_life'))
        known = and_(current,states.c.mastery.is_not(None))
        estimated = case((supported,expected),else_=states.c.mastery)
        decay_age = func.greatest(0,func.extract('epoch',literal(now)-states.c.last_demonstrated_at)/86400.0)
        recall = states.c.retention_confidence * func.power(2.0,-decay_age/projection.c.retention_half_life)
        risk = case((and_(current,states.c.last_demonstrated_at.is_not(None),states.c.retention_confidence.is_not(None)),1-recall),else_=.5)
        uncertainty = 1-func.coalesce(states.c.estimate_confidence,0)
        prerequisite = func.least(1.0,func.coalesce(prereqs.c.count,0)/3.0)
        weights = sum((ranking.weakness_weight,ranking.retention_weight,ranking.uncertainty_weight,
            ranking.prerequisite_weight,ranking.relevance_weight))
        practice = (ranking.weakness_weight*(1-estimated)+ranking.retention_weight*risk+
            ranking.uncertainty_weight*uncertainty+ranking.prerequisite_weight*prerequisite+
            ranking.relevance_weight*scoped.c.relevance)/weights
        verification = .45*uncertainty+.35*risk+.1*prerequisite+.1*scoped.c.relevance
        def score(value, unknown):
            value = case((~known,unknown),(states.c.verification_required,1.0),
                (~supported,func.greatest(value,.75)),else_=value)
            return value*(.2+.8*scoped.c.importance)
        eligible = and_(known,or_(states.c.verification_required,and_(supported,
            projection.c.independent_items>=3,func.coalesce(states.c.estimate_confidence,0)>=.4)),
            or_(states.c.verification_required,func.coalesce(states.c.estimate_confidence,0)<.65,recall<.5))
        scored = select(concept.c.id.label('concept_id'),func.coalesce(topic_skill.c.topic_id,concept.c.id).label('group_id'),
            topic_skill.c.topic_id.is_not(None).label('grouped'),
            score(practice,.8).label('practice'),score(verification,.9).label('verification'),eligible.label('eligible'))\
            .select_from(scoped.join(concept,concept.c.id==scoped.c.concept_id)
                .outerjoin(projection,and_(projection.c.learner_id==owner,projection.c.concept_id==concept.c.id))
                .outerjoin(prereqs,prereqs.c.concept_id==concept.c.id)
                .outerjoin(topic_skill,and_(topic_skill.c.learner_id==owner,topic_skill.c.concept_id==concept.c.id)))\
            .where(scoped.c.importance>0,concept.c.status=='ACTIVE').cte('ranking_scores')
        def shortlist(mode, only_supported=False):
            filters=[scored.c.eligible] if only_supported else []
            # Ungrouped skills are already one candidate per group. A top-N
            # heap avoids sorting their entire registry by an invented group ID.
            loose=select(scored.c.concept_id,scored.c[mode].label('priority')).where(
                ~scored.c.grouped,*filters).order_by(scored.c[mode].desc(),scored.c.concept_id.collate('C').desc()).limit(128)
            grouped=select(scored.c.concept_id,scored.c[mode].label('priority')).where(
                scored.c.grouped,*filters).distinct(scored.c.group_id.collate('C')).order_by(
                scored.c.group_id.collate('C'),scored.c[mode].desc(),scored.c.concept_id.collate('C').desc()).subquery()
            grouped=select(grouped).order_by(grouped.c.priority.desc(),grouped.c.concept_id.collate('C').desc()).limit(128)
            selected=union_all(loose,grouped).subquery()
            return select(selected.c.concept_id).order_by(selected.c.priority.desc(),selected.c.concept_id.collate('C').desc()).limit(128)
        with self._session() as session:
            return list(session.scalars(union(shortlist('practice'),shortlist('verification',supported_only))))
