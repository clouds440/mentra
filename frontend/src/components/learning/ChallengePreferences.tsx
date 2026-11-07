import { useCallback,useEffect,useRef,useState } from 'react';
import { Button,Dialog,Toggle } from '../ui';
import { useAuth } from '../auth/AuthProvider';
import { apiRequest } from '../../services/api';

interface Preference {
  scope_key:string;context_id:string;concept_id:string;name:string;language:string;answer_mode:string;
  enabled:boolean;control_revision:number;global_enabled:boolean;mode:string;offset:number;families:number;flags:string[];
}
interface Page {items:Preference[];next_cursor:string|null}
const base='/api/v1/learner/challenge-preferences';

export function ChallengePreferences(){
  const {identity}=useAuth();
  const [items,setItems]=useState<Preference[]>([]),[cursor,setCursor]=useState<string|null>(null);
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [reset,setReset]=useState<Preference|null>(null);
  const controller=useRef<AbortController|null>(null),sequence=useRef(0),locked=useRef(false);
  const operations=useRef(new Map<string,string>());
  const load=useCallback(async(after?:string)=>{
    const signal=controller.current?.signal;if(!signal)return;
    const current=++sequence.current;setLoading(true);
    try{
      const page=await apiRequest<Page>(`${base}${after?`?after=${encodeURIComponent(after)}`:''}`,{signal,cache:'no-store'});
      if(!Array.isArray(page.items))throw new Error('Challenge preferences are unavailable. Refresh to retry.');
      if(!signal.aborted&&current===sequence.current){setItems(previous=>after?[...previous,...page.items]:page.items);setCursor(page.next_cursor);setError('');}
    }catch(reason){if(!signal.aborted&&current===sequence.current)setError(reason instanceof Error?reason.message:'Could not load challenge preferences.');}
    finally{if(!signal.aborted&&current===sequence.current)setLoading(false);}
  },[]);
  useEffect(()=>{
    const active=new AbortController();controller.current=active;operations.current.clear();locked.current=false;setBusy(false);setReset(null);setItems([]);void load();
    const refresh=()=>{if(!locked.current)void load();};window.addEventListener('focus',refresh);
    return()=>{active.abort();window.removeEventListener('focus',refresh);};
  },[identity?.learner_id,load]);
  async function change(item:Preference,enabled:boolean,resetHistory=false){
    if(locked.current)return;
    locked.current=true;setBusy(true);setError('');
    const signal=controller.current!.signal;
    const value={context_id:item.context_id,concept_id:item.concept_id,enabled,reset:resetHistory,expected_revision:item.control_revision};
    const key=JSON.stringify(value);const id=operations.current.get(key)??crypto.randomUUID();operations.current.set(key,id);
    try{
      await apiRequest(base,{method:'POST',signal,body:JSON.stringify({...value,client_request_id:id})});
      if(!signal.aborted){operations.current.delete(key);setReset(null);await load();}
    }catch(reason){if(!signal.aborted)setError(reason instanceof Error?reason.message:'Could not save challenge preferences.');}
    finally{if(controller.current?.signal===signal){locked.current=false;if(!signal.aborted)setBusy(false);}}
  }
  return <section aria-label="Challenge preferences" className="space-y-4 border-t border-border pt-5">
    <div><h3 className="font-medium text-heading">Practice challenge</h3><p className="mt-2 text-sm leading-6 text-muted">Your easier/harder choices and qualifying results can guide future practice for the same skill, language and format. Your current choice always wins; this doesn’t change mastery.</p></div>
    {error&&<p role="alert" className="text-sm text-danger">{error} <Button size="sm" variant="ghost" disabled={loading} onClick={()=>void load()}>Refresh preferences</Button></p>}
    {loading&&!items.length?<p role="status" className="text-sm text-muted">Loading challenge preferences…</p>:!items.length&&!error?<p className="text-sm text-muted">Use Make easier or Make harder before an assessment. Suggestions need qualifying results from several different practice sets and sessions.</p>:items.map(item=><article key={item.scope_key} className="space-y-2 py-2">
      <h4 className="text-sm font-medium text-heading" dir="auto">{item.name}</h4>
      <p className="text-xs text-muted">{item.language==='en'?'English':item.language==='ar'?'Arabic':'Language unverified'} · {item.answer_mode==='text'?'Written':item.answer_mode==='multiple_choice'?'Multiple selection':'Multiple choice'} · {item.families} qualifying practice sets</p>
      <p className="text-xs text-muted">{!item.global_enabled?'Challenge personalization is paused.':item.mode==='expired'?'Waiting for fresh results.':item.offset>0?'Provisional fit: slightly harder practice.':item.offset<0?'Provisional fit: slightly easier practice.':'Still collecting reliable results.'}</p>
      {!!item.flags.length&&<p className="text-xs text-warning">Mixed or difficult results call for a diagnostic; they don’t establish the cause.</p>}
      <div className="flex flex-wrap items-center justify-between gap-3"><Toggle checked={item.enabled} disabled={busy||!item.global_enabled} label={<>Use these suggestions<span className="sr-only"> for {item.name}</span></>} onCheckedChange={checked=>void change(item,checked)}/><Button size="sm" variant="ghost" disabled={busy} onClick={()=>setReset(item)}>Reset preference</Button></div>
    </article>)}
    {cursor&&<Button size="sm" variant="ghost" disabled={loading||busy} onClick={()=>void load(cursor)}>More preferences</Button>}
    {reset&&<Dialog title="Reset this challenge preference?" open busy={busy} onDismiss={()=>setReset(null)} className="max-w-md"><p className="text-sm text-muted">Future suggestions for {reset.name} will start from new results. Your practice, grades and mastery are kept.</p><div className="mt-5 flex gap-2"><Button loading={busy} onClick={()=>void change(reset,reset.enabled,true)}>Reset preference</Button><Button variant="ghost" disabled={busy} onClick={()=>setReset(null)}>Cancel</Button></div></Dialog>}
  </section>;
}
