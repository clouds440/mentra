import { test,expect } from '@playwright/test';
import { assessmentFixture } from './fixtures/assessment';

test('same-attempt newer revision cannot replace dirty choices',async({page})=>{
  const state=await assessmentFixture(page,{existingAttempt:true});
  const choice=state.quiz.getByRole('radio').first();await choice.check();
  state.completeElsewhere(true);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('alert')).toContainText('Your answers are kept');
  await expect(choice).toBeChecked();await expect(choice).toBeDisabled();
  await expect(state.quiz.getByRole('button',{name:'Download my answers'})).toBeVisible();
  expect(state.writes).toEqual([]);
});

test('duplicate views preserve their own unfinished answers across reload',async({page})=>{
  const state=await assessmentFixture(page,{duplicate:true});
  await state.quiz.first().getByRole('radio').first().check();await state.quiz.first().getByRole('button',{name:'Next',exact:true}).click();
  await state.quiz.last().getByRole('radio').last().check();await page.reload();
  await expect(state.quiz.first().getByText(/Question 2 of 3/)).toBeVisible();
  await state.quiz.first().getByRole('button',{name:'Back',exact:true}).click();
  await expect(state.quiz.first().getByRole('radio').first()).toBeChecked();await expect(state.quiz.last().getByRole('radio').last()).toBeChecked();
  expect(state.writes).toEqual([]);
});

test('a new local draft survives reload after another view submits',async({page})=>{
  const state=await assessmentFixture(page,{delay:10});await state.quiz.getByRole('radio').first().check();
  state.completeElsewhere();await page.reload();
  await expect(page.getByRole('alert')).toContainText('Your answers are kept');
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();
  await expect(state.quiz.getByRole('radio').first()).toBeDisabled();
  await page.getByRole('button',{name:'Review saved attempt',exact:true}).click();
  await expect(page.getByRole('region',{name:'Assessment feedback'})).toBeVisible();
  await expect(page.getByText('Recovered local answers (1)',{exact:true})).toBeVisible();expect(state.writes).toEqual([]);
});

test('reviewing a saved revision keeps a downloadable recovery copy of local work',async({page})=>{
  const state=await assessmentFixture(page,{existingAttempt:true,delay:10});await state.quiz.getByRole('radio').first().check();
  state.completeElsewhere(true);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await page.getByRole('button',{name:'Review saved attempt',exact:true}).click();
  await expect(page.getByRole('region',{name:'Assessment feedback'})).toBeVisible();
  await page.getByText('Recovered local answers (1)',{exact:true}).click();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download recovery 1',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('mentra-local-answers.txt');
});

test('the Assessments page serves a completed quiz before delayed background history arrives',async({page})=>{
  const state=await assessmentFixture(page,{path:'/assessments?tab=create&generation=handoff-job',pageDelay:4000});
  await expect(state.quiz.getByRole('radio').first()).toBeVisible();
  expect(Date.now()-state.completedAt()).toBeLessThan(1000);
  await state.quiz.getByRole('radio').first().check();await state.quiz.getByRole('button',{name:'Next',exact:true}).click();
  await page.waitForTimeout(4200);await state.quiz.getByRole('button',{name:'Back',exact:true}).click();
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();expect(state.writes).toEqual([]);
});

test('written answers survive local navigation and a full reload without navigation writes',async({page})=>{
  const state=await assessmentFixture(page,{written:true,existingAttempt:true});
  await state.quiz.getByRole('textbox',{name:'Answer question 1',exact:true}).fill('The acceleration is 1.5 m/s² because a = F / m.');
  await state.quiz.getByRole('button',{name:'Next',exact:true}).click();
  await state.quiz.getByRole('textbox',{name:'Answer question 2',exact:true}).fill('A second independent explanation.');
  await page.reload();
  await expect(state.quiz.getByRole('textbox',{name:'Answer question 2',exact:true})).toHaveValue('A second independent explanation.');
  await state.quiz.getByRole('button',{name:'Back',exact:true}).click();
  await expect(state.quiz.getByRole('textbox',{name:'Answer question 1',exact:true})).toHaveValue('The acceleration is 1.5 m/s² because a = F / m.');
  expect(state.writes).toEqual([]);
});

