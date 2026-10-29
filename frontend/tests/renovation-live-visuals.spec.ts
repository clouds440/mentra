import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const width of [390, 1280]) test(`disclaimer stays visible while typing after a new reply at ${width}px`, async ({ page }) => {
  await page.setViewportSize({width, height: 800});
  const state = await workspace(page); await page.goto('/chat/polish-chat');
  const input = page.getByRole('textbox', {name:'Ask Mentra anything'});
  await input.fill('Explain gravity simply.');
  // Complete the fixture only after its POST has created the new running turn.
  const sent = page.waitForResponse(response => response.url().endsWith('/api/v1/conversations/turns') && response.request().method() === 'POST');
  await page.getByRole('button', {name:'Send message', exact:true}).click(); await sent;
  state.complete('Gravity pulls objects together.');
  await expect(page.getByRole('article', {name:'Mentra response'}).last()).toContainText('Gravity pulls objects together.');
  // The answer can paint before the turn's terminal state enables the composer.
  // pressSequentially does not wait for an enabled field, unlike fill.
  await expect(input).toBeEnabled();
  await expect(page.getByLabel('Chat disclaimer')).toBeInViewport();
  await page.waitForTimeout(150);
  await page.getByLabel('Chat disclaimer').evaluate(el => {
    const data = {running:true, samples:[] as {gap:number;h:number;css:string;top:number;footer:number;latest:number;latestTop:number}[]}; (window as unknown as {footerProbe:typeof data}).footerProbe=data;
    const sample = () => {if(!data.running)return; const pane=el.closest('[role="log"]')!; data.samples.push({gap:el.getBoundingClientRect().bottom-pane.getBoundingClientRect().bottom,h:pane.clientHeight,css:(pane as HTMLElement).style.getPropertyValue('--latest-turn-height'),top:pane.scrollTop,footer:el.getBoundingClientRect().height,latest:pane.querySelector('[data-latest-turn]')!.getBoundingClientRect().height,latestTop:pane.querySelector('[data-latest-turn]')!.getBoundingClientRect().top-pane.getBoundingClientRect().top}); requestAnimationFrame(sample);}; requestAnimationFrame(sample);
  });
  await input.pressSequentially('A draft with enough text to wrap. '.repeat(8), {delay:3});
  await input.fill(''); await input.pressSequentially('A short draft', {delay:10});
  await page.waitForTimeout(100);
  const samples = await page.evaluate(() => {const data=(window as unknown as {footerProbe:{running:boolean;samples:{gap:number;h:number;css:string;top:number;footer:number;latest:number;latestTop:number}[]}}).footerProbe;data.running=false;return data.samples;});
  expect(samples.length).toBeGreaterThan(5); expect(Math.max(...samples.map(item=>item.gap))).toBeLessThanOrEqual(1);
});

