import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

const created='2026-10-17T00:00:00Z';
const hit={conversation_id:'older-chat',title:'A saved explanation of motion, force and acceleration',matched_message_id:'old-message',sequence:3,role:'assistant',snippet:'The cart accelerates because the resultant force is nonzero.',created_at:created,matched_in:'message'};

for (const viewport of [{width:360,height:740,theme:'light'},{width:390,height:844,theme:'dark'},{width:768,height:1024,theme:'light'},{width:1440,height:1000,theme:'dark'}] as const) {
  test(`saved chat search opens an unloaded exchange and preserves Back at ${viewport.width} ${viewport.theme}`,async ({page},info) => {
    await workspace(page);
    await page.setViewportSize(viewport);
    await page.addInitScript(theme=>localStorage.setItem('mentra-theme',theme),viewport.theme);
    const requests: string[]=[];
    await page.route('**/api/v1/conversations/search?*',route=>{
      const query=new URL(route.request().url()).searchParams.get('query') ?? ''; requests.push(query);
      return route.fulfill({json:{items:query ? [hit] : [],next_offset:null,truncated:false}});
    });
    await page.route('**/api/v1/conversations/older-chat/messages/old-message/window',route=>route.fulfill({json:{conversation_id:hit.conversation_id,title:hit.title,matched_message_id:hit.matched_message_id,messages:[
      {id:'earlier-question',role:'user',content:'Why does the cart accelerate?',created_at:created},
      {id:'old-message',role:'assistant',content:'An old explanation that is absent from the latest window.\n\n$$F = ma$$',created_at:created},
    ]}}));
    await page.goto('/chat/polish-chat');
    await expect(page.locator('html')).toHaveAttribute('data-theme',viewport.theme);
    if (viewport.width<1024) await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
    await page.getByRole('button',{name:'Search saved chats',exact:true}).click();
    const search=page.getByRole('dialog',{name:'Search your chats',exact:true});
    const input=search.getByRole('searchbox',{name:'Search chat titles and messages',exact:true});
    await expect(input).toBeFocused();
    await input.fill('رفتار force');
    const result=search.getByRole('link').filter({hasText:hit.title});
    await expect(result).toBeVisible();
    expect(requests.at(-1)).toBe('رفتار force');
    await page.screenshot({path:info.outputPath(`search-${viewport.width}-${viewport.theme}.png`),animations:'disabled'});
    await input.press('Tab'); await expect(result).toBeFocused(); await page.keyboard.press('Enter');
    const exchange=page.getByRole('dialog',{name:hit.title,exact:true});
    await expect(exchange.getByRole('region',{name:'Matching message',exact:true})).toBeFocused();
    await expect(exchange).toContainText('An old explanation that is absent from the latest window.');
    await expect(exchange.locator('.katex')).toHaveCount(1);
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath(`exchange-${viewport.width}-${viewport.theme}.png`),animations:'disabled'});
    await page.goBack();
    await expect(page.getByRole('dialog',{name:'Search your chats',exact:true}).getByRole('searchbox')).toHaveValue('رفتار force');
  });
}

test('search aborts stale results and retries a failure without clearing the phrase',async ({page})=>{
  await workspace(page);
  let release:()=>void=()=>{}, fail=true;
  await page.route('**/api/v1/conversations/search?*',async route=>{
    const query=new URL(route.request().url()).searchParams.get('query');
    if(query==='old') { await new Promise<void>(resolve=>{release=resolve;}); return route.fulfill({json:{items:[{...hit,title:'Old private hit'}],next_offset:null,truncated:false}}).catch(()=>{}); }
    if(fail) return route.fulfill({status:503,json:{error:{code:'CHAT_SEARCH_BUSY',message:'Busy'}}});
    return route.fulfill({json:{items:[hit],next_offset:null,truncated:false}});
  });
  await page.goto('/chat/polish-chat?search_open=1');
  const dialog=page.getByRole('dialog',{name:'Search your chats',exact:true});
  const input=dialog.getByRole('searchbox');
  await input.fill('old');
  await page.waitForRequest(request=>request.url().includes('query=old'));
  await input.fill('new');
  await expect(dialog.getByRole('alert')).toContainText('Try a more specific phrase');
  release(); fail=false;
  await dialog.getByRole('button',{name:'Retry search'}).click();
  await expect(dialog.getByRole('link').filter({hasText:hit.title})).toBeVisible();
  await expect(dialog).not.toContainText('Old private hit');
  await expect(input).toHaveValue('new');
});
