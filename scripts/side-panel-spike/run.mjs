// Run with PLAYWRIGHT_MODULE pointing to an installed playwright/index.mjs if needed.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
import { fileURLToPath } from 'node:url';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const extension = fileURLToPath(new URL('.', import.meta.url));
import {createServer} from 'node:http';
const server=createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<title>Local advert</title><h1>Example engineer</h1><a target="_blank" href="http://localhost:'+server.address().port+'/apply">Apply</a>');});
await new Promise(r=>server.listen(0,r));
const origin='http://127.0.0.1:'+server.address().port;
for(const [name,executablePath] of [['Chrome for Testing',chromium.executablePath()],['Brave','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']]){
 let ctx;
 const profile = await mkdtemp(join(tmpdir(), 'jobweaver-panel-spike-'));
 try{
 ctx=await chromium.launchPersistentContext(profile,{executablePath,headless:false,ignoreDefaultArgs:['--disable-extensions'],args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`,'--auto-confirm-dialogs-for-testing=accept']});
 const sw=ctx.serviceWorkers()[0]??await ctx.waitForEvent('serviceworker');
 const page=await ctx.newPage();await page.goto(origin);await page.bringToFront();
 console.log(name,'version',await ctx.browser()?.version());
 const id=new URL(sw.url()).host;
 const tabId=await sw.evaluate(async()=>(await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0].id);
 const launch=await ctx.newPage();await launch.goto(`chrome-extension://${id}/launch.html?tab=${tabId}`);
 await launch.getByRole('button').click();console.log(name,'panelOpen',await launch.locator('#result').textContent());
 await page.bringToFront();await page.waitForTimeout(500);
 const cdp=await ctx.newCDPSession(page);
 const panelTarget=(await cdp.send('Target.getTargets')).targetInfos.find(t=>t.url===`chrome-extension://${id}/panel.html`);
 const browserCdp=await ctx.browser().newBrowserCDPSession();
 const {sessionId}=await browserCdp.send('Target.attachToTarget',{targetId:panelTarget.targetId,flatten:false});
 let seq=0;
 const panel=async expression=>{
   const id=++seq;
   const result=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Panel evaluation timed out')),10000);const listener=message=>{if(message.sessionId!==sessionId)return;const reply=JSON.parse(message.message);if(reply.id!==id)return;clearTimeout(timer);browserCdp.off('Target.receivedMessageFromTarget',listener);resolve(reply.result);};browserCdp.on('Target.receivedMessageFromTarget',listener);});
   await browserCdp.send('Target.sendMessageToTarget',{sessionId,message:JSON.stringify({id,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true,userGesture:true}})});
   return (await result).result?.value;
 };
 console.log(name,'panelBeforeGrant',await panel(`(async()=>{document.querySelector('#scan').click();await new Promise(r=>setTimeout(r,300));return document.querySelector('#result').textContent})()`));
 const grant = await panel(`chrome.permissions.request({origins:['http://127.0.0.1/*']})`);
 if (grant !== true) throw new Error('First fixture grant failed');
 console.log(name,'siteGrant',grant);
 console.log(name,'panelAfterGrant',await panel(`(async()=>{document.querySelector('#scan').click();await new Promise(r=>setTimeout(r,300));return document.querySelector('#result').textContent})()`));
 const next=ctx.waitForEvent('page');await page.getByRole('link',{name:'Apply',exact:true}).click();const form=await next;await form.waitForLoadState();await form.bringToFront();
 console.log(name,'newTabWithoutGrant',await panel(`(async()=>{document.querySelector('#scan').click();await new Promise(r=>setTimeout(r,300));return document.querySelector('#result').textContent})()`));
 const newGrant = await panel(`chrome.permissions.request({origins:['http://localhost/*']})`);
 if (newGrant !== true) throw new Error('Second fixture grant failed');
 console.log(name,'newSiteGrant',newGrant);
 console.log(name,'newTabAfterGrant',await panel(`(async()=>{document.querySelector('#scan').click();await new Promise(r=>setTimeout(r,300));return document.querySelector('#result').textContent})()`));
 await form.goto(origin+'/same-tab');
 console.log(name,'crossOriginToGrantedSite',await panel(`(async()=>{document.querySelector('#scan').click();await new Promise(r=>setTimeout(r,300));return document.querySelector('#result').textContent})()`));
 console.log(name,'inject',await sw.evaluate(async()=>{const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});try{return {tabId:tab.id,result:await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>location.href})};}catch(e){return {error:e.message};}}));
 }catch(e){console.error(name,e.message);process.exitCode=1;}finally{await ctx?.close();await rm(profile,{recursive:true,force:true});}
}
server.close();
