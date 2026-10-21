"""Page mistake history in PostgreSQL without transferring every paper/answer."""
from sqlalchemy import text


# Resolution and facets intentionally use the WHOLE owned history, before the
# visible filters. A later revision-practice answer can resolve an older source.
PAGE = text("""
WITH expanded AS (
    SELECT a.id::text assessment_id, a.title assessment_title,
           r.id::text attempt_id, r.grade_revision,
           q.value->>'id' question_id, q.value question,
           coalesce(a.practice_lineage->'question_items'->>(q.value->>'id'),
                    a.id::text || ':' || (q.value->>'id')) root,
           (g.value->>'score')::double precision score,
           (q.value->>'marks')::double precision marks,
           g.value->>'feedback' feedback,
           coalesce(r.answers->>(q.value->>'id'), '') answer,
           r.submitted_at, r.created_at, g.position,
           coalesce(r.submitted_at, r.created_at) occurred_at
    FROM assessment a JOIN assessment_attempt r ON r.assessment_id=a.id AND r.learner_id=a.learner_id
    CROSS JOIN LATERAL jsonb_array_elements(a.questions) q(value)
    CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(r.grades)='array'
        THEN r.grades ELSE '[]'::jsonb END) WITH ORDINALITY g(value, position)
    WHERE a.learner_id=:owner AND r.state='graded' AND g.value->>'question_id'=q.value->>'id'
), ranked AS (
    SELECT *, row_number() OVER (ORDER BY submitted_at ASC NULLS LAST, created_at, attempt_id, position) encounter_order,
        sum((score < marks)::integer) OVER (PARTITION BY root) occurrences,
        first_value(score >= marks) OVER (PARTITION BY root ORDER BY
            submitted_at DESC NULLS FIRST, created_at DESC, attempt_id DESC, position DESC) resolved
    FROM expanded
), wrong AS (
    SELECT *, min(encounter_order) OVER (PARTITION BY assessment_id, question_id) first_seen,
        row_number() OVER (PARTITION BY assessment_id, question_id ORDER BY
        submitted_at DESC NULLS FIRST, created_at DESC, attempt_id DESC, position DESC) latest_wrong
    FROM ranked WHERE score < marks
), catalog AS MATERIALIZED (
    SELECT *, row_number() OVER (ORDER BY NOT resolved DESC, occurrences DESC,
        (1-score/marks) DESC, marks DESC, occurred_at DESC,
        first_seen) catalog_order
    FROM wrong WHERE latest_wrong=1
), filtered AS (
    SELECT * FROM catalog WHERE
        (cardinality(CAST(:assessment_ids AS text[]))=0 OR assessment_id=ANY(CAST(:assessment_ids AS text[]))) AND
        (cardinality(CAST(:topic_ids AS text[]))=0 OR EXISTS (
            SELECT 1 FROM jsonb_array_elements_text(question->'concept_ids') topic(value)
            WHERE topic.value=ANY(CAST(:topic_ids AS text[]))))
), page AS (
    SELECT * FROM filtered ORDER BY catalog_order LIMIT 30 OFFSET :offset
), assessment_facets AS (
    SELECT assessment_id, assessment_title, min(catalog_order) first_seen
    FROM catalog GROUP BY assessment_id, assessment_title
), topic_facets AS (
    SELECT DISTINCT ON (topic.value) topic.value id, catalog_order first_seen,
        topic.position first_position
    FROM catalog CROSS JOIN LATERAL jsonb_array_elements_text(question->'concept_ids')
        WITH ORDINALITY topic(value, position)
    ORDER BY topic.value, catalog_order, topic.position
)
SELECT (SELECT count(*) FROM filtered) total,
    (SELECT count(*) FROM filtered WHERE NOT resolved) active_count,
    coalesce((SELECT jsonb_agg(jsonb_build_object(
        'id', assessment_id || ':' || question_id, 'assessment_id', assessment_id,
        'assessment_title', assessment_title, 'attempt_id', attempt_id,
        'grade_revision', grade_revision, 'question_id', question_id,
        'prompt', question->>'prompt', 'context', coalesce(question->>'context',''),
        'topic_ids', question->'concept_ids', 'score', score, 'marks', marks,
        'feedback', feedback, 'answer', answer, 'answer_mode', question->'answer_mode',
        'options', CASE WHEN jsonb_typeof(question->'options')='array' THEN question->'options' ELSE '[]'::jsonb END,
        'occurrences', occurrences, 'resolved', resolved, 'occurred_at', occurred_at,
        'priority', CASE WHEN occurrences>1 THEN 'Repeated mistake' WHEN score=0 THEN 'Incorrect answer' ELSE 'Partial answer' END,
        'topics', coalesce((SELECT jsonb_agg(jsonb_build_object('id', topic.value,
            'name', coalesce(c.canonical_name, 'Learning topic')) ORDER BY topic.position)
            FROM jsonb_array_elements_text(question->'concept_ids') WITH ORDINALITY topic(value, position)
            LEFT JOIN concept c ON c.id=topic.value), '[]'::jsonb)
        ) ORDER BY catalog_order) FROM page), '[]'::jsonb) items,
    coalesce((SELECT jsonb_agg(jsonb_build_object('id', assessment_id, 'title', assessment_title)
        ORDER BY first_seen) FROM assessment_facets), '[]'::jsonb) assessments,
    coalesce((SELECT jsonb_agg(jsonb_build_object('id', f.id, 'name', coalesce(c.canonical_name,'Learning topic'))
        ORDER BY f.first_seen, f.first_position, f.id) FROM topic_facets f LEFT JOIN concept c ON c.id=f.id), '[]'::jsonb) topics
""")


def page(repository, owner, assessment_ids=(), topic_ids=(), offset=0):
    with repository.sessions() as session:
        result = dict(session.execute(PAGE, dict(owner=owner, assessment_ids=list(assessment_ids),
            topic_ids=list(topic_ids), offset=offset)).mappings().one())
    # Match the existing Python ISO representation used by clients and exports.
    from datetime import datetime
    for item in result['items']:
        item['occurred_at'] = datetime.fromisoformat(item['occurred_at']).isoformat()
    result['next_offset'] = offset+30 if offset+30 < result['total'] else None
    return result
