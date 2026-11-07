import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { workspace } from './renovation-fixtures';
import type { BulkChatRequest, ChatManagementJob, Conversation } from '../src/types/conversations';

async function organization(page: Page) {
  await workspace(page);
  const stamp = '2026-11-07T01:00:00Z';
  let rows: Conversation[] = ['Mechanics', 'Algebra', 'Revision notes'].map((title, i) => ({id:`chat-${i}`,title,revision:2,message_count:2,selection:{mode:'STANDARD',context_ids:[],document_ids:[],include_archived:false},created_at:stamp,updated_at:stamp,deleted_at:null,archived_at:i === 2 ? stamp : null,pinned_at:null,pending_action:null,pending_action_id:null}));
  const jobs = new Map<string, ChatManagementJob>();
  const requests: BulkChatRequest[] = [];
  let finish = false, reject = false, loseResponse = false;
  const searches: boolean[] = [];
  await page.route('**/api/v1/conversations**', async route => {
    const url = new URL(route.request().url()), path = url.pathname, method = route.request().method();
    if (path.endsWith('/sync')) return route.fulfill({json:{reset:true,cursor:1,has_more:false,conversations:rows.filter(row => !row.deleted_at),deleted_ids:rows.filter(row => row.deleted_at).map(row => row.id),list_cursor:null}});
    if (path.endsWith('/organization')) {
      const row = rows.find(row => path.includes(`/${row.id}/`))!;
      const body = route.request().postDataJSON();
      row.revision++;
      if ('pinned' in body) row.pinned_at = body.pinned ? stamp : null;
      if ('archived' in body) { row.archived_at = body.archived ? stamp : null; if (body.archived) row.pinned_at = null; }
      return route.fulfill({json:row});
    }
    if (path.endsWith('/bulk') && method === 'POST') {
      const body: BulkChatRequest = route.request().postDataJSON(); requests.push(body);
      if (reject) return route.fulfill({status:409,json:{code:'CHAT_REVISION_CONFLICT',message:'Synthetic conflict'}});
      if (!jobs.has(body.client_request_id)) {
        jobs.set(body.client_request_id, {id:body.client_request_id,action:body.action,items:body.items,completed_ids:[],failed_items:[],state:'queued'});
        rows = rows.map(row => body.items.some(item => item.conversation_id === row.id) ? {...row,revision:row.revision+1,pending_action:body.action,pending_action_id:body.client_request_id} : row);
      }
      if (loseResponse) { loseResponse = false; return route.abort('connectionreset'); }
      // Keep acknowledgement pending long enough to prove navigation is immediate.
      await new Promise(resolve => setTimeout(resolve, 450));
      return route.fulfill({status:202,json:jobs.get(body.client_request_id)});
    }
    if (path.includes('/bulk/')) {
      const job = jobs.get(path.split('/').pop()!)!;
      if (finish && job.state !== 'completed') {
        job.state = 'completed'; job.completed_ids = job.items.map(item => item.conversation_id);
        rows = rows.map(row => job.completed_ids.includes(row.id) ? {...row,revision:row.revision+1,pending_action:null,pending_action_id:null,...(job.action === 'delete' ? {deleted_at:stamp} : {archived_at:job.action === 'archive' ? stamp : null,pinned_at:null})} : row);
      }
      return route.fulfill({json:job});
    }
    if (path.endsWith('/search')) {
      const include = url.searchParams.get('include_archived') === 'true'; searches.push(include);
      return route.fulfill({json:{items:include ? [{conversation_id:'chat-2',title:'Revision notes',matched_message_id:'message-2',sequence:1,role:'user',snippet:'Revision needle',created_at:stamp,matched_in:'message',archived_at:stamp}] : [],next_offset:null,truncated:false}});
    }
    if (path.endsWith('/status')) {
      const row = rows.find(row => path.includes(`/${row.id}/`))!;
      return route.fulfill({json:{conversation:row,items:[],has_more:false,next_cursor:null,turn:null}});
    }
    if (method === 'PATCH') {
      const row = rows.find(row => path.endsWith(`/${row.id}`))!;
      row.title = route.request().postDataJSON().title; row.revision++;
      return route.fulfill({json:row});
    }
    if (path.endsWith('/conversations')) return route.fulfill({json:{items:rows.filter(row => !row.deleted_at && !!row.archived_at === (url.searchParams.get('archived') === 'true')),next_cursor:null}});
    return route.fallback();
  });
  return {requests,searches, finish:() => {finish=true;},reject:() => {reject=true;}, loseResponse:() => {loseResponse=true;}};
}

