import { Download } from 'lucide-react';
import { Button } from '../ui';
import type { Assessment } from '../../types/assessments';
import { selectedAnswer } from './AssessmentPaper';
import { useAssessmentEvaluation } from '../../stores/assessmentSession';
import { assessmentSession } from '../../stores/assessmentSession';
import { memo,useEffect,useState } from 'react';
import { useAuth } from '../auth/AuthProvider';

export function DraftStorageNotice({assessment,answers}:{assessment:Assessment;answers:Record<string,string>}){
  const unavailable=useAssessmentEvaluation().draftStorageUnavailable;
  return unavailable ? <div role="status" className="space-y-1 text-xs text-muted"><p>Browser recovery storage is unavailable. Keep this tab open or download your answers before leaving.</p><DownloadAnswers assessment={assessment} answers={answers} /></div> : null;
}

export function DownloadAnswers({assessment,answers}:{assessment:Assessment;answers:Record<string,string>}){
  return <Button variant="ghost" size="sm" onClick={()=>downloadAnswers(assessment,answers)}><Download size={14} aria-hidden="true" />Download my answers</Button>;
}

function downloadAnswers(assessment:Assessment,answers:Record<string,string>){
    const text=assessment.questions.map((question,index)=>`Question ${index+1}\n${question.prompt}\n\nYour answer:\n${selectedAnswer(question,answers[question.id])}`).join('\n\n---\n\n');
    const url=URL.createObjectURL(new Blob([`${assessment.title}\n\n${text}`],{type:'text/plain;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download='mentra-local-answers.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export const RecoveryAnswers=memo(function RecoveryAnswers({assessmentId}:{assessmentId:string}){
  const {identity}=useAuth();const owner=identity?.learner_id;
  const [keys,setKeys]=useState(()=>assessmentSession.recoveryKeys(owner,assessmentId));
  useEffect(()=>{setKeys(assessmentSession.recoveryKeys(owner,assessmentId));const receive=(event:Event)=>{if((event as CustomEvent<string>).detail===assessmentId)setKeys(assessmentSession.recoveryKeys(owner,assessmentId));};window.addEventListener('mentra:assessment-recovery',receive);return ()=>window.removeEventListener('mentra:assessment-recovery',receive);},[owner,assessmentId]);
  if(!keys.length)return null;
  return <details className="text-xs text-muted"><summary className="ui-disclosure cursor-pointer py-2">Recovered local answers ({keys.length})</summary><p className="py-2">These copies preserve your work from before an attempt changed elsewhere.</p>{keys.map((key,index)=><div key={key} className="flex flex-wrap gap-2"><Button variant="ghost" size="sm" onClick={()=>{const draft=assessmentSession.draft(owner,key);if(draft)downloadAnswers(draft.paper,draft.answers);}}>Download recovery {index+1}</Button><Button variant="ghost" size="sm" onClick={()=>{assessmentSession.forget(owner,key);setKeys(previous=>previous.filter(value=>value!==key));}}>Remove recovery {index+1}</Button></div>)}</details>;
});
