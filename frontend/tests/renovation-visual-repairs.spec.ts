import { expect, test } from '@playwright/test';
import { richChat } from './renovation-rich-fixtures';
import { readFile } from 'node:fs/promises';

const exactDiagram = `flowchart TB
    subgraph React["React stack"]
        R1["Icons: lucide-react / react-icons"]
        R2["Animation: motion (Framer Motion)"]
        R3["Forms: react-hook-form + zod"]
        R4["Data: TanStack Query + Zustand"]
        R5["UI: shadcn/ui + Radix"]
    end
    subgraph Angular["Angular stack"]
        A1["Icons: @ng-icons / lucide-angular"]
        A2["Animation: @angular/animations + GSAP"]
        A3["Forms: Reactive Forms + zod"]
        A4["Data: HttpClient + signals / NgRx"]
        A5["UI: Angular Material / Spartan"]
    end
    R2 -.->|"biggest advantage"| A2
    R1 -.->|"near parity"| A1
    R3 -.->|"near parity"| A3`;

test('the exact saved React Angular diagram renders its Data labels', async ({ page }) => {
  await richChat(page, '```mermaid\n' + exactDiagram + '\n```'); await page.goto('/chat/polish-chat');
  const diagram = page.locator('.mermaid-figure');
  await expect(diagram.locator('svg text').filter({ hasText: /Data:\s*TanStack\s*Query/ })).toBeVisible();
  await expect(diagram.locator('svg text').filter({ hasText: /Data:\s*HttpClient/ })).toBeVisible();
  await expect(diagram.getByRole('button', { name: 'Expand', exact: true })).toBeEnabled();
});

for (const theme of ['light', 'dark']) test(`colored diagrams and semantic text render visibly in ${theme}`, async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
  await richChat(page, ':color[Benefit]{tone="success"} and :color[Caution]{tone="warning"}.\n\n```mermaid\nflowchart LR\n A[Data: React] --> B[Data: Angular]\n classDef react fill:#0000ff,stroke:#38bdf8,color:#0000ff\n class A react\n style B fill:#ff0000,stroke:#ff0000,color:#ff0000\n```');
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.mermaid-figure svg')).toBeVisible();
  const fills = await page.locator('.mermaid-figure svg .node rect').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).fill));
  expect(fills).toContain('rgb(0, 0, 255)'); expect(fills).toContain('rgb(255, 0, 0)');
  const labels = await page.locator('.mermaid-figure .node text').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).fill));
  expect(labels).not.toContain('rgb(0, 0, 255)'); expect(labels).not.toContain('rgb(255, 0, 0)');
  const colors = await page.locator('.rich-color').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).color));
  expect(colors).toHaveLength(2); expect(colors[0]).not.toBe(colors[1]);
});

test('unsafe diagram styles remain rejected with a visible explanation', async ({ page }) => {
  await richChat(page, '```mermaid\nflowchart LR\n A --> B\n classDef bad fill:url(https://tracker.example.com/a)\n class A bad\n```');
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('This diagram could not be displayed. Its source is available below.')).toBeVisible();
  await expect(page.locator('.mermaid-svg svg')).toHaveCount(0);
});

for (const legacy of [false, true]) test(`comparison bars pair entities with stable colors, legacy ${legacy}`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const bars = ['Animation', 'Forms'].flatMap(group => ['React', 'Angular'].map((series, i) => ({ label: `${series} — ${group}`, value: 5 - i, max: 5, unit: 'points', ...(legacy ? {} : { group, series, color: i ? 'red' : 'blue' }) })));
  await richChat(page, '', [{ id: 'compare', kind: 'value_bars', question: 'Framework comparison', bars }]); await page.goto('/chat/polish-chat');
  const card = page.getByRole('region', { name: 'Framework comparison' });
  const group = card.getByRole('group', { name: 'Animation', exact: true });
  const left = await group.getByRole('meter', { name: 'React — Animation', exact: true }).boundingBox();
  const right = await group.getByRole('meter', { name: 'Angular — Animation', exact: true }).boundingBox();
  expect(Math.abs(left!.y - right!.y)).toBeLessThan(2); expect(right!.x).toBeGreaterThan(left!.x);
  const fills = await card.getByRole('meter').evaluateAll(nodes => nodes.map(node => getComputedStyle(node.firstElementChild!).backgroundColor));
  expect(fills[0]).toBe(fills[2]); expect(fills[1]).toBe(fills[3]); expect(fills[0]).not.toBe(fills[1]);
  if (!legacy) {
    const danger = await page.evaluate(() => 'rgb(' + getComputedStyle(document.documentElement).getPropertyValue('--danger').trim().split(/\s+/).join(', ') + ')');
    expect(fills[1]).toBe(danger);
  }
  await expect(card.getByRole('meter').first()).toHaveAttribute('aria-valuetext', '5 / 5 points · 100%');
});

test('chart series colors and pie palettes use only validated colors', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const spec = { type: 'BarChart', title: 'Colors', xKey: 'topic', data: [{ topic: 'A', react: 5, angular: 3 }], series: [{ dataKey: 'react', color: '#123456' }, { dataKey: 'angular', color: 'red' }] };
  await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
  await expect(page.locator('.recharts-bar-rectangle')).toHaveCount(2);
  const fills = await page.locator('.recharts-bar-rectangle path').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).fill));
  expect(fills).toContain('rgb(18, 52, 86)'); expect(fills[1]).not.toBe(fills[0]);
  const pie = { type: 'PieChart', title: 'Palette', xKey: 'name', data: [{ name: 'A', value: 1 }, { name: 'B', value: 2 }], series: [{ dataKey: 'value' }], colors: ['#123456', '#abcdef'] };
  await richChat(page, '```recharts\n' + JSON.stringify(pie) + '\n```'); await page.goto('/chat/polish-chat');
  await expect(page.locator('.recharts-pie-sector')).toHaveCount(2);
  const pieFills = await page.locator('.recharts-pie-sector path').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).fill));
  expect(pieFills).toEqual(['rgb(18, 52, 86)', 'rgb(171, 205, 239)']);
});

