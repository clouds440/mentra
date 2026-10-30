// Capture the running local product with a separate synthetic account.
// Run from the repo root: node frontend/scripts/capture-showcase.mjs
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { randomUUID, randomBytes } from 'node:crypto';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const root = process.cwd();
const web = process.env.SHOWCASE_WEB_URL ?? 'http://localhost:5173';
const api = process.env.SHOWCASE_API_URL ?? 'http://localhost:8000/api/v1';
const browser = await chromium.launch({ headless: process.env.SHOWCASE_HEADED !== '1' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
const page = await context.newPage();
const manifest = { captured: new Date().toISOString(), source: 'Running local Mentra app; isolated synthetic showcase account; no API mocks.', screenshots: [], notes: [] };
const ids = {};
const errors = [];
page.on('pageerror', e => errors.push(e.message));

async function call(url, data, method = 'POST') {
  const response = await context.request.fetch(api + url, { method, data, headers: { Origin: web, 'X-Mentra-Session': 'cookie' }, timeout: 180_000 });
  if (!response.ok()) throw new Error(`${method} ${url}: ${response.status()} ${(await response.text()).slice(0, 350)}`);
  return response.status() === 204 ? null : response.json();
}
async function get(url) { return call(url, undefined, 'GET'); }
async function capture(module, name, description, target = page) {
  const file = `docs/${module}/screenshots/showcase/${name}.png`;
  await mkdir(path.join(root, path.dirname(file)), { recursive: true });
  await target.locator('main').waitFor({ state: 'visible' });
  await target.waitForTimeout(1000);
  await target.evaluate(() => document.fonts.ready);
  await target.waitForFunction(() => ![...document.querySelectorAll('[role="status"][aria-label^="Loading"]')].some(el => el.getBoundingClientRect().height > 0), undefined, { timeout: 90_000 });
  if (new URL(target.url()).pathname.startsWith('/chat/')) await target.getByRole('article', { name: 'Mentra response' }).first().waitFor({ state: 'visible', timeout: 90_000 });
  await target.waitForTimeout(1400);
  await target.screenshot({ path: path.join(root, file), animations: 'disabled' });
  manifest.screenshots.push({ file, description, viewport: target.viewportSize() });
  console.log('Captured', file);
}
async function route(url) { await page.goto(web + url); await page.locator('main').waitFor(); }
async function optional(name, action) { try { await action(); } catch (e) { manifest.notes.push(`${name}: ${e.message}`); console.log('Skipped', name, e.message.slice(0, 200)); } }
async function waitTurn(id) {
  for (let i = 0; i < 100; i++) {
    const value = await get(`/conversations/${id}/status`);
    if (value.turn?.state !== 'RUNNING') return value;
    await page.waitForTimeout(2000);
  }
  throw new Error('Chat did not finish within capture budget');
}
async function chat(content) {
  const id = randomUUID();
  await call('/conversations/turns', { conversation_id: id, client_turn_id: randomUUID(), expected_revision: 0, content, timezone: 'Asia/Karachi' });
  const value = await waitTurn(id);
  if (value.turn?.state !== 'SUCCEEDED') throw new Error('Chat state '+value.turn?.state+': '+value.turn?.error);
  return id;
}

try {
  const username = 'showcase_' + randomUUID().slice(0, 8);
  await call('/auth/register', { username, password: randomBytes(28).toString('base64url') });
  let profile = await get('/student-profile');
  profile = await call('/student-profile/details', { expected_version: profile.version, details: { preferred_name: 'Maya', education_level: 'college', field_of_study: 'Physics and mathematics', learning_goal: 'Build intuition with visual explanations, then practise and learn from mistakes.', learning_preference: 'examples_first', explanation_depth: 'standard', visual_support: 'prefer_visuals', participation: 'adaptive' } }, 'PUT');
  await call('/student-profile/calibration/skip', { expected_version: profile.version });
  console.log('Created separate synthetic showcase account and completed onboarding.');
  await page.addInitScript(() => localStorage.setItem('mentra-theme', 'light'));
  const learningContext = await call('/learning-contexts', { name: 'Physics · Forces and motion', activate: true });
  console.log('Context response keys:', Object.keys(learningContext).join(','));
  ids.context = learningContext.context_id ?? learningContext.id;

  await optional('Library originals', async () => {
    const text = '# Forces and motion\n\nNewton’s second law: the net force on an object equals its mass multiplied by acceleration (F = ma). A force of 12 N acting on a 3 kg cart produces an acceleration of 4 m/s².\n\nInertia is the tendency to resist a change in velocity. An unbalanced force causes acceleration. The direction of acceleration follows the net force.\n\nWorked example: a 2 kg cart pushed with 10 N accelerates at 5 m/s². When the net force is zero, its velocity stays constant.\n';
    const response = await context.request.post(api+'/files/uploads', { headers: { Origin: web }, multipart: { purpose: 'library', operation_key: randomUUID(), file: { name: 'Forces and motion — study notes.txt', mimeType: 'text/plain', buffer: Buffer.from(text) } }, timeout: 180_000 });
    if (!response.ok()) throw new Error('Files upload '+response.status()+': '+(await response.text()).slice(0, 200));
    const file = await response.json();
    const result = await call('/documents', { file_id: file.id, title: 'Forces and motion · Illustrated study notes', context_ids: [ids.context], idempotency_key: randomUUID() });
    ids.document = result.document_id;
    console.log('Uploaded synthetic study notes.');
  });
  for (const event of [
    { title: 'Mechanics revision · Newton’s laws', description: 'Review the worked examples, then try a short practice session.', kind: 'study', local_date: '2026-10-31' },
    { title: 'Physics quiz · Forces and motion', description: 'A short check of forces, acceleration and free-body diagrams.', kind: 'quiz', local_date: '2026-11-02' },
    { title: 'Finish the motion worksheet', description: 'Solve on paper and upload the answer sheet for review.', kind: 'assignment', local_date: '2026-11-04' },
  ]) await optional('Agenda item', () => call('/events', { ...event, client_request_id: randomUUID(), context_id: ids.context, timezone: 'Asia/Karachi', reminder: { mode: 'default' } }));

  await optional('Visual learning conversation', async () => {
    ids.chat = await chat('Explain Newton’s second law with a short, friendly worked example for a 3 kg cart pushed by 12 N. Include a clear equation, one compact Mermaid flowchart connecting force, mass and acceleration, and a brief takeaway. Keep the whole answer concise enough for one screen. Do not create practice yet.');
    await route('/chat/'+ids.chat);
    await capture('chat', 'learning-conversation', 'Actual local chat: equation, worked example and model-generated explanation.');
    await page.setViewportSize({ width: 390, height: 844 });
    await capture('chat', 'learning-mobile', 'The same conversation in the mobile layout.');
    await page.setViewportSize({ width: 1440, height: 1000 });
  });
  await optional('Exploratory chart', async () => {
    ids.chart = await chat('Show a compact interactive line chart of acceleration against applied net force for a cart. This is illustrative data: forces 0, 4, 8, 12, 16 N with a mass parameter initially 2 kg, range 1 to 5 kg. Use your supported chart format and local equation controls so I can change mass and see acceleration = force / mass. Add only a one-sentence explanation; no practice questions.');
    await route('/chat/'+ids.chart);
    await page.locator('.recharts-wrapper').first().waitFor({ timeout: 30_000 });
    await page.locator('.recharts-figure').first().scrollIntoViewIfNeeded();
    await capture('chat', 'interactive-chart', 'Actual model-generated exploratory chart in the running application.');
    const slider = page.getByRole('slider', { name: 'Adjust selected value' });
    if (await slider.count()) {
      await mkdir(path.join(root, '.cache/showcase-frames'), { recursive: true });
      for (let n = 0; n < 8; n++) {
        if (n) { await slider.focus(); for (let k=0; k<4; k++) await page.keyboard.press(n<5 ? 'ArrowRight' : 'ArrowLeft'); }
        await page.waitForTimeout(500);
        await page.locator('.recharts-figure').first().screenshot({ path: path.join(root, `.cache/showcase-frames/chart-${n}.png`), animations: 'disabled' });
      }
      console.log('Recorded chart interaction frames.');
      await optional('Chart GIF encoding', async () => {
        const python = process.env.SHOWCASE_PYTHON ?? path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
        const code = "from pathlib import Path; from PIL import Image; frames=[Image.open(p).convert('RGB') for p in sorted(Path('.cache/showcase-frames').glob('chart-*.png'))]; width=min(1040,frames[0].width); frames=[im.resize((width,round(im.height*width/im.width))) for im in frames]; frames[0].save('docs/chat/screenshots/showcase/chart-exploration.gif',save_all=True,append_images=frames[1:],duration=[1400]+[600]*(len(frames)-2)+[1400],loop=0,optimize=True)";
        await promisify(execFile)(python, ['-c', code], { cwd: root });
        manifest.animations = [{ file: 'docs/chat/screenshots/showcase/chart-exploration.gif', description: 'Actual local chart-control screenshot frames assembled into a looping GIF.' }];
      });
    }
  });
  await optional('Conversational questionnaire', async () => {
    ids.questions = await chat('Help me choose a study routine. Ask a grouped questionnaire of three short questions together: my main goal, time available per day, and whether I prefer worked examples or practice. Use native chat input controls. Do not answer these questions for me or create an assessment.');
    await route('/chat/'+ids.questions);
    await page.getByRole('region', { name: 'Conversation questions' }).waitFor({ timeout: 15_000 });
    await capture('chat', 'conversation-questions', 'Native conversational questionnaire, generated by the running local app.');
  });
  await optional('Saved assessment', async () => {
    const job = await call('/assessments/generation-jobs', { client_request_id: randomUUID(), context_id: ids.context, topic: 'Newton’s laws: net force, mass and acceleration', count: 3, question_format: 'mcq', purpose: 'practice', grounded: false, result_style: 'feedback' });
    let generated;
    for (let n=0;n<100;n++) {
      generated = await get('/assessments/generation-jobs/'+job.id);
      if (generated.state==='completed') break;
      if (generated.state==='failed') throw new Error(generated.error ?? 'Generation failed');
      await page.waitForTimeout(2000);
    }
    const assessment=generated.result;
    if (!assessment?.id) throw new Error('No completed assessment result');
    ids.assessment=assessment.id;
    await route('/assessments?assessment='+ids.assessment);
    await capture('assessments', 'practice-workspace', 'Generated local practice assessment with download and answer-sheet entry points.');
    const attempt = await call(`/assessments/${ids.assessment}/attempts`, { client_request_id: randomUUID() });
    ids.attempt=attempt.id;
    const answers=Object.fromEntries(assessment.questions.map((q,n)=>[q.id,q.options[n % q.options.length].id]));
    await call(`/assessments/attempts/${attempt.id}/submission`, { expected_revision: attempt.revision, client_request_id: randomUUID(), answers, transcription_confirmed: false, assistance: 'independent' });
    let result;
    for (let n=0;n<90;n++) { result=await get('/assessments/attempts/'+attempt.id); if (['graded','failed'].includes(result.state)) break; await page.waitForTimeout(2000); }
    if (result.state!=='graded') throw new Error('Grading state '+result.state);
    await route(`/assessments?assessment=${ids.assessment}&attempt=${attempt.id}`);
    await capture('assessments','graded-feedback','Real grading results for synthetic showcase answers; not a real learner record.');
    await route('/assessments?tab=mistakes');
    await capture('assessments','mistake-review','Saved mistake history from the synthetic practice attempt.');
    await optional('Answer sheet review',async()=>{
      const next=await call(`/assessments/${ids.assessment}/attempts`,{client_request_id:randomUUID()});
      const sheet=assessment.questions.map((q,n)=>`${n+1}. ${String.fromCharCode(65+(n%q.options.length))}`).join('\n');
      const response=await context.request.post(api+'/files/uploads',{headers:{Origin:web},multipart:{purpose:'assessment',operation_key:randomUUID(),file:{name:'Maya — mechanics answers.txt',mimeType:'text/plain',buffer:Buffer.from(sheet)}},timeout:180_000});
      if(!response.ok())throw new Error('Answer file upload '+response.status());
      const file=await response.json();
      await call(`/assessments/attempts/${next.id}/source`,{file_id:file.id,expected_revision:next.revision});
      await route(`/assessments?assessment=${ids.assessment}&attempt=${next.id}`);
      await capture('assessments','answer-sheet-review','Actual TXT extraction and explicit review/confirmation before grading.');
    });
  });
  for (const [url,module,name,description] of [
    ['/library','library','source-library','Private Library with synthetic source material.'],
    ['/progress','learning','learning-progress','Topics and evidence from the synthetic local practice session.'],
    ['/progress?tab=events','events','study-agenda','Owned agenda populated through the real event API.'],
    ['/settings','profile','teaching-preferences','Current profile, teaching preferences and account settings.'],
    ['/assessments?tab=create','assessments','create-assessment','Configurable practice generation in the real workspace.'],
  ]) await optional(name,async()=>{await route(url);await capture(module,name,description);});
  await optional('Subskill detail',async()=>{
    await route('/progress');
    const explore=page.getByRole('button',{name:/^Explore /}).or(page.getByRole('button',{name:/skills not grouped yet/})).first();
    await explore.waitFor({timeout:90_000});await explore.click();
    await page.getByRole('dialog').waitFor();
    await capture('learning','topic-subskills','Actual independently tracked skills and their evidence/practice actions; topic grouping is shown as recorded.');
  });
  await optional('Notifications', async () => { await route('/notifications'); await capture('notifications', 'reminder-inbox', 'Actual reminder inbox in the separate showcase account.'); });
  await optional('Profile editor', async () => { await route('/settings'); await page.getByRole('button', { name: 'Edit profile', exact: true }).click(); await capture('profile', 'edit-teaching-preferences', 'User-owned profile editor with teaching preferences.'); });
  await optional('Dark theme', async () => {
    const dark = await context.newPage();
    try {
      await dark.addInitScript(() => localStorage.setItem('mentra-theme', 'dark'));
      await dark.goto(web + '/chat/' + ids.chart);
      await dark.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
      await capture('chat', 'learning-dark', 'Actual exploratory chart in verified Dark theme.', dark);
    } finally { await dark.close(); }
  });
  manifest.notes.push(...errors.map(e=>'Browser error: '+e));
  if (process.env.SHOWCASE_KEEP_SESSION === '1') {
    await mkdir(path.join(root,'.cache'),{recursive:true});
    await context.storageState({path:path.join(root,'.cache/showcase-browser-state.json')});
    await writeFile(path.join(root,'.cache/showcase-ids.json'),JSON.stringify(ids,null,2));
  }
} finally {
  await mkdir(path.join(root,'docs/product/showcase'),{recursive:true});
  await writeFile(path.join(root,'docs/product/showcase/capture-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  await browser.close();
  console.log('Showcase capture finished:',manifest.screenshots.length,'screenshots;',manifest.notes.length,'notes.');
}
