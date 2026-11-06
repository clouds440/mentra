import {test,expect,type Page} from '@playwright/test';
import {workspace} from './renovation-fixtures';

async function observations(page:Page){
  await workspace(page);
  let rows=[{id:'source-observation',turn_id:'source-turn',context_id:null,concept_id:null,kind:'struggle',label:'Chain rule',topic:'Calculus',quote:'أنا محتار في قاعدة السلسلة.',source_revision:'source-hash-1',source_kind:'user',status:'pending',observed_at:'2026-11-06T00:00:00Z',details:{reviewed:false,scoring:'not_admitted'}}];
  let reads=0;const writes:{path:string;body:Record<string,unknown>|null}[]=[];
  await page.route('**/api/v1/learning/signals**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(request.method()==='GET'){reads++;return route.fulfill({json:{items:rows,next_offset:null}});}
    writes.push({path,body:request.method()==='DELETE'?null:request.postDataJSON()});
    if(request.method()==='DELETE'){rows=[];return route.fulfill({status:204});}
    rows=rows.map(item=>({...item,status:'active',context_id:'context-1',concept_id:'existing-chain-rule',details:{reviewed:true,scoring:'not_admitted'}}));
    return route.fulfill({json:{id:'source-observation',status:'active',scoring:'not_admitted'}});
  });
  await page.route('**/api/v1/learning/understanding?**',route=>route.fulfill({json:{items:[{concept_id:'existing-chain-rule',name:'Chain rule',context_id:'context-1',mastery:null,estimate_confidence:null,retention_confidence:null,knowledge_status:'insufficient_evidence',misconceptions:[]}],total:1,total_concepts:1,limit:10,offset:0,generated_at:'2026-11-06T00:00:00Z'}}));
  await page.route('**/api/v1/learning/signal-captures**',route=>{
    if(route.request().method()==='POST'){writes.push({path:new URL(route.request().url()).pathname,body:null});return route.fulfill({json:{state:'queued'}});}
    return route.fulfill({json:{items:[{turn_id:'source-turn',conversation_id:'polish-chat',title:'Calculus work',disposition:'capture_failed'}]}});
  });
  await page.goto('/progress');
  return {reads:()=>reads,writes};
}

test('chat observations load on demand, require deliberate scope, and never submit a mastery score',async({page})=>{
  const state=await observations(page);const open=page.getByRole('button',{name:'Observations from your chats',exact:true});
  await expect(open).toBeVisible();expect(state.reads()).toBe(0);await open.click();
  await expect(page.getByText('Needs review',{exact:false})).toBeVisible();await expect(page.getByText('أنا محتار في قاعدة السلسلة.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Review & link skill'}).click();const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('button',{name:'Confirm & link'})).toBeDisabled();
  await dialog.getByRole('combobox',{name:'Observation learning area'}).click();await page.getByRole('option',{name:'A broader learning context with a longer descriptive name',exact:true}).click();
  await dialog.getByRole('combobox',{name:'Observation skill'}).click();await page.getByRole('option',{name:'Chain rule',exact:true}).click();await dialog.getByRole('button',{name:'Confirm & link'}).click();
  await expect(dialog).toHaveCount(0);expect(state.writes[0].body).toEqual({context_id:'context-1',concept_id:'existing-chain-rule',source_revision:'source-hash-1'});
  await page.getByRole('button',{name:'Withdraw',exact:true}).click();await expect(page.getByText('No matching observations yet.')).toBeVisible();
});

test('reviewed new skills and failed-capture recovery remain explicit actions',async({page})=>{
  const state=await observations(page);await page.getByRole('button',{name:'Observations from your chats',exact:true}).click();
  await page.getByRole('button',{name:'Review & link skill'}).click();const dialog=page.getByRole('dialog');
  await dialog.getByRole('combobox',{name:'Observation learning area'}).click();await page.getByRole('option',{name:'A broader learning context with a longer descriptive name',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Confirm & link'})).toBeDisabled();
  await dialog.getByRole('combobox',{name:'Observation skill'}).click();await page.getByRole('option',{name:'Create a reviewed skill',exact:true}).click();await dialog.getByLabel('Specific skill name').fill('Differentiate a composition');
  await dialog.getByRole('button',{name:'Confirm & link'}).click();
  expect(state.writes[0].body).toEqual({context_id:'context-1',new_label:'Differentiate a composition',source_revision:'source-hash-1'});
  await page.getByRole('button',{name:'Capture recovery',exact:true}).click();await page.getByRole('button',{name:'Retry capture',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Capture queued'})).toBeVisible();
  expect(state.writes.at(-1)?.path).toBe('/api/v1/learning/signal-captures/source-turn/retry');
});
