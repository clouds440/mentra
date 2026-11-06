import { useEffect,useId,useRef,useState } from 'react';
import { useNavigate } from 'react-router';
import { Button,Dialog,Input,Select } from '../ui';
import { learningSignals,learningProgress,reviewLearningSignal,withdrawLearningSignal } from '../../services/learning';
import type { LearningSignal,LearningConcept } from '../../types/learning';
import type { LearningContext } from '../../types/rag';
import { CaptureRecovery } from './CaptureRecovery';

export function LearningObservations({contexts,context='',onReviewed}:{contexts:LearningContext[];context?:string;onReviewed:()=>void}){
  const navigate=useNavigate();const heading=useId();
  const [open,setOpen]=useState(false),[items,setItems]=useState<LearningSignal[]>([]),[next,setNext]=useState<number|null>(null);
  const [query,setQuery]=useState(''),[submittedQuery,setSubmittedQuery]=useState(''),[page,setPage]=useState(0),[reload,setReload]=useState(0);
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [review,setReview]=useState<LearningSignal|null>(null),[area,setArea]=useState(''),[skill,setSkill]=useState(''),[label,setLabel]=useState(''),[skills,setSkills]=useState<LearningConcept[]>([]),[search,setSearch]=useState('');
  const active=useRef<AbortController|null>(null);
  useEffect(()=>()=>active.current?.abort(),[]);
  useEffect(()=>{setPage(0);},[context,submittedQuery]);
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();setLoading(true);setError('');
    void learningSignals(controller.signal,context,submittedQuery,page).then(value=>{if(!controller.signal.aborted){setItems(value.items);setNext(value.next_offset);}})
      .catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Could not load observations.');})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[open,context,submittedQuery,page,reload]);
  useEffect(()=>{
    if(!review||!area){setSkills([]);return;}
    const controller=new AbortController();const timer=setTimeout(()=>{
      void learningProgress(controller.signal,search,0,area).then(value=>{if(!controller.signal.aborted)setSkills(value.items);})
        .catch(()=>{if(!controller.signal.aborted)setError('Could not search existing skills. Retry before creating a duplicate.');});
    },200);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[review,area,search]);
  async function apply(item:LearningSignal,withdraw=false){
    if(busy)return;setBusy(true);setError('');const controller=new AbortController();active.current=controller;
    try{
      if(withdraw)await withdrawLearningSignal(item.id,controller.signal);
      else await reviewLearningSignal(item,area,skill==='new'?{new_label:label.trim()}:{concept_id:skill},controller.signal);
      if(!controller.signal.aborted){setReview(null);setReload(value=>value+1);onReviewed();}
    }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Could not save this review. Your source observation is kept.');}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  return <section aria-label="Learning observations" className="space-y-3"><Button variant="ghost" onClick={()=>setOpen(value=>!value)} aria-expanded={open}>Observations from your chats</Button>{open&&<>
    <p className="max-w-2xl text-sm text-muted">Source-backed observations of topics you encountered, questions and work. These do not assign mastery scores. Review uncertain observations or link one to a skill in the right learning area.</p>
    <form className="flex gap-2" onSubmit={event=>{event.preventDefault();setSubmittedQuery(query.trim());}}><Input aria-label="Search learning observations" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Find a topic…"/><Button variant="secondary" type="submit">Search</Button></form>
    {loading&&<p role="status" className="text-xs text-muted">Loading observations…</p>}{error&&!review&&<p role="alert" className="text-sm text-danger">{error}<Button variant="ghost" size="sm" onClick={()=>setReload(value=>value+1)}>Retry</Button></p>}
    {!loading&&!items.length&&!error&&<p className="text-sm text-muted">No matching observations yet.</p>}
    <div className="space-y-5">{items.map(item=><article key={item.id} className="space-y-2"><div className="flex flex-wrap items-center gap-2"><h3 dir="auto" className="min-w-0 break-words text-sm font-medium text-heading">{item.label}</h3><span className="text-xs text-muted">{item.kind.replace('_',' ')} · {item.status==='pending'?'Needs review':item.details.reviewed?'Reviewed observation':'Unverified observation'}</span></div><blockquote dir="auto" className="whitespace-pre-wrap break-words text-sm text-muted">{item.quote}</blockquote><p className="text-xs text-subtle">{item.source_kind==='attachment'?'Attachment text':'Chat message'} · {new Date(item.observed_at).toLocaleDateString()}</p><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy} onClick={()=>{setReview(item);setArea(item.context_id??context);setLabel(item.label);setSkill(item.concept_id??'');setSearch(item.label);setError('');}}>Review & link skill</Button>{item.context_id&&<Button variant="ghost" size="sm" onClick={()=>navigate(`/assessments?tab=create&context=${encodeURIComponent(item.context_id!)}&topic=${encodeURIComponent(item.label)}`)}>Practise this</Button>}<Button size="sm" variant="ghost" disabled={busy} onClick={()=>void apply(item,true)}>Withdraw</Button></div></article>)}</div>
    <div className="flex gap-2"><Button variant="ghost" size="sm" disabled={page===0||loading} onClick={()=>setPage(value=>Math.max(0,value-20))}>Previous observations</Button><Button variant="ghost" size="sm" disabled={next===null||loading} onClick={()=>setPage(next!)}>Next observations</Button><Button variant="ghost" size="sm" onClick={()=>setReload(value=>value+1)}>Refresh observations</Button></div>
    <CaptureRecovery />
    {review&&<Dialog open busy={busy} onDismiss={()=>setReview(null)} aria-labelledby={heading} className="max-w-lg"><h2 id={heading} className="text-lg font-medium text-heading">Review this observation</h2><blockquote dir="auto" className="my-4 whitespace-pre-wrap break-words text-sm text-muted">{review.quote}</blockquote><div className="space-y-3"><label className="block space-y-1 text-xs text-muted"><span>Learning area</span><Select aria-label="Observation learning area" disabled={busy} value={area} onChange={event=>{setArea(event.target.value);setSkill('');}}><option value="">Choose a learning area</option>{contexts.map(value=><option key={value.context_id} value={value.context_id}>{value.name}</option>)}</Select></label><label className="block space-y-1 text-xs text-muted"><span>Find an existing skill</span><Input disabled={busy||!area} value={search} onChange={event=>setSearch(event.target.value)}/></label><Select aria-label="Observation skill" disabled={busy||!area} value={skill} onChange={event=>setSkill(event.target.value)}><option value="">Choose a skill or create one</option>{skill&&skill!=='new'&&!skills.some(value=>value.concept_id===skill)&&<option value={skill}>Current linked skill</option>}<option value="new">Create a reviewed skill</option>{skills.map(value=><option key={value.concept_id} value={value.concept_id}>{value.name}</option>)}</Select>{skill==='new'&&<label className="block space-y-1 text-xs text-muted"><span>Specific skill name</span><Input dir="auto" value={label} maxLength={200} disabled={busy} onChange={event=>setLabel(event.target.value)}/></label>}<p className="text-xs text-muted">Linking confirms the topic and source, not whether you have mastered it.</p>{error&&<p role="alert" className="text-sm text-danger">{error}</p>}<div className="flex gap-2"><Button loading={busy} disabled={!area||!skill||skill==='new'&&!label.trim()} onClick={()=>void apply(review)}>Confirm & link</Button><Button variant="ghost" disabled={busy} onClick={()=>setReview(null)}>Cancel</Button></div></div></Dialog>}
  </>}</section>;
}
