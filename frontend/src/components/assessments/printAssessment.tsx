import { renderToStaticMarkup } from 'react-dom/server';
import type { Assessment } from '../../types/assessments';
import { AssessmentPaper } from './AssessmentPaper';

/** Print an isolated question paper; never include answers, grading keys or chat. */
export async function printAssessment(assessment: Assessment) {
  const frame=document.createElement('iframe');
  const opener=document.activeElement instanceof HTMLElement ? document.activeElement : null;
  let cleaned=false;
  const finish=() => { if (cleaned) return; cleaned=true; const restore=document.activeElement===frame || document.activeElement===document.body; frame.remove(); if(restore && opener?.isConnected) opener.focus({preventScroll:true}); };
  frame.title='Printable assessment'; frame.setAttribute('aria-hidden','true');
  Object.assign(frame.style,{position:'fixed',width:'0',height:'0',border:'0',visibility:'hidden'});
  document.body.append(frame);
  try {
    const target=frame.contentDocument!, view=frame.contentWindow!;
    target.documentElement.dataset.theme='light'; target.title=assessment.title;
    const styles=Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')).map(link => new Promise<void>(resolve => {
      const copy=target.createElement('link'); copy.rel='stylesheet'; copy.href=link.href; copy.onload=copy.onerror=() => resolve(); target.head.append(copy); setTimeout(resolve,5000);
    }));
    const title=target.createElement('h1'); title.textContent=assessment.title;
    target.body.append(title);
    const content=target.createElement('main'); content.innerHTML=renderToStaticMarkup(<AssessmentPaper assessment={assessment} printMode />); target.body.append(content);
    const css=target.createElement('style'); css.textContent='@page{size:A4;margin:15mm}html,body{height:auto!important;overflow:visible!important;background:white!important;color:#111!important}body{padding:0;font:12px/1.6 system-ui}h1{font-size:22px;font-weight:700;margin:0 0 20px}button,.code-actions{display:none!important}section{break-inside:avoid-page}pre{white-space:pre-wrap!important;overflow-wrap:anywhere}a{color:inherit}*{animation:none!important;box-shadow:none!important}'; target.head.append(css);
    await Promise.all(styles); await target.fonts.ready;
    await Promise.all(Array.from(target.images).map(image => image.complete ? Promise.resolve() : new Promise<void>(resolve => { image.onload=image.onerror=()=>resolve(); setTimeout(resolve,5000); })));
    view.addEventListener('afterprint',finish,{once:true});
    view.focus(); view.print(); setTimeout(finish,60_000);
  } catch (error) { finish(); throw error; }
}
