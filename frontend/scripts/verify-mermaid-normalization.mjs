import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto(process.env.MERMAID_TEST_URL ?? 'http://localhost:5188');
  const source = `accTitle: Horse journey split into two legs
accDescr: Two legs totaling 29.83 km.
flowchart LR
A["Start<br/>t = 0"] -->|"Leg 1: 40 km/h × 20 min<br/>= 13.33 km"| B["Tired<br/>t = 20 min"]
B -->|"Leg 2: 30 km/h × 33 min<br/>= 16.5 km"| C["Arrive<br/>t = 53 min"]
C --> D["Total = 13.33 + 16.5<br/>= 29.83 km"]
style A fill:#dbeafe,stroke:#1d4ed8,color:#0f172a`;
  const checks = await page.evaluate(async source => {
    const { normalizeMermaidSource: normalize } = await import('/src/lib/mermaidSource.ts');
    const normalized = normalize(source);
    if (!normalized.startsWith('flowchart LR\naccTitle:')) throw Error('Metadata not reordered');
    if (normalized.includes('<br')) throw Error('Break tags remain');
    for (const bad of ['<br onload="alert(1)">', '<script>alert(1)</script>', '%%{init: {}}%%', '---\ntitle: unsafe\n---']) {
      if (!normalize(bad).includes(bad)) throw Error('Unsafe source was silently stripped');
    }
    const { default: React } = await import('/node_modules/.vite/deps/react.js');
    const { default: { createRoot } } = await import('/node_modules/.vite/deps/react-dom_client.js');
    const { MermaidDiagram } = await import('/src/components/content/MermaidDiagram.tsx');
    document.body.innerHTML = '<div id="fixture"></div>';
    window.fixtureRoot = createRoot(document.getElementById('fixture'));
    window.fixtureRoot.render(React.createElement(MermaidDiagram, { code: source }));
    return true;
  }, source);
  assert(checks);
  await page.locator('.mermaid-svg svg').waitFor();
  assert.match(await page.locator('.mermaid-svg svg').textContent(), /29.83/);
  assert.match(await page.locator('.mermaid-svg svg').textContent(), /Start/);
  await page.getByRole('button', { name: 'Expand', exact: true }).click();
  await page.getByRole('dialog').locator('svg').waitFor();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.evaluate(async () => {
    const { default: React } = await import('/node_modules/.vite/deps/react.js');
    const { MermaidDiagram } = await import('/src/components/content/MermaidDiagram.tsx');
    window.fixtureRoot.render(React.createElement(MermaidDiagram, { code: 'flowchart LR\nA["<br onclick=alert(1)>"]' }));
  });
  await page.getByText('This diagram could not be displayed. Its source is available below.').waitFor();
  assert.equal(await page.locator('.mermaid-svg svg').count(), 0);
  console.log('Passed: metadata order, harmless breaks, visible labels, actual Mermaid render, fullscreen, unsafe HTML rejection.');
} finally { await browser.close(); }
