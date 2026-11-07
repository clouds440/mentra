import {test,expect} from '@playwright/test';
import {workspace} from './renovation-fixtures';

async function preferences(page:import('@playwright/test').Page,loseFirstResponse=false){
  await workspace(page);
  let enabled=false,revision=0,resets=0;
  const writes:Record<string,unknown>[]=[],receipts=new Map<string,unknown>();
  await page.route('**/api/v1/learner/challenge-preferences*',async route=>{
    const request=route.request();
    if(request.method()==='POST'){
      const body=request.postDataJSON();writes.push(body);
      if(receipts.has(body.client_request_id))return route.fulfill({json:receipts.get(body.client_request_id)});
      if(body.expected_revision!==revision)return route.fulfill({status:409,json:{error:{code:'REVISION_CONFLICT',message:'Refresh challenge preferences.'}}});
      enabled=body.enabled;revision++;if(body.reset)resets++;
      const result={revision,enabled};receipts.set(body.client_request_id,result);
      if(loseFirstResponse&&writes.length===1)return route.abort('connectionreset');
      return route.fulfill({json:result});
    }
    return route.fulfill({json:{items:[{scope_key:'scope',context_id:'physics',concept_id:'skill',name:'Net force',
      language:'en',answer_mode:'single_choice',enabled,control_revision:revision,global_enabled:true,
      mode:'shadow',offset:resets?0:.1,families:resets?0:3,flags:[]}],next_cursor:null}});
  });
  await page.goto('/settings');
  const section=page.getByRole('region',{name:'Challenge preferences'});
  await expect(section.getByText('Net force',{exact:true})).toBeVisible();
  return {section,writes,resets:()=>resets};
}

test('challenge preferences opt in, survive reload, and reset with the standard titled modal',async({page})=>{
  const state=await preferences(page);
  const toggle=state.section.getByRole('switch',{name:'Use these suggestions for Net force'});
  await expect(toggle).not.toBeChecked();await toggle.click();await expect(toggle).toBeChecked();
  await page.reload();await expect(toggle).toBeChecked();
  await state.section.getByRole('button',{name:'Reset preference',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Reset this challenge preference?'});
  await expect(dialog.locator('.dialog-chrome').getByRole('heading')).toHaveText('Reset this challenge preference?');
  await dialog.getByRole('button',{name:'Reset preference',exact:true}).click();
  await expect(dialog).toHaveCount(0);await expect(state.section.getByText('Still collecting reliable results.')).toBeVisible();
  expect(state.resets()).toBe(1);expect(state.writes[1]).toMatchObject({reset:true,expected_revision:1,enabled:true});
});

test('lost save responses retry with the same operation and do not duplicate resets',async({page})=>{
  const state=await preferences(page,true);
  await state.section.getByRole('button',{name:'Reset preference',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Reset preference',exact:true}).click();
  await expect(state.section.getByRole('alert')).toBeVisible();
  await dialog.getByRole('button',{name:'Reset preference',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  expect(state.writes).toHaveLength(2);
  expect(state.writes[0].client_request_id).toBe(state.writes[1].client_request_id);
  expect(state.resets()).toBe(1);
});

test('an unavailable preference service leaves the settings and chat usable',async({page})=>{
  await workspace(page);
  await page.route('**/api/v1/learner/challenge-preferences*',route=>route.fulfill({status:503,json:{error:{code:'UNAVAILABLE',message:'Preferences temporarily unavailable.'}}}));
  await page.goto('/settings');
  await expect(page.getByRole('region',{name:'Challenge preferences'}).getByRole('alert')).toBeVisible();
  await expect(page.getByRole('button',{name:'Edit profile',exact:true})).toBeEnabled();
  await page.goto('/chat/polish-chat');await expect(page.getByRole('textbox',{name:'Ask Mentra anything',exact:true})).toBeVisible();
});
