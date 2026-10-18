import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

const contextId = '11111111-1111-4111-8111-111111111111';
const conceptId = '22222222-2222-4222-8222-222222222222';
const created = '2026-10-17T00:00:00Z';
const material = (index: number) => ({ id: `material-${index}`, title: `Material ${index}`, filename: `notes-${index}.pdf`, context_ids: [contextId], archived: false, revision: 1, active_generation_id: `generation-${index}`, versions: [], version_count: 1, generations: [], jobs: [] });

test('math renders across chat without rewriting code, prices or copied equations', async ({ page, context }, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const state = await workspace(page);
  state.complete(String.raw`Inline $x^2 + 2x$ and \(\frac{1}{2}\). Price $5 and $10.

\[
\sqrt{9} = 3
\]

$$\begin{pmatrix}1&2\\3&4\end{pmatrix}$$

Code: ` + '`\\(literal\\)`' + '\n\n```tex\n\\[keep code\\]\n```');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/chat/polish-chat');
  const response = page.getByRole('article', { name: 'Mentra response' }).last();
  await expect(response.locator('.katex-mathml')).toHaveCount(4);
  await expect(response).toContainText('Price $5 and $10.');
  await expect(response.locator('code').filter({ hasText: '\\(literal\\)' })).toBeVisible();
  await response.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('\\frac{1}{2}');
  expect(copied).toContain('Price $5 and $10.');
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('math-mobile.png') });
});

test('assessment source picker searches later pages and keeps selected material', async ({ page }) => {
  await workspace(page);
  const queued: Record<string, unknown>[] = [];
  const hydrated: string[] = [];
  await page.route('**/api/v1/documents**', route => {
    const url = new URL(route.request().url()), id = /\/documents\/(material-\d+)$/.exec(url.pathname)?.[1];
    if (id) { hydrated.push(id); return route.fulfill({ json: material(Number(id.split('-')[1])) }); }
    const offset = Number(url.searchParams.get('offset') ?? 0), query = url.searchParams.get('query');
    const all = Array.from({ length: 60 }, (_, i) => material(i + 1)).filter(item => !query || item.title.toLowerCase().includes(query.toLowerCase()));
    return route.fulfill({ json: { items: all.slice(offset, offset + 25), total: all.length, offset, limit: 25 } });
  });
  await page.route('**/api/v1/assessments/generation-jobs', route => {
    queued.push(route.request().postDataJSON());
    return route.fulfill({ json: { id: 'job-1', state: 'queued', title: 'Practice', completed_parts: 0, total_parts: 3, result: null, error: null, can_retry: false } });
  });
  await page.goto('/assessments?tab=create&document=material-60&context=' + contextId + '&topic=Mechanics');
  await expect(page.getByText('1 selected · Choose up to 20 ready materials. Selections stay when you search or change pages.')).toBeVisible();
  await page.getByRole('button', { name: 'Load more material', exact: true }).click();
  await page.getByRole('button', { name: 'Load more material', exact: true }).click();
  await page.getByRole('combobox', { name: 'Assessment study documents', exact: true }).click();
  await page.getByRole('option', { name: 'Material 51', exact: true }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('searchbox', { name: 'Search assessment materials' }).fill('Material 2');
  await expect(page.getByRole('combobox', { name: 'Assessment study documents', exact: true })).toContainText('Material 51');
  await page.getByRole('button', { name: 'Generate assessment', exact: true }).click();
  await expect.poll(() => queued.length).toBe(1);
  expect([...(queued[0].document_ids as string[])].sort()).toEqual(['material-51', 'material-60']);
  expect(queued[0]).toMatchObject({ context_id: contextId, grounded: true, count: 3 });
  expect(hydrated).toEqual(['material-60']);
});

test('review and practice links retain exact concept, context and purpose without creating a job on navigation', async ({ page }) => {
  await workspace(page);
  let jobs = 0;
  await page.route('**/api/v1/learning', route => route.fulfill({ json: { learner: { concepts: [], context_ids: [contextId], generated_at: created }, recommendations: [{ concept_id: conceptId, context_id: contextId, name: 'Shared topic', reason: 'low_mastery' }], verification: [{ concept_id: conceptId, context_id: contextId, name: 'Shared topic', reason: 'contradictory_evidence' }] } }));
  await page.route('**/api/v1/learning-contexts**', route => route.fulfill({ json: [{ context_id: contextId, name: 'Mechanics', status: 'ACTIVE' }] }));
  await page.route('**/api/v1/assessments/generation-jobs', route => { jobs++; return route.fulfill({ json: {} }); });
  await page.goto('/progress');
  await page.getByRole('link', { name: 'Start quick review', exact: true }).click();
  await expect(page).toHaveURL(new RegExp('concept=' + conceptId));
  await expect(page.getByLabel('Topic (optional)', { exact: true })).toHaveValue('Shared topic');
  await expect(page.getByRole('combobox', { name: 'Assessment purpose', exact: true })).toContainText('Verification');
  await expect(page.getByRole('combobox', { name: 'Assessment learning context', exact: true })).toContainText('Mechanics');
  await page.reload();
  await expect(page.getByText('Practising 1 selected topic in this learning context.')).toBeVisible();
  expect(jobs).toBe(0);
});

test('a distant citation loads its exact chunk before the first page and preserves version identity', async ({ page }) => {
  await workspace(page);
  const source = { token: 'S1', document_id: 'material-1', version_id: 'version-1', generation_id: 'generation-1', chunk_id: 'chunk-150', title: 'Long notes', filename: 'notes.md', media_type: 'text/markdown', heading_path: [], spans: [{ block: 150, page: 75, slide: null, start: 0, end: 20, method: 'native' }], excerpt: 'Distant passage', warnings: [] };
  let pages = 0;
  await page.route('**/api/v1/conversations/polish-chat/status*', route => route.fulfill({ json: { conversation: { id: 'polish-chat', title: 'Sources', revision: 8, message_count: 2, created_at: created, updated_at: created }, items: [{ id: 'answer', conversation_id: 'polish-chat', sequence: 2, role: 'assistant', content: 'Supported here [[S1]].', created_at: created, citations: ['S1'], sources: [source] }], has_more: false, next_cursor: null, turn: { id: 'source-turn', state: 'SUCCEEDED', attempt: 1, user_sequence: 1, selection: { mode: 'STANDARD' } } } }));
  await page.route('**/api/v1/rag/chunks/chunk-150*', route => route.fulfill({ json: { ...source, id: source.chunk_id, content: 'The exact cited passage on page 75.' } }));
  await page.route('**/versions/version-1/chunks*', route => { pages++; return route.fulfill({ json: [] }); });
  await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'Open cited source Long notes', exact: true }).click();
  await expect(page.getByText('The exact cited passage on page 75.', { exact: true })).toBeVisible();
  expect(pages).toBe(0);
  await page.getByRole('button', { name: 'Read full source', exact: true }).click();
  await expect.poll(() => pages).toBe(1);
});

