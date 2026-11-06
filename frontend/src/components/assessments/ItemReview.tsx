import { useEffect,useId,useRef,useState } from 'react';
import { Flag } from 'lucide-react';
import { Button,Dialog,IconButton,Select,Textarea } from '../ui';
import { assessments } from '../../services/assessments';
import type { Assessment,AssessmentQuestion,AssessmentReportReason } from '../../types/assessments';

const reasons: {value:AssessmentReportReason;label:string}[] = [
  {value:'wrong_answer',label:'The answer or explanation is wrong'},
  {value:'ambiguous',label:'The question is ambiguous'},
  {value:'answer_leak',label:'The question gives away the answer'},
  {value:'off_request',label:'Doesn’t match what I requested'},
  {value:'unhelpful',label:'Not useful for my learning'},
  {value:'difficulty_mismatch',label:'Difficulty doesn’t match my request'},
  {value:'missing_information',label:'Missing information or impossible to answer'},
];

export function useItemQuarantine(assessment:Assessment) {
  const [reported,setReported]=useState(false);
  useEffect(()=>{
    const receive=(event:Event)=>{ const value=(event as CustomEvent<Assessment>).detail;
      if(value?.id===assessment.id) setReported(value.questions.some(q=>q.validation?.state==='invalidated')); };
    window.addEventListener('mentra:assessment-reviewed',receive);
    return ()=>window.removeEventListener('mentra:assessment-reviewed',receive);
  },[assessment.id]);
  return reported || assessment.questions.some(q=>q.validation?.state==='invalidated');
}

export function ItemReview({assessment,question,ensureSaved}:{assessment:Assessment;question:AssessmentQuestion;ensureSaved?:(signal:AbortSignal)=>Promise<Assessment>}) {
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [reason,setReason]=useState<AssessmentReportReason>('wrong_answer'),[details,setDetails]=useState('');
  const heading=useId(),operation=useRef(crypto.randomUUID()),active=useRef<AbortController|null>(null);
  useEffect(()=>()=>active.current?.abort(),[]);
  useEffect(()=>{
    setOpen(false);setReason('wrong_answer');setDetails('');setError('');operation.current=crypto.randomUUID();
  },[assessment.id,question.id]);
  async function report(){
    if(busy) return;
    const controller=new AbortController();active.current=controller;setBusy(true);setError('');
    try {
      const saved=ensureSaved ? await ensureSaved(controller.signal) : assessment;
      const value=await assessments.reportItem(saved,question.id,reason,operation.current,controller.signal,details);
      if(!controller.signal.aborted){
        window.dispatchEvent(new CustomEvent('mentra:assessment-reviewed',{detail:value}));
        setOpen(false);operation.current=crypto.randomUUID();
      }
    } catch(error){if(!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not report this question. Try again.');}
    finally{if(!controller.signal.aborted) setBusy(false);}
  }
  return <><IconButton aria-label="Report question" title="Report question" onClick={()=>setOpen(true)}><Flag size={14} aria-hidden="true" /></IconButton>
    {open && <Dialog title="Report this question" open busy={busy} onDismiss={()=>setOpen(false)} aria-labelledby={heading} className="max-w-md">
      <p className="mb-3 text-sm text-muted">Your report is saved for review. Scoring stays paused until a correction is approved. Your answers and earlier results are preserved.</p>
      <label className="block space-y-2 text-sm"><span>What needs review?</span>
        <Select value={reason} disabled={busy} onChange={event=>{setReason(event.target.value as AssessmentReportReason);operation.current=crypto.randomUUID();}}>
          {reasons.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
      </label>
      <label className="mt-4 block space-y-2 text-sm"><span>Anything else we should know? (optional)</span>
        <Textarea value={details} disabled={busy} rows={3} maxLength={2000} onChange={event=>{setDetails(event.target.value);operation.current=crypto.randomUUID();}} />
      </label>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      <div className="mt-5 flex flex-wrap gap-2"><Button loading={busy} onClick={()=>void report()}>Report & pause scoring</Button><Button variant="ghost" disabled={busy} onClick={()=>setOpen(false)}>Cancel</Button></div>
    </Dialog>}</>;
}

export function QuarantineNotice(){return <p role="alert" className="text-sm text-warning">A question needs review. Scoring is paused; your answers are kept.</p>;}