test('generic URL and SVG path icons render without Lucide or brand mappings', async ({ page }) => {
  let requests = 0; const catalogs: string[] = [];
  page.on('request', request => { if (/lucideIconCatalog/.test(request.url())) catalogs.push(request.url()); });
  await page.route('https://assets.example.com/logo.svg', route => { requests++; return route.fulfill({ headers: { 'access-control-allow-origin': '*' }, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="red" d="M12 2L2 22H22Z"/></svg>' }); });
  await richChat(page, ':icon[https://assets.example.com/logo.svg] Icon. :icon[https://assets.example.com/logo.svg] Reused. :icon[M12 2L2 22H22Z] Shape. :icon[M2 2L22 22] Stroke. :icon[M256 2L2 510H510Z]{viewBox="0 0 512 512"} Large coordinates.');
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.rich-icon img')).toHaveCount(2);
  await expect(page.locator('.rich-icon svg')).toHaveCount(3);
  await expect(page.locator('.rich-icon svg').last()).toHaveAttribute('viewBox', '0 0 512 512');
  expect(await page.locator('.rich-icon svg').nth(1).locator('path').getAttribute('fill')).toBe('none');
  expect(requests).toBe(1); expect(catalogs).toEqual([]);
  expect(await page.locator('.rich-icon img').first().evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);
});

test('failed URLs, oversized assets and malformed paths retain placeholders', async ({ page }) => {
  await page.route('https://assets.example.com/fail.svg', route => route.fulfill({ status: 404, body: '' }));
  await page.route('https://assets.example.com/huge.svg', route => route.fulfill({ headers: { 'access-control-allow-origin': '*', 'content-length': '100000' }, contentType: 'image/svg+xml', body: 'x'.repeat(100000) }));
  await richChat(page, ':icon[https://assets.example.com/fail.svg] Failed. :icon[https://assets.example.com/huge.svg] Too large. :icon[M12 2L] Invalid. :icon[BookOpen]{style="color:red"} Unsupported. :icon[M0 0] Empty. :icon[M2 2A5 5 0 2 1 10 10] Invalid arc.');
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.rich-icon-placeholder')).toHaveCount(6);
  await expect(page.locator('.rich-icon img')).toHaveCount(0);
  await expect(page.locator('.rich-icon svg')).toHaveCount(0);
});

test('every chart family downloads a standalone SVG with title, units and legend', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const type of ['BarChart', 'LineChart', 'AreaChart', 'ComposedChart', 'PieChart', 'RadarChart', 'ScatterChart']) {
    const spec = { type, title: `Assignment ${type}`, unit: 'points', xKey: 'name', data: [{ name: type === 'ScatterChart' ? 1 : 'A', value: 2 }, { name: type === 'ScatterChart' ? 2 : 'B', value: 4 }, { name: type === 'ScatterChart' ? 3 : 'C', value: 3 }], series: [{ dataKey: 'value', name: 'Measured values', ...(type === 'ComposedChart' ? { type: 'Bar' } : {}) }] };
    await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
    await expect(page.locator('.recharts-figure .recharts-wrapper')).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download SVG', exact: true }).click()]);
    const path = info.outputPath(`${type}.svg`); await download.saveAs(path); const svg = await readFile(path, 'utf8');
    expect(svg).toContain(spec.title); expect(svg).toContain('points'); expect(svg).toContain(type === 'PieChart' ? '>A<' : 'Measured values');
    expect(svg).not.toContain('var('); expect(svg).not.toContain('foreignObject');
    const decoded = await page.evaluate(async source => { const url = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml' })); try { const image = new Image(); image.src = url; await image.decode(); return image.naturalWidth > 100 && image.naturalHeight > 100; } finally { URL.revokeObjectURL(url); } }, svg);
    expect(decoded).toBe(true);
    if (type === 'BarChart') {
      const [png] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download PNG', exact: true }).click()]);
      const imagePath = info.outputPath('assignment-chart.png'); await png.saveAs(imagePath); const bytes = await readFile(imagePath);
      expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a'); expect(bytes.readUInt32BE(16)).toBeGreaterThan(100);
    }
  }
});

test('Mermaid downloads portable SVG and PNG in dark mode', async ({ page }, info) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await richChat(page, '```mermaid\nflowchart LR\n accTitle: Assignment diagram\n A[Input] --> B[Result]\n```'); await page.goto('/chat/polish-chat');
  await expect(page.locator('.mermaid-svg svg')).toBeVisible();
  for (const format of ['SVG', 'PNG']) {
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: `Download ${format}`, exact: true }).click()]);
    const path = info.outputPath(`assignment-diagram.${format.toLowerCase()}`); await download.saveAs(path); const bytes = await readFile(path);
    if (format === 'SVG') { expect(bytes.toString()).toContain('Assignment diagram'); expect(bytes.toString()).toContain('<rect'); }
    else expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  }
});