test('a workspace submission keeps its attempt when mutation-driven page refreshes race it',async({page})=>{
  const state=await assessmentFixture(page,{path:'/assessments?tab=create&generation=handoff-job',pageDelay:250});
  for(let i=0;i<3;i++){await state.quiz.getByRole('radio').first().check();if(i<2)await state.quiz.getByRole('button',{name:'Next',exact:true}).click();}
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();await page.waitForTimeout(700);
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(state.writes).toEqual(['/api/v1/assessments/handoff-quiz/attempts','/api/v1/assessments/attempts/local-attempt/submission']);
});

test('a quality report pauses scoring across duplicate cards and preserves answers',async({page})=>{
  const state=await assessmentFixture(page,{duplicate:true});
  await state.quiz.first().getByRole('radio').first().check();
  await state.quiz.first().getByRole('button',{name:'Report question',exact:true}).click();
  await page.getByRole('button',{name:'Report & pause scoring',exact:true}).click();
  await expect(state.quiz.first().getByRole('alert')).toContainText('Scoring is paused');
  await expect(state.quiz.last().getByRole('alert')).toContainText('Scoring is paused');
  await expect(state.quiz.first().getByRole('radio').first()).toBeChecked();
  await expect(state.quiz.first().getByRole('radio').first()).toBeDisabled();
  await state.quiz.first().getByRole('button',{name:'Next',exact:true}).click();
  await expect(state.quiz.first().getByText(/Question 2 of 3/)).toBeVisible();
  expect(state.writes).toEqual(['/api/v1/assessments/handoff-quiz/items/q-0/report']);
});

test('keyboard choices, progress and report dialog retain accessible focus',async({page})=>{
  const state=await assessmentFixture(page);
  await state.quiz.getByRole('radio').first().focus();await page.keyboard.press('ArrowDown');
  await expect(state.quiz.getByRole('radio').last()).toBeChecked();
  await page.keyboard.press('Tab');await expect(state.quiz.getByRole('button',{name:'Next',exact:true})).toBeFocused();
  await page.keyboard.press('Enter');await expect(state.quiz.getByText(/Question 2 of 3/)).toBeVisible();
  const report=state.quiz.getByRole('button',{name:'Report question',exact:true});await report.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(report).toBeFocused();
});

test('multiple-choice RTL stays tidy at 360px, 200% zoom, both themes and reduced motion',async({page},info)=>{
  await page.setViewportSize({width:720,height:1300});await page.emulateMedia({reducedMotion:'reduce'});
  const state=await assessmentFixture(page,{multiple:true,rtl:true});
  await state.quiz.getByRole('checkbox').first().check();await state.quiz.getByRole('checkbox').last().check();
  await page.evaluate(()=>{document.documentElement.style.zoom='2';});
  for(const theme of ['light','dark']){
    await page.evaluate(value=>{localStorage.setItem('mentra-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'mentra-theme',newValue:value,storageArea:localStorage}));},theme);
    await state.quiz.scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const choices=state.quiz.getByRole('checkbox');await expect(choices.first()).toBeChecked();await expect(choices.last()).toBeChecked();
    expect(await state.quiz.locator('.question-transition').evaluate(element=>getComputedStyle(element).animationName)).toBe('none');
    await page.screenshot({path:info.outputPath(`assessment-rtl-${theme}-zoom.png`)});
  }
});

test('a browser storage failure keeps local answers and offers a download',async({page})=>{
  await page.addInitScript(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.startsWith('mentra:assessment-draft:'))throw new DOMException('Quota','QuotaExceededError');return original.call(this,key,value);};});
  const state=await assessmentFixture(page);await state.quiz.getByRole('radio').first().check();
  await expect(state.quiz.getByText(/Browser recovery storage is unavailable/)).toBeVisible();
  const download=page.waitForEvent('download');await state.quiz.getByRole('button',{name:'Download my answers'}).click();
  expect((await download).suggestedFilename()).toBe('mentra-local-answers.txt');
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();expect(state.writes).toEqual([]);
});

