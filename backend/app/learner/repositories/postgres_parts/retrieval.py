"""Bounded SQLAlchemy queries for owned context, state and graph retrieval."""

from sqlalchemy import select, func, case, or_, literal, Integer
from app.learner.repositories.tables import concept, concept_alias as aliases, concept_redirect as redirects, learning_context as contexts, context_concept as links, concept_relation as relations
from .base import PostgresRepositoryBase
from app.learner.repositories.tables.topics import topic_skill, learning_topic


def matches(term, learner_id=None):
    alias_match = select(aliases.c.id).where(aliases.c.concept_id == concept.c.id, aliases.c.confidence >= 0.9,
                  func.strpos(literal(' ') + aliases.c.normalized_alias + ' ', ' ' + term + ' ') > 0).exists()
    private_match = select(topic_skill.c.concept_id).join(learning_topic,
        (learning_topic.c.id == topic_skill.c.topic_id) & (learning_topic.c.learner_id == topic_skill.c.learner_id)).where(
            topic_skill.c.learner_id == learner_id, topic_skill.c.concept_id == concept.c.id,
            or_(func.lower(topic_skill.c.label).contains(term, autoescape=True),
                topic_skill.c.phrases.contains(term, autoescape=True),
                learning_topic.c.normalized_name.contains(term, autoescape=True))).exists()
    return or_(func.strpos(literal(' ') + concept.c.normalized_name + ' ', ' ' + term + ' ') > 0, alias_match, private_match)


class RetrievalStore(PostgresRepositoryBase):
    def progress_concepts(self, learner_id, context_ids, query, limit, offset):
        # Search the owned collection, not the compact top-K model packet.
        linked = select(links.c.context_id).join(contexts, contexts.c.id == links.c.context_id).where(
            links.c.concept_id == concept.c.id, links.c.learner_id == learner_id,
            contexts.c.learner_id == learner_id, contexts.c.id.in_(context_ids)).exists()
        base = select(concept).where(linked, concept.c.status == 'ACTIVE')
        filtered = base
        if query:
            alias_match = select(aliases.c.id).where(aliases.c.concept_id == concept.c.id,
                aliases.c.confidence >= .9, func.strpos(aliases.c.normalized_alias, query) > 0).exists()
            filtered = base.where(or_(func.strpos(concept.c.normalized_name, query) > 0, alias_match))
        with self._session() as session:
            # One statement gives rows, counts and a clamped page from the same
            # snapshot, even when links change while the reader is paging.
            counts = select(
                select(func.count()).select_from(filtered.subquery()).scalar_subquery().label('total'),
                select(func.count()).select_from(base.subquery()).scalar_subquery().label('total_concepts')).cte('counts')
            bounded_offset = func.least(offset, func.greatest(0, func.floor((counts.c.total - 1) / limit)).cast(Integer) * limit)
            page = filtered.order_by(func.lower(concept.c.canonical_name), concept.c.id).limit(limit).offset(bounded_offset).lateral('page')
            stmt = select(counts, bounded_offset.label('offset'), page).select_from(counts.outerjoin(page, literal(True)))
            rows = list(session.execute(stmt).mappings())
            summary = rows[0]
            return ([self._concept_from_row(row) for row in rows if row['id'] is not None],
                    summary['total'], summary['total_concepts'], summary['offset'])

    def canonical_concepts(self, concept_ids):
        original = concept.alias('original')
        stmt = select(original.c.id.label('original_id'), concept).select_from(original.outerjoin(redirects,
            redirects.c.source_id == original.c.id).join(concept, concept.c.id == func.coalesce(redirects.c.target_id, original.c.id))).where(original.c.id.in_(concept_ids))
        with self._session() as session:
            return {row['original_id']: self._concept_from_row(row) for row in session.execute(stmt).mappings()}

    def context_ids_for_terms(self, learner_id, terms):
        if not terms:
            return set()
        stmt = select(contexts.c.id).join(links, links.c.context_id == contexts.c.id).join(concept, concept.c.id == links.c.concept_id).where(
            contexts.c.learner_id == learner_id, links.c.learner_id == learner_id, contexts.c.status != 'ARCHIVED',
            concept.c.status == 'ACTIVE', or_(*(matches(term, learner_id) for term in terms))).distinct()
        with self._session() as session:
            return set(session.execute(stmt).scalars())

    def context_concepts(self, learner_id, context_ids, query_terms=(), limit=None, normalized_query='', concept_ids=None):
        score = literal(0)
        filters = [contexts.c.learner_id == learner_id, links.c.learner_id == learner_id,
                   contexts.c.id.in_(context_ids), concept.c.status == 'ACTIVE']
        if concept_ids is not None:
            filters.append(concept.c.id.in_(concept_ids))
        if query_terms:
            predicates = [matches(term, learner_id) for term in query_terms]
            filters.append(or_(*predicates))
            exact_alias = select(aliases.c.id).where(aliases.c.concept_id == concept.c.id,
                aliases.c.confidence >= 0.9, aliases.c.normalized_alias == normalized_query).exists()
            score = sum((case((predicate, 1), else_=0) for predicate in predicates), literal(0))
            score += case((or_(concept.c.normalized_name == normalized_query, exact_alias), 100), else_=0)
        stmt = select(concept, score.label('match_score'), func.lower(concept.c.canonical_name).label('name_order')).join(links, links.c.concept_id == concept.c.id).join(contexts,
            contexts.c.id == links.c.context_id).where(*filters).distinct().order_by(score.desc(), func.lower(concept.c.canonical_name), concept.c.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._session() as session:
            return [self._concept_from_row(row) for row in session.execute(stmt).mappings()]

    def context_factors(self, learner_id, selected_contexts, concept_ids=None):
        relevance = {c.id: c.relevance_score if c.relevance_score is not None else 0.5 for c in selected_contexts}
        result = {}
        with self._session() as session:
            query = select(links).where(links.c.learner_id == learner_id, links.c.context_id.in_(relevance))
            if concept_ids is not None:
                query = query.where(links.c.concept_id.in_(concept_ids))
            for row in session.execute(query).mappings():
                factor = dict(importance=row['importance'], relevance=relevance[row['context_id']], target_difficulty=row['target_difficulty'], context_id=row['context_id'])
                old = result.get(row['concept_id'])
                if old is None or (factor['importance'] * factor['relevance'], factor['target_difficulty']) > (
                        old['importance'] * old['relevance'], old['target_difficulty']):
                    result[row['concept_id']] = factor
        return result

    def context_relevance(self, learner_id, context_ids):
        with self._session() as session:
            return dict(session.execute(select(links.c.concept_id, func.max(func.coalesce(contexts.c.relevance_score, 0.5))).join(contexts,
                contexts.c.id == links.c.context_id).where(contexts.c.learner_id == learner_id, links.c.learner_id == learner_id,
                contexts.c.id.in_(context_ids)).group_by(links.c.concept_id)).all())

    def prerequisite_counts(self, concept_ids, context_ids=None, learner_id=None):
        filters = [relations.c.relation_type == 'PREREQUISITE_OF', relations.c.confidence >= 0.8, relations.c.source_concept_id.in_(concept_ids)]
        if context_ids is not None:
            filters.append(select(links.c.context_id).where(links.c.concept_id == relations.c.target_concept_id,
                links.c.learner_id == learner_id, links.c.context_id.in_(context_ids)).exists())
        with self._session() as session:
            return dict(session.execute(select(relations.c.source_concept_id, func.count()).where(*filters).group_by(relations.c.source_concept_id)).all())