test('Library searches the server and preserves the query through filters', async ({ page }) => {
  await workspace(page);
  const requests: URL[] = [];
  await page.route('**/api/v1/documents?*', route => { const url = new URL(route.request().url()); requests.push(url); return route.fulfill({ json: { items: url.searchParams.get('query') === 'اردو' ? [material(55)] : [], total: 1, offset: 0, limit: 25 } }); });
  await page.goto('/library');
  await page.getByRole('searchbox', { name: 'Search Library' }).fill('اردو');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Material 55', exact: true })).toBeVisible();
  expect(requests.at(-1)?.searchParams.get('query')).toBe('اردو');
  await expect(page.getByRole('link', { name: 'Quiz this material', exact: true })).toHaveAttribute('href', /document=material-55/);
  await page.reload();
  await expect(page.getByRole('searchbox', { name: 'Search Library' })).toHaveValue('اردو');
});

test('event detail downloads an explicit calendar snapshot', async ({ page }) => {
  await workspace(page);
  const event = { id: 'event-1', title: 'Study session', description: '', kind: 'study', status: 'scheduled', timezone: 'Asia/Karachi', local_date: '2026-10-20', starts_at: null, bucket: 'upcoming', revision: 1, reminder_state: 'pending', reminder_due_at: null, evidence: [] };
  await page.route('**/api/v1/events/event-1', route => route.fulfill({ json: event }));
  await page.route('**/api/v1/events/event-1/calendar', route => route.fulfill({ contentType: 'text/calendar', body: 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n' }));
  await page.goto('/progress?tab=events&event=event-1');
  await expect(page.getByText('The calendar file is a snapshot. Later changes in Mentra do not update your calendar.', { exact: true })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download calendar file', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('mentra-event-event-1.ics');
});
