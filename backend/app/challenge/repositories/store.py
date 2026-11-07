"""Owner-transaction hooks. No provider calls or lifetime evidence scans."""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,update,or_,func,literal
from sqlalchemy.dialects.postgresql import insert,JSONB
from app.core.exceptions import AppError
from app.core.config import settings
from .tables import choices,outcomes,families,states,controls
from ..policy import POLICY,WINDOW,DAYS,evaluate,scope_key


def source(repository,session,owner,kind,identifier,conversation=None):
    if kind=='draft':
        from app.assessments.repositories.chat import ChatAssessmentRepository
        row=ChatAssessmentRepository(repository)._draft(session,owner,str(identifier))
        if conversation and row['conversation_id']!=conversation:
            raise AppError('ASSESSMENT_DRAFT_NOT_FOUND','This assessment is not in the current chat.',404)
        if row['assessment_id']:return repository._assessment(session,owner,row['assessment_id'])
        return row['payload']
    return repository._assessment(session,owner,str(identifier))


def register_choice(repository,session,owner,request,job):
    if request.challenge_choice_id is None:return
    from app.chat.repositories.tables import messages,turns
    from ..schemas import ChallengeAction
    if str(request.challenge_choice_id)!=job['source_turn_id']:
        raise AppError('CHALLENGE_ACTION_REQUIRED','Use the difficulty action on the original assessment.',422)
    raw=session.scalar(select(messages.c.metadata['challenge_action']).join(turns,
        (turns.c.conversation_id==messages.c.conversation_id)&(turns.c.user_sequence==messages.c.sequence)&(turns.c.learner_id==messages.c.learner_id)).where(
            turns.c.id==job['source_turn_id'],turns.c.learner_id==owner,turns.c.state=='RUNNING'))
    action=ChallengeAction.model_validate(raw)
    identifier=str(request.revision_draft_id or request.revision_assessment_id)
    kind='draft' if request.revision_draft_id else 'assessment'
    if kind!=action.source_kind or identifier!=str(action.source_id) or request.expected_source_revision!=action.expected_revision or request.challenge_direction!=action.direction:
        raise AppError('CHALLENGE_SOURCE_CHANGED','The difficulty action source changed.',409)
    original=source(repository,session,owner,action.source_kind,identifier,job['conversation_id'])
    if original['revision']!=action.expected_revision:
        raise AppError('REVISION_CONFLICT','This assessment changed. Refresh before adjusting difficulty.',409)
    from app.assessments.quality import answerable
    answerable(original)
    if original['context_id']!=request.context_id:raise AppError('CHALLENGE_CONTEXT','Keep the original learning context.',409)
    session.execute(choices.insert().values(learner_id=owner,id=str(request.challenge_choice_id),
        context_id=original['context_id'],family=(original.get('preferences') or {}).get('challenge_family') or original['id'],
        direction=action.direction,source_kind=action.source_kind,source_id=identifier,source_revision=action.expected_revision,
        job_id=job['id'],conversation_id=job['conversation_id'],created_at=repository.clock(),
        payload=dict(baseline=sum(q['difficulty'] for q in original['questions'])/len(original['questions']),
            operation_id=str(request.client_request_id),
            source_items=[{key:q.get(key) for key in ('difficulty','concept_ids','answer_mode')} for q in original['questions']],
            source_prompts=[__import__('hashlib').sha256(q['prompt'].strip().casefold().encode()).hexdigest() for q in original['questions']])))


def publication_preferences(repository,session,owner,request,paper):
    preferences=dict(paper['preferences'],challenge_family=paper['id'],language=request.language)
    if request.revision_draft_id or request.revision_assessment_id:
        parent=source(repository,session,owner,'draft' if request.revision_draft_id else 'assessment',
            request.revision_draft_id or request.revision_assessment_id)
        if request.expected_source_revision is not None and parent['revision']!=request.expected_source_revision:
            raise AppError('REVISION_CONFLICT','The source changed while this version was being generated.',409)
        from app.assessments.quality import answerable
        answerable(parent)
        preferences['challenge_family']=(parent.get('preferences') or {}).get('challenge_family') or parent['id']
    if request.challenge_choice_id:
        row=session.execute(select(choices).where(choices.c.learner_id==owner,choices.c.id==str(request.challenge_choice_id))).mappings().first()
        if not row:raise AppError('CHALLENGE_ACTION_REQUIRED','Difficulty action receipt unavailable.',409)
        if row['payload']['operation_id']!=str(request.client_request_id) or row['assessment_id'] not in (None,paper['id']):
            raise AppError('CHALLENGE_ACTION_CONFLICT','This difficulty action already belongs to another version.',409)
        prompts={__import__('hashlib').sha256(q['prompt'].strip().casefold().encode()).hexdigest() for q in paper['questions']}
        changed=bool(prompts-set(row['payload']['source_prompts']))
        actual=sum(q['difficulty'] for q in paper['questions'])/len(paper['questions'])
        delta=actual-row['payload']['baseline']
        verified=changed and (delta>=.02 if row['direction']=='harder' else delta<=-.02)
        payload=dict(row['payload'],direction_verified=verified,actual_difficulty=actual)
        session.execute(update(choices).where(choices.c.learner_id==owner,choices.c.id==row['id']).values(
            served_at=repository.clock(),assessment_id=paper['id'],payload=payload))
        preferences.update(challenge_choice_id=row['id'],challenge_family=row['family'])
    return preferences


