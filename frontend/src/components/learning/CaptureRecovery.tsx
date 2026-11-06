import { useEffect,useRef,useState } from 'react';
import { useNavigate } from 'react-router';
import { Button } from '../ui';
import { failedSignalCaptures,retrySignalCapture } from '../../services/learning';

export function CaptureRecovery(){
  const navigate=useNavigate();const [open,setOpen]=useState(false),[reload,setReload]=useState(0),[busy,setBusy]=useState('');
  const [items,setItems]=useState<Awaited<ReturnType<typeof failedSignalCaptures>>['items']|null>(null),[error,setError]=useState(''),[status,setStatus]=useState('');
  const active=useRef<AbortController|null>(null);useEffect(()=>()=>active.current?.abort(),[]);
  useEffect(()=>{if(!open)return;const controller=new AbortController();setError('');
    void failedSignalCaptures(controller.signal).then(value=>{if(!controller.signal.aborted)setItems(value.items);}).catch(()=>{if(!controller.signal.aborted)setError('Could not load capture recovery.');});
    return ()=>controller.abort();
  },[open,reload]);
  async function retry(turn:string){if(busy)return;const controller=new AbortController();active.current=controller;setBusy(turn);setError('');
    try{await retrySignalCapture(turn,controller.signal);if(!controller.signal.aborted){setItems(previous=>previous?.filter(item=>item.turn_id!==turn)??[]);setStatus('Capture queued. Refresh observations after it finishes.');}}
    catch(error){if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Could not queue capture.');}
    finally{if(!controller.signal.aborted)setBusy('');}
  }
  return <div className="space-y-2 text-xs text-muted"><Button variant="ghost" size="sm" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>Capture recovery</Button>{open&&<><p>Failed captures keep their chat source. Retrying resumes saved work without scoring chat mentions.</p>{status&&<p role="status">{status}</p>}{error&&<p role="alert" className="text-danger">{error}</p>}{items?.length===0&&<p>No failed captures.</p>}{items?.map(item=><div key={item.turn_id} className="flex flex-wrap items-center gap-2"><span>{item.title}</span><Button size="sm" variant="ghost" onClick={()=>navigate(`/chat/${item.conversation_id}`)}>Open chat</Button><Button size="sm" disabled={!!busy} loading={busy===item.turn_id} onClick={()=>void retry(item.turn_id)}>Retry capture</Button></div>)}<Button variant="ghost" size="sm" onClick={()=>setReload(value=>value+1)}>Refresh capture status</Button></>}</div>;
}