for(const mobile of [false,true])test(`${mobile?'4x CPU mobile':'desktop'}: 30 complete handoffs and local interaction latency`,async({browser},info)=>{
  test.setTimeout(180000);const ready:number[]=[],interactions:{kind:string;ms:number}[]=[];
  for(let sample=0;sample<30;sample++){
    const context=await browser.newContext({viewport:mobile?{width:360,height:800}:{width:1280,height:900},isMobile:mobile,hasTouch:mobile});
    const page=await context.newPage();if(mobile){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});}
    const state=await assessmentFixture(page,{messages:sample===0?200:0,duplicate:sample===0,written:sample===1});
    const quiz=state.quiz.first();await expect(quiz).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>performance.getEntriesByName('mentra.assessment.ready_to_visible').length)).toBeGreaterThan(0);
    ready.push(await page.evaluate(()=>performance.getEntriesByName('mentra.assessment.ready_to_visible').at(-1)!.duration));
    if(sample<2){
      await page.evaluate(()=>{const values:{kind:string;ms:number}[]=[];(window as unknown as {interactionTimes:{kind:string;ms:number}[]}).interactionTimes=values;
        const measure=(event:Event)=>{if(!(event.target as HTMLElement).closest('.assessment-interaction'))return;const target=event.target as HTMLInputElement;const kind=target.tagName==='TEXTAREA'?'text':target.type==='radio'?'choice':'navigation';if(event.type!=='input'&&kind!=='navigation')return;const start=performance.now();requestAnimationFrame(()=>requestAnimationFrame(()=>values.push({kind,ms:performance.now()-start})));};
        document.addEventListener('input',measure,true);document.addEventListener('click',measure,true);
      });
      if(sample===1){await quiz.getByRole('textbox').pressSequentially('Independent reasoning: force divided by mass gives acceleration.');}
      else{for(let i=0;i<30;i++)await quiz.getByRole('radio').nth(i%2).check();}
      if(sample===0)for(let i=0;i<15;i++){await quiz.getByRole('button',{name:'Next',exact:true}).click();await quiz.getByRole('button',{name:'Back',exact:true}).click();}
      await page.waitForTimeout(100);
      interactions.push(...await page.evaluate(()=>(window as unknown as {interactionTimes:{kind:string;ms:number}[]}).interactionTimes));
      if(sample===0)await page.screenshot({path:info.outputPath(mobile?'assessment-mobile.png':'assessment-desktop.png')});
    }
    expect(state.writes).toEqual([]);expect(state.reads.filter(path=>path.includes('/chat-drafts/')||path.endsWith('/handoff-quiz/attempts'))).toEqual([]);
    await context.close();
  }
  const p95=(values:number[])=>[...values].sort((a,b)=>a-b)[Math.ceil(values.length*.95)-1];
  const metrics={mobile,cpu_rate:mobile?4:1,samples:ready.length,ready_p95_ms:p95(ready),interaction_samples:interactions.length,interaction_p95_ms:p95(interactions.map(row=>row.ms)),by_kind:Object.fromEntries(['choice','text','navigation'].map(kind=>{const values=interactions.filter(row=>row.kind===kind).map(row=>row.ms);expect(values.length).toBeGreaterThanOrEqual(30);return [kind,{samples:values.length,p95_ms:p95(values)}];})),blocking_hydration_reads:0,navigation_writes:0};
  console.log('ASSESSMENT_UI_METRICS',JSON.stringify(metrics));await info.attach('ui-metrics',{body:JSON.stringify(metrics),contentType:'application/json'});
  expect(metrics.ready_p95_ms).toBeLessThanOrEqual(mobile?1000:500);for(const value of Object.values(metrics.by_kind))expect(value.p95_ms).toBeLessThanOrEqual(mobile?200:100);
});