async function selectMechanics(page: Page) {
  await page.getByRole('link',{name:'Mechanics',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Mechanics'}).click();
  await page.getByRole('menuitem',{name:'Select',exact:true}).click();
  await expect(page.getByRole('checkbox',{name:'Select Mechanics',exact:true})).toBeChecked();
}

test('pinning, unpinning, archived settings and explicit archived search', async ({page}) => {
  const fixture = await organization(page);
  await page.goto('/');
  await page.getByRole('link',{name:'Mechanics',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Mechanics'}).click();
  await expect(page.getByRole('menuitem',{name:'Rename',exact:true})).toBeVisible();
  await expect(page.getByRole('menuitem',{name:'Delete',exact:true})).toBeVisible();
  await page.getByRole('menuitem',{name:'Pin',exact:true}).click();
  await expect(page.getByRole('region',{name:'Pinned chats'}).getByRole('link',{name:'Mechanics',exact:true})).toBeVisible();
  expect(await page.getByRole('region',{name:'Pinned chats'}).evaluate(node => node.getBoundingClientRect().top)).toBeLessThan(await page.getByRole('button',{name:'Recents',exact:true}).evaluate(node => node.getBoundingClientRect().top));
  await page.reload();
  await expect(page.getByRole('region',{name:'Pinned chats'})).toBeVisible();
  await page.getByRole('link',{name:'Mechanics',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Mechanics'}).click();
  await page.getByRole('menuitem',{name:'Unpin',exact:true}).click();
  await expect(page.getByRole('region',{name:'Pinned chats'})).toHaveCount(0);
  await page.getByRole('button',{name:'Search saved chats'}).click();
  await page.getByRole('searchbox',{name:'Search chat titles and messages'}).fill('needle');
  await expect(page.getByText('No matching chats', {exact:true})).toBeVisible();
  expect(fixture.searches.at(-1)).toBe(false);
  await page.getByRole('switch',{name:'Include archived chats'}).click();
  await expect(page.getByRole('link').filter({hasText:'Revision notes'})).toBeVisible();
  expect(fixture.searches.at(-1)).toBe(true);
  await page.keyboard.press('Escape');
  await page.goto('/settings?tab=archive');
  await expect(page.getByRole('tab',{name:'Archived chats'})).toHaveAttribute('aria-selected','true');
  await page.locator('.archived-chat-list').getByRole('link',{name:'Revision notes',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Revision notes'}).click();
  await page.getByRole('menuitem',{name:'Unarchive',exact:true}).click();
  await expect(page.getByRole('heading',{name:'No archived chats'})).toBeVisible();
  await expect(page.getByRole('region',{name:'Conversation history'}).getByRole('link',{name:'Revision notes',exact:true})).toBeVisible();
});

for (const theme of ['light','dark']) test(`bulk deletion returns immediately, disables pending rows and recovers on reload in ${theme}`, async ({page}, info) => {
  const fixture = await organization(page);
  await page.addInitScript(value => localStorage.setItem('mentra-theme',value), theme);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/chat/chat-0');
  await selectMechanics(page);
  await page.getByRole('checkbox',{name:'Select Algebra',exact:true}).click();
  await expect(page.getByRole('toolbar',{name:'Chat selection'})).toContainText('2');
  const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations.map(item => ({id:item.id,targets:item.nodes.map(node => node.target)}))).toEqual([]);
  await page.screenshot({path:info.outputPath(`selection-${theme}.png`)});
  await page.getByRole('button',{name:'Delete selected chats'}).click();
  const dialog = page.getByRole('dialog',{name:'Delete 2 chats?'});
  await expect(dialog).toContainText('This cannot be undone.');
  await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
  await dialog.getByRole('button',{name:'Delete 2 chats',exact:true}).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('textbox',{name:'Ask Mentra anything'})).toBeVisible();
  await expect(page.locator('[data-pending-action="delete"]')).toHaveCount(2);
  await expect(page.getByRole('link',{name:'Mechanics',exact:true})).toHaveCount(0);
  await expect.poll(() => fixture.requests.length).toBe(1);
  await page.reload();
  await expect(page.locator('[data-pending-action="delete"]')).toHaveCount(2);
  fixture.finish();
  await expect(page.locator('[data-pending-action="delete"]')).toHaveCount(0);
  await expect(page.getByText('Deleted 2 chats.',{exact:true})).toBeVisible();
  // Reload may interrupt admission before the response; replay must retain UUID/payload.
  expect(new Set(fixture.requests.map(request => request.client_request_id)).size).toBe(1);
  expect(fixture.requests.every(request => JSON.stringify(request) === JSON.stringify(fixture.requests[0]))).toBe(true);
});

test('lost admission response replays the same UUID; archive finishes in background', async ({page}) => {
  const fixture = await organization(page); fixture.loseResponse();
  await page.goto('/chat/chat-0');
  await selectMechanics(page);
  await page.getByRole('button',{name:'Archive selected chats'}).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('[data-pending-action="archive"]')).toHaveCount(1);
  await expect.poll(() => fixture.requests.length).toBeGreaterThanOrEqual(2);
  expect(fixture.requests[0]).toEqual(fixture.requests[1]);
  fixture.finish();
  await expect(page.getByText('Archived 1 chat.',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Mechanics',exact:true})).toHaveCount(0);
  await page.goto('/settings?tab=archive');
  await expect(page.locator('.archived-chat-list').getByRole('link',{name:'Mechanics',exact:true})).toBeVisible();
});

test('rejected selection returns rows to their usable state and explains failure', async ({page}) => {
  const fixture = await organization(page); fixture.reject();
  await page.goto('/');
  await selectMechanics(page);
  await page.getByRole('button',{name:'Archive selected chats'}).click();
  await expect(page.getByRole('alert')).toContainText('changed');
  await expect(page.locator('[data-pending-action]')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Mechanics',exact:true})).toBeVisible();
});

test('archive keeps rename and supports keyboard exit and bulk unarchive', async ({page}, info) => {
  const fixture = await organization(page);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/settings?tab=archive');
  const archive = page.locator('.archived-chat-list');
  await archive.getByRole('link',{name:'Revision notes',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Revision notes'}).click();
  await page.getByRole('menuitem',{name:'Rename',exact:true}).click();
  await page.getByRole('textbox',{name:'Conversation title'}).fill('Saved for later');
  await page.getByRole('button',{name:'Save conversation title'}).click();
  await expect(archive.getByRole('link',{name:'Saved for later',exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath('archived-settings.png')});
  await archive.getByRole('link',{name:'Saved for later',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Saved for later'}).click();
  await page.getByRole('menuitem',{name:'Select',exact:true}).click();
  const checkbox = page.getByRole('checkbox',{name:'Select Saved for later',exact:true});
  await checkbox.focus(); await page.keyboard.press('Escape');
  await expect(page.getByRole('toolbar',{name:'Chat selection'})).toHaveCount(0);
  await archive.getByRole('link',{name:'Saved for later',exact:true}).hover();
  await page.getByRole('button',{name:'Actions for Saved for later'}).click();
  await page.getByRole('menuitem',{name:'Select',exact:true}).click();
  await page.getByRole('button',{name:'Unarchive selected chats'}).click();
  await expect(page).toHaveURL(/\/$/);
  fixture.finish();
  await expect(page.getByText('Unarchived 1 chat.',{exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Conversation history'}).getByRole('link',{name:'Saved for later',exact:true})).toBeVisible();
});

test('mobile long press selection fits Mentra drawer and Escape exits selection', async ({browser}, info) => {
  const context = await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true,reducedMotion:'reduce'});
  const page = await context.newPage(); await organization(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Open navigation menu'}).click();
  const row = page.getByRole('link',{name:'Mechanics',exact:true});
  const pointer = {pointerId:1,pointerType:'touch',isPrimary:true,button:0,clientX:90,clientY:330};
  await row.dispatchEvent('pointerdown',pointer);
  await expect(page.getByRole('menuitem',{name:'Select',exact:true})).toBeVisible();
  await row.dispatchEvent('pointerup',pointer);
  await page.getByRole('menuitem',{name:'Select',exact:true}).click();
  await expect(page.getByRole('checkbox',{name:'Select Mechanics',exact:true})).toBeChecked();
  const toolbar = page.getByRole('toolbar',{name:'Chat selection'});
  expect(await toolbar.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  expect(await toolbar.evaluate(node => node.getBoundingClientRect().right <= innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('mobile-selection.png')});
  await page.keyboard.press('Escape');
  await expect(toolbar).toHaveCount(0);
  await context.close();
});
