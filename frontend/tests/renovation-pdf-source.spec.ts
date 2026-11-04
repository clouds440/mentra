import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';

async function sourceFixture(page: Page, state: 'processing' | 'ready' | 'failed' = 'processing', chunkError = false, metadataOnly = false, diagram = false) {
  await workspace(page);
  const current = { state, chunkReads: 0, visualReads: 0, empty: false, chunkError, extractionError: null as string | null };
  const warnings = Array.from({length:42},(_,i)=>`Page ${i+1} was read with OCR; verify equations and handwriting.`);
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (diagram && path.endsWith('/rag/visuals/diagram-1/source')) {
      current.visualReads++;
      return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ZkAAAAASUVORK5CYII=','base64')});
    }
    if (path.endsWith('/documents/pdf-source')) {
      const ready = current.state === 'ready', failed = current.state === 'failed';
      return route.fulfill({ json: {
        id:'pdf-source',title:'Scanned lecture',filename:'scanned.pdf',context_ids:['context-1'],concept_ids:[],
        archived:false,revision:ready ? 2 : 1,active_generation_id:ready ? 'generation-ready' : null,
        versions:[{id:'pdf-version',filename:'scanned.pdf',size_bytes:1000,media_type:'application/pdf',created_at:'2026-11-03T00:00:00Z',generation_id:ready ? 'generation-ready' : null,warnings:ready ? warnings : [],extraction_state:current.state,extraction_error:current.extractionError ?? (failed ? 'This PDF needs OCR. The server OCR tools are unavailable.' : null)}],version_count:1,
        generations:metadataOnly ? [] : [{id:'generation-ready',version_id:'pdf-version',state:ready ? 'READY' : failed ? 'FAILED' : 'PROCESSING',warnings:ready ? warnings : [],chunk_count:ready ? 1 : 0}],
        jobs:metadataOnly ? [] : [{id:'pdf-job',document_id:'pdf-source',generation_id:'generation-ready',operation:'INGEST',state:ready ? 'SUCCEEDED' : failed ? 'FAILED' : 'RUNNING',stage:ready ? 'ready' : 'parsing',attempts:1,error:failed ? 'This PDF needs OCR. The server OCR tools are unavailable.' : null}],
      } });
    }
    if (path.endsWith('/versions/pdf-version/chunks')) {
      current.chunkReads++;
      if (current.chunkError) return route.fulfill({status:503,json:{error:{code:'UNAVAILABLE',message:'Source passages are temporarily unavailable.'}}});
      return route.fulfill({json:current.state === 'ready' && !current.empty ? [{id:'chunk-1',content:'Scanned body alpha was recovered with OCR.',heading_path:[],spans:[{block:0,start:0,end:45,page:diagram ? null : 1,slide:diagram ? 8 : null,method:'ocr'}],visuals:diagram ? [{id:'diagram-1',caption:'Exception hierarchy',width:1,height:1,media_type:'image/png'}] : []}] : []});
    }
    if (path.endsWith('/files/uploads')) return route.fulfill({json:{id:'upload-file',filename:'scan.pdf',size_bytes:1000,purpose:'library',state:'STAGED'}});
    if (path.endsWith('/documents/pdf-source/versions') && route.request().method()==='POST') return route.fulfill({json:{document_id:'pdf-source',job_id:'upload-job',generation_id:'upload-generation',duplicate:false}});
    return route.fallback();
  });
  await page.goto('/library/pdf-source');
  await page.getByRole('button',{name:'Open source version',exact:true}).click();
  return current;
}

test('a source opened before OCR completes refreshes passages without reopening or permanent warnings', async ({page}) => {
  const state = await sourceFixture(page);
  const viewer = page.getByRole('tabpanel',{name:'scanned.pdf'});
  state.state = 'ready';
  await expect(viewer).toContainText('Scanned body alpha was recovered with OCR.',{timeout:12000});
  await expect(viewer).not.toContainText('Extraction notes');
  await expect(page.getByText(/was read with OCR|may be inaccurate or missing/)).toHaveCount(0);
});

test('an unpublished source shows processing rather than claiming no content', async ({page}) => {
  await sourceFixture(page);
  const viewer = page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer.getByRole('status')).toContainText('Reading and indexing');
  await expect(viewer).not.toContainText('No extracted passages');
});