def refresh(session,owner,key,dimensions,now):
    refresh_many(session,owner,{key:dimensions},now)


def refresh_many(session,owner,scopes,now):
    if not scopes:return
    from sqlalchemy import union_all
    if len(scopes)>64:
        items=list(scopes.items())
        for offset in range(0,len(items),64):refresh_many(session,owner,dict(items[offset:offset+64]),now)
        return
    filters=or_(*[(controls.c.context_id==value['context_id'])&(controls.c.concept_id==value['concept_id']) for value in scopes.values()])
    resets={(row['context_id'],row['concept_id']):row['reset_at'] for row in session.execute(
        select(controls).where(controls.c.learner_id==owner,filters)).mappings()}
    windows=[]
    for key,dimensions in scopes.items():
        cutoff=max(now-timedelta(days=DAYS),resets.get((dimensions['context_id'],dimensions['concept_id']),datetime(1970,1,1,tzinfo=timezone.utc)))
        window=select(literal(key).label('scope_key'),families.c.payload,families.c.occurred_at).where(
            families.c.learner_id==owner,families.c.scope_key==key,families.c.valid.is_(True),families.c.occurred_at>cutoff)
        windows.append(select(window.order_by(families.c.occurred_at.desc(),families.c.family.desc()).limit(WINDOW).subquery()))
    grouped=defaultdict(list)
    for row in session.execute(union_all(*windows)).mappings():grouped[row['scope_key']].append(row)
    values=[]
    for key,dimensions in scopes.items():
        rows=grouped[key]
        values.append(dict(learner_id=owner,scope_key=key,**dimensions,updated_at=now,
            expires_at=min((row['occurred_at'] for row in rows),default=now)+timedelta(days=DAYS),
            policy=POLICY,payload=evaluate([row['payload'] for row in rows])))
    statement=insert(states).values(values)
    session.execute(statement.on_conflict_do_update(index_elements=['learner_id','scope_key'],
        set_={column.name:statement.excluded[column.name] for column in states.c if column.name not in ('learner_id','scope_key')}))


