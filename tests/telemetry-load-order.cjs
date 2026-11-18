// Retained browser regression: an unavailable analytics host must not block app
// module startup or DOMContentLoaded. A startup canary replaces application code;
// this tests browser scheduling, not full app hydration. Every request stays local.
// Run: node tests/telemetry-load-order.cjs (Chrome required; CHROME_BIN supported).
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');const assert=require('node:assert/strict');
const sourceFiles=["templates/base.html"];
(async()=>{
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'telemetry-load-order-'));
 const chrome=spawn(process.env.CHROME_BIN||'/opt/google/chrome/chrome',['--headless','--disable-gpu','--remote-debugging-pipe','--user-data-dir='+profile,'about:blank'],{detached:true,stdio:['ignore','ignore','ignore','pipe','pipe']});
 let nextId=0,buffer='';const pending=new Map(),states=new Map();
 function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++nextId;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},10000);pending.set(id,m=>{clearTimeout(timer);m.error?reject(Error(m.error.message)):resolve(m)});chrome.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0')})}
 async function handle(m){
  if(m.method!=='Fetch.requestPaused')return;
  const state=states.get(m.sessionId),p=m.params;if(!state)return;
  const url=new URL(p.request.url);
  if(url.hostname==='analytics.ideaflow.app'){state.held++;return;}
  let body='',type='text/plain';
  if(url.pathname==='/'){
   type='text/html';body='<html><head>'+state.tag+'</head><body><div id="root"></div><script>addEventListener("DOMContentLoaded",()=>window.domReady=true)</script><script type="module" src="/app-boot-canary.js"></script></body></html>';
  }else if(url.pathname==='/app-boot-canary.js'){
   type='application/javascript';body='document.getElementById("root").textContent="APP_BOOT_CANARY";window.moduleBoot=true;';
  }
  await send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:type}],body:Buffer.from(body).toString('base64')},m.sessionId);
 }
 chrome.stdio[4].on('data',data=>{buffer+=data.toString();let i;while((i=buffer.indexOf('\0'))>=0){const m=JSON.parse(buffer.slice(0,i));buffer=buffer.slice(i+1);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}else handle(m).catch(e=>{const state=states.get(m.sessionId);if(state)state.error=e.message})}});
 let cases=0;
 try{
  for(const file of sourceFiles){
   const source=fs.readFileSync(path.join(__dirname,'..',file),'utf8').replaceAll('${ANALYTICS_SCRIPT}','https://analytics.ideaflow.app/ideaflow.js').replace(/(<script\b[^>]*?)\/>/gi,'$1></script>');
   const tags=[...source.matchAll(/<script\b[^>]*src=["']https:\/\/analytics\.ideaflow\.app\/ideaflow\.js["'][^>]*>[\s\S]*?<\/script>/gi)].map(x=>x[0]);
   assert.ok(tags.length,file+': actual telemetry tag missing');
   for(const tag of tags){
    assert.match(tag,/\basync(?:\s|>|=)/,file+': analytics must load asynchronously');
    assert.doesNotMatch(tag,/\bdefer(?:\s|>|=)/,file+': ordered defer loading returned');
    for(const control of [false,true]){
     const t=await send('Target.createTarget',{url:'about:blank'}),sid=(await send('Target.attachToTarget',{targetId:t.result.targetId,flatten:true})).result.sessionId;
     const state={tag:control?tag.replace(/\basync\b/,'defer'):tag,held:0};states.set(sid,state);
     await send('Page.enable',{},sid);await send('Fetch.enable',{patterns:[{urlPattern:'*'}]},sid);await send('Page.navigate',{url:'https://telemetry-load-test.invalid/'},sid);
     for(let n=0;n<40&&!state.held;n++)await new Promise(r=>setTimeout(r,10));
     assert.ok(state.held,file+': analytics request was not held');
     await new Promise(r=>setTimeout(r,160));
     const ev=await send('Runtime.evaluate',{expression:'({boot:!!window.moduleBoot,domReady:!!window.domReady,root:document.getElementById("root")?.textContent})',returnByValue:true},sid);
     const value=ev.result.result.value;assert.equal(value.boot,!control,file+': startup while analytics remains stalled');assert.equal(value.domReady,!control,file+': DOMContentLoaded while analytics remains stalled');if(!control)assert.equal(value.root,'APP_BOOT_CANARY');assert.ok(!state.error,state.error);
     await send('Target.closeTarget',{targetId:t.result.targetId});states.delete(sid);cases++;
    }
   }
  }
  console.log('PASS '+cases+' cases: actual async tags boot while analytics is held; old defer controls block. All requests local; zero production events.');
 }finally{if(chrome.exitCode===null&&chrome.signalCode===null){const stopped=new Promise(r=>chrome.once('exit',r));try{process.kill(-chrome.pid,'SIGTERM')}catch{chrome.kill('SIGTERM')}await stopped}fs.rmSync(profile,{recursive:true,force:true,maxRetries:20,retryDelay:250})}
})().catch(e=>{console.error(e);process.exitCode=1});