test('OCR failure remains actionable inside the source viewer', async ({page}) => {
  await sourceFixture(page,'failed');
  const viewer = page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer.getByRole('alert')).toContainText('server OCR tools are unavailable');
  await expect(viewer.getByRole('button',{name:'Download original'})).toBeEnabled();
});

test('a historical failure is visible from version metadata without recent jobs', async ({page}) => {
  await sourceFixture(page,'failed',false,true);
  await expect(page.getByRole('tabpanel',{name:'scanned.pdf'}).getByRole('alert')).toContainText('server OCR tools are unavailable');
});

test('a passage read error never also claims that extraction produced no content', async ({page}) => {
  const state=await sourceFixture(page,'ready',true);
  const viewer = page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer.getByRole('alert')).toBeVisible();
  await expect(viewer).not.toContainText('No extracted passages');
  await expect(viewer.getByRole('button',{name:'Refresh content'})).toBeVisible();
  state.chunkError=false;
  await viewer.getByRole('button',{name:'Refresh content'}).click();
  await expect(viewer).toContainText('Scanned body alpha was recovered with OCR.');
});

test('failure of a newer reindex does not hide previously published content', async ({page}) => {
  const state=await sourceFixture(page);
  state.state='ready'; state.extractionError='OCR needs repair.';
  const viewer=page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer).toContainText('Scanned body alpha was recovered with OCR.',{timeout:12000});
  await expect(viewer.getByRole('alert')).toContainText('Showing the previously indexed content.');
});

test('an indexed source with missing passages reports a load inconsistency', async ({page}) => {
  const state=await sourceFixture(page);
  state.empty=true; state.state='ready';
  const viewer=page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer).toContainText('This source was indexed, but its extracted passages could not be loaded.',{timeout:12000});
  await expect(viewer.getByRole('button',{name:'Refresh content'})).toBeVisible();
  state.empty=false;
  await viewer.getByRole('button',{name:'Refresh content'}).click();
  await expect(viewer).toContainText('Scanned body alpha was recovered with OCR.');
});

test('unsaved title edits cannot freeze source processing progress', async ({page}) => {
  const state=await sourceFixture(page);
  await page.getByRole('button',{name:'Close side panel',exact:true}).click();
  await page.getByLabel('Title',{exact:true}).fill('My unsaved lecture title');
  await page.getByRole('button',{name:'Open source version',exact:true}).click();
  state.state='ready';
  await expect(page.getByRole('tabpanel',{name:'scanned.pdf'})).toContainText('Scanned body alpha was recovered with OCR.',{timeout:12000});
  await page.getByRole('button',{name:'Close side panel',exact:true}).click();
  await expect(page.getByLabel('Title',{exact:true})).toHaveValue('My unsaved lecture title');
});

test('one OCR notice appears only for the selected upload and disappears after acceptance', async ({page}) => {
  await sourceFixture(page,'ready');
  await page.getByRole('button',{name:'Close side panel',exact:true}).click();
  await expect(page.getByRole('status',{name:'OCR upload notice'})).toHaveCount(0);
  await expect(page.getByText(/Extraction notes|may be inaccurate or missing/)).toHaveCount(0);
  await page.getByLabel('File',{exact:true}).setInputFiles({name:'scan.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF synthetic')});
  await expect(page.getByRole('status',{name:'OCR upload notice'})).toHaveCount(1);
  await page.getByRole('button',{name:'Submit replacement',exact:true}).click();
  await expect(page.getByRole('status',{name:'OCR upload notice'})).toHaveCount(0);
  await page.getByRole('button',{name:'Open source version',exact:true}).click();
  await expect(page.getByRole('tabpanel',{name:'scanned.pdf'})).toContainText('Scanned body alpha');
  await expect(page.getByText(/Extraction notes|may be inaccurate or missing/)).toHaveCount(0);
});

test('source diagrams load through authenticated delivery beside their passage without extraction warnings', async ({page}) => {
  const state=await sourceFixture(page,'ready',false,false,true);
  const viewer=page.getByRole('tabpanel',{name:'scanned.pdf'});
  await expect(viewer.getByRole('img',{name:'Exception hierarchy'})).toBeVisible();
  await expect.poll(() => viewer.getByRole('img',{name:'Exception hierarchy'}).evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  expect(state.visualReads).toBe(1);
  await expect(viewer).toContainText('Slide 8');
  await expect(page.getByText(/was read with OCR|Extraction notes/)).toHaveCount(0);
});