import { richChat } from './renovation-rich-fixtures';
import { chooseOption } from './select-helpers';
for (const type of ['LineChart','BarChart','AreaChart','ComposedChart','PieChart','RadarChart','ScatterChart']) test(`${type} local controls, reset and fullscreen`,async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  const chart={type,title:'Illustrative values',enableControls:true,xKey:'name',data:[{name:type==='ScatterChart'?1:'A',value:2},{name:type==='ScatterChart'?2:'B',value:4},{name:type==='ScatterChart'?3:'C',value:3}],series:[{dataKey:'value',name:'Value',...(type==='ComposedChart'?{type:'Bar'}:{})}]};
  const state=await richChat(page,'```recharts\n'+JSON.stringify(chart)+'\n```');await page.goto('/chat/polish-chat');
  await expect(page.getByRole('region',{name:'Chart controls'})).toBeVisible();await page.getByRole('button',{name:'View data',exact:true}).click();
  const cell=page.locator('.recharts-figure tbody tr').first().locator('td');
  await page.getByRole('button',{name:'Number',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Selected value',exact:true}).fill('12');await expect(cell).toHaveText('12');
  if(type==='ScatterChart'){await chooseOption(page.getByRole('combobox',{name:'Chart value',exact:true}),'name');await page.getByRole('spinbutton',{name:'Selected value',exact:true}).fill('5');await expect(page.locator('.recharts-figure tbody tr').first().locator('th')).toHaveText('5');await chooseOption(page.getByRole('combobox',{name:'Chart value',exact:true}),'value');}
  await page.getByRole('button',{name:'View source',exact:true}).click();await expect(page.locator('.recharts-figure pre')).toContainText('12');
  await page.getByRole('button',{name:'Show chart',exact:true}).click();
  if(type==='BarChart'){const [file]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download SVG',exact:true}).click()]);expect(await file.failure()).toBeNull();}
  await page.getByRole('button',{name:'Slider',exact:true}).click();
  await page.getByRole('slider',{name:'Adjust selected value'}).evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,'6');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});await expect(cell).toHaveText('6');
  await page.getByRole('button',{name:'Number',exact:true}).click();
  await page.getByRole('button',{name:'Reset',exact:true}).click();await expect(cell).toHaveText('2');expect(state.submissions).toHaveLength(0);
  await page.getByRole('button',{name:'Expand',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Expanded chart: Illustrative values'});
  await dialog.getByRole('spinbutton',{name:'Selected value',exact:true}).fill('8');await dialog.getByRole('button',{name:'Close',exact:true}).click();await expect(cell).toHaveText('8');
});
test('read-only defaults and invalid control flags stay safe',async({page})=>{
  const chart={type:'BarChart',title:'Canonical values',xKey:'name',data:[{name:'A',value:2}],series:[{dataKey:'value'}]};
  await richChat(page,'```recharts\n'+JSON.stringify(chart)+'\n```');await page.goto('/chat/polish-chat');await expect(page.locator('.recharts-wrapper')).toBeVisible();await expect(page.getByRole('region',{name:'Chart controls'})).toHaveCount(0);
  await richChat(page,'```recharts\n'+JSON.stringify({...chart,enableControls:'true'})+'\n```');await page.reload();await expect(page.getByRole('status').filter({hasText:'unsupported or invalid data'})).toBeVisible();
});
test('pie controls reject negative values and an empty total',async({page})=>{
  await richChat(page,'```recharts\n'+JSON.stringify({type:'PieChart',title:'Illustrative',enableControls:true,xKey:'name',data:[{name:'A',value:2}],series:[{dataKey:'value'}]})+'\n```');await page.goto('/chat/polish-chat');
  await page.getByRole('button',{name:'Number',exact:true}).click();
  const input=page.getByRole('spinbutton',{name:'Selected value',exact:true});await input.fill('-1');await expect(input).toHaveAttribute('aria-invalid','true');await input.fill('0');await expect(input).toHaveAttribute('aria-invalid','true');
  await page.getByRole('button',{name:'View data',exact:true}).click();await expect(page.locator('.recharts-figure tbody td')).toHaveText('2');
  await page.getByRole('button',{name:'Reset',exact:true}).click();await expect(input).toHaveValue('2');await expect(input).toHaveAttribute('aria-invalid','false');
});
test('images attach captions, expand, preserve linked sources and fail locally',async({page})=>{
  await page.route('https://images.example.org/photo.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="teal"/></svg>'}));
  await page.route('https://images.example.org/missing.jpg',route=>route.fulfill({status:404,body:'missing'}));
  await richChat(page,'Before.\n\n![Diagram](https://images.example.org/photo.svg "Attached caption")\n\n[![Other](https://images.example.org/photo.svg "Linked caption")](https://example.org/source)\n\n![Missing](https://images.example.org/missing.jpg "Caption remains")\n\n![Unsafe](http://localhost/private.png "Blocked")\n\nAfter.');await page.goto('/chat/polish-chat');
  const images=page.locator('figure.markdown-image');await expect(images).toHaveCount(4);await expect(images.first().locator('figcaption')).toHaveText('Attached caption');
  await images.first().getByRole('button').click();await expect(page.getByRole('dialog',{name:'Expanded image: Attached caption'})).toBeVisible();await page.keyboard.press('Escape');await expect(images.first().getByRole('button')).toBeFocused();
  await expect(images.nth(1).getByRole('link',{name:'Source'})).toHaveAttribute('href','https://example.org/source');await expect(images.nth(2)).toContainText('Image unavailable');await expect(images.nth(2).locator('figcaption')).toHaveText('Caption remains');await expect(images.nth(3).locator('img')).toHaveCount(0);await expect(page.locator('p figure')).toHaveCount(0);
});

for(const width of [375,768,1280]) test(`Events keep viewing and editing inside dialogs at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:850});await workspace(page);
  const event={id:'event-1',title:'Physics study session',description:'Review motion',kind:'study',status:'scheduled',revision:1,timezone:'UTC',local_date:'2026-11-01',starts_at:null,ends_at:null,context_id:null,reminder:{mode:'default'},reminder_state:'pending',reminder_due_at:null,bucket:'upcoming',origin:'manual'};
  await page.route('**/api/v1/events/page?*',route=>route.fulfill({json:{items:[event],next_cursor:null,detail:new URL(route.request().url()).searchParams.has('selected')?event:null,proposals:[],proposals_error:false}}));
  await page.goto('/progress?tab=events');
  const create=page.getByRole('button',{name:'New event',exact:true});await create.click();await expect(page.getByRole('dialog',{name:'New event',exact:true})).toBeVisible();await page.keyboard.press('Escape');await expect(create).toBeFocused();
  await page.getByRole('button',{name:/Physics study session/}).click();const detail=page.getByRole('dialog',{name:'Event details',exact:true});await expect(detail).toBeVisible();await expect(detail.getByRole('heading',{name:event.title})).toBeVisible();
  await detail.getByRole('button',{name:'Edit',exact:true}).click();await expect(page.getByRole('dialog',{name:'Edit event',exact:true})).toBeVisible();await expect(page.getByRole('dialog')).toHaveCount(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('typing preserves the reader position after scrolling up',async({page})=>{
  await workspace(page);await page.goto('/chat/polish-chat');const log=page.getByRole('log');await expect(page.getByLabel('Chat disclaimer')).toBeInViewport();
  await log.hover();await page.mouse.wheel(0,-500);await page.waitForTimeout(200);const top=await log.evaluate(el=>el.scrollTop);
  await page.getByRole('textbox',{name:'Ask Mentra anything'}).fill('Draft text that grows. '.repeat(30));
  expect(Math.abs(await log.evaluate(el=>el.scrollTop)-top)).toBeLessThan(2);await expect(page.getByLabel('Chat disclaimer')).not.toBeInViewport();
});