def observe(repository,session,job,receipt):
    paper,attempt,owner=job['assessment'],job['attempt'],job['owner']
    choice_id=(paper.get('preferences') or {}).get('challenge_choice_id')
    if not choice_id:return
    choice=session.execute(select(choices).where(choices.c.learner_id==owner,choices.c.id==choice_id)).mappings().first()
    if not choice or choice['assessment_id']!=paper['id']:return  # Copied papers are not new interventions.
    source_valid=True
    try:
        original=source(repository,session,owner,choice['source_kind'],choice['source_id'])
        from app.assessments.quality import answerable
        answerable(paper)
        answerable(original)
        source_valid=original['revision']==choice['source_revision']
    except AppError:source_valid=False
    from app.assessments.repositories.tables import prediction_snapshots
    snapshots={row['question_id']:row for row in session.execute(select(prediction_snapshots).where(
        prediction_snapshots.c.learner_id==owner,prediction_snapshots.c.attempt_id==job['id'])).mappings()}
    accepted={(row.get('question_id'),row['concept_id']) for row in receipt or [] if row.get('accepted')}
    grades={row['question_id']:row for row in attempt['grades'] or []}
    groups=defaultdict(list)
    for question in paper['questions']:
        for concept in question['concept_ids']:
            dimensions=dict(context_id=paper['context_id'],concept_id=concept,language=question.get('language','und'),
                answer_mode=question.get('answer_mode') or 'text')
            key=scope_key(**dimensions)
            grade=grades.get(question['id'],{})
            score=(grade.get('concept_grades') or {}).get(concept,{})
            snapshot=snapshots.get(question['id'])
            baselines=[item['difficulty'] for item in choice['payload']['source_items'] if concept in item['concept_ids']
                and (item.get('answer_mode') or 'text')==dimensions['answer_mode']]
            delta=question['difficulty']-sum(baselines)/len(baselines) if baselines else 0
            supported_direction=bool(baselines) and (delta>=.02 if choice['direction']=='harder' else delta<=-.02)
            eligible=(source_valid and choice['payload'].get('direction_verified') and dimensions['language'] in ('en','ar')
                and supported_direction and (not question.get('options') or question.get('validation',{}).get('semantic_review') in ('model_cross_checked','trusted_correction')
                    and question.get('validation',{}).get('challenge_change_verified'))
                and __import__('hashlib').sha256(question['prompt'].strip().casefold().encode()).hexdigest() not in choice['payload']['source_prompts']
                and attempt['attempt_number']==1 and attempt.get('assistance')=='independent'
                and not (paper.get('practice_lineage') or {}).get('known_exposure')
                and snapshot and snapshot['first_exposure'] and (question['id'],concept) in accepted
                and min(grade.get('confidence',0),score.get('confidence',0))>=.8
                and question.get('validation',{}).get('state')!='invalidated')
            groups[(key,tuple(dimensions.items()))].append((question,score,snapshot,bool(eligible)))
    keys=[key for key,_ in groups]
    existing=dict(session.execute(select(outcomes.c.scope_key,outcomes.c.payload).where(outcomes.c.learner_id==owner,
        outcomes.c.attempt_id==job['id'],outcomes.c.grade_revision==job['grade_revision'])).all())
    current_families={row['scope_key']:row for row in session.execute(select(families).where(families.c.learner_id==owner,
        families.c.family==choice['family'],families.c.scope_key.in_(keys))).mappings()}
    new_events=[];updates=[];scopes={}
    for (key,items),group in groups.items():
        if key in existing:
            # Source withdrawals live in effective families. A replay cannot
            # rewrite the original observation or revive its withdrawn support.
            continue
        dimensions=dict(items)
        qualified={row[2]['content_hash']:row for row in group if row[3]}
        valid=len(qualified)>=1
        marks=sum(row[1].get('max_score',0) for row in qualified.values())
        score=sum(row[1].get('score',0) for row in qualified.values())/marks if marks else 0
        payload=dict(direction=choice['direction'],score=score,items=len(qualified),session=f"{choice['conversation_id']}:{attempt['submitted_at'].date().isoformat()}",
            **dimensions,eligible=valid,exclusions=[] if valid else ['insufficient_independent_verified_items'])
        values=dict(learner_id=owner,attempt_id=job['id'],grade_revision=job['grade_revision'],scope_key=key,
            assessment_id=paper['id'],choice_id=choice_id,family=choice['family'],occurred_at=attempt['submitted_at'],payload=payload)
        new_events.append(values)
        current=current_families.get(key)
        stamp=(attempt['submitted_at'],str(job['id']),job['grade_revision'])
        if current and stamp<(current['occurred_at'],current['attempt_id'],current['grade_revision']):continue
        if not valid and current and current['valid'] and current['attempt_id']!=job['id']:continue
        family=dict(learner_id=owner,scope_key=key,family=choice['family'],assessment_id=paper['id'],attempt_id=job['id'],
            grade_revision=job['grade_revision'],occurred_at=attempt['submitted_at'],valid=valid,payload=payload)
        updates.append(family);scopes[key]=dimensions
    if new_events:session.execute(outcomes.insert().values(new_events))
    if updates:
        statement=insert(families).values(updates)
        session.execute(statement.on_conflict_do_update(index_elements=['learner_id','scope_key','family'],
            set_={column.name:statement.excluded[column.name] for column in families.c if column.name not in ('learner_id','scope_key','family')}))
    refresh_many(session,owner,scopes,repository.clock())


def invalidate(repository,session,owner,assessment_id):
    from app.assessments.repositories.tables import chat_drafts
    draft_ids=select(chat_drafts.c.id).where(chat_drafts.c.learner_id==owner,chat_drafts.c.assessment_id==assessment_id)
    affected=select(choices.c.family).where(choices.c.learner_id==owner,or_(choices.c.assessment_id==assessment_id,
        choices.c.source_id==assessment_id,choices.c.source_id.in_(draft_ids)))
    rows=session.execute(update(families).where(families.c.learner_id==owner,
        or_(families.c.assessment_id==assessment_id,families.c.family==assessment_id,families.c.family.in_(affected))).values(valid=False)
        .returning(families.c.scope_key,families.c.payload)).all()
    scopes=[dict(key=key,dimensions={name:payload[name] for name in ('context_id','concept_id','language','answer_mode')})
        for key,payload in dict(rows).items()]
    if scopes:
        from sqlalchemy import delete
        session.execute(delete(states).where(states.c.learner_id==owner,states.c.scope_key.in_([item['key'] for item in scopes])))
        from .worker import enqueue
        enqueue(repository,session,owner,'refresh',f"{assessment_id}:{repository.clock().isoformat()}",dict(scopes=scopes))


def projection_column(owner,concept_column,context_column=None):
    from app.core.config import settings
    query=select(func.jsonb_agg(states.c.payload.op('||')(func.jsonb_build_object('context_id',states.c.context_id,
        'language',states.c.language,'answer_mode',states.c.answer_mode)))).select_from(states.join(controls,
            (controls.c.learner_id==states.c.learner_id)&(controls.c.context_id==states.c.context_id)&(controls.c.concept_id==states.c.concept_id))).where(
        states.c.learner_id==owner,states.c.concept_id==concept_column,states.c.policy==POLICY,states.c.expires_at>func.now(),
        controls.c.enabled.is_(True),states.c.updated_at>=controls.c.reset_at,
        states.c.payload['offset'].as_float()!=0,literal(settings.learner_challenge_adaptation_enabled),literal(settings.learner_personalization_enabled))
    if context_column is not None:query=query.where(states.c.context_id==context_column)
    return func.coalesce(query.correlate_except(states,controls).scalar_subquery(),literal([],type_=JSONB)).label('challenge_preferences')
