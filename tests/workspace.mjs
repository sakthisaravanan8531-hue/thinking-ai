import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
class Element{
 constructor(){this.children=[];this.hidden=false;this.value='';this.textContent='';this.disabled=false;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 get lastElementChild(){return this.children.at(-1);}
 scrollIntoView(){}
 setAttribute(){}
 addEventListener(name,callback){this.listeners??={};this.listeners[name]=callback;}
 requestSubmit(){this.onsubmit?.({preventDefault(){}});}
 showModal(){this.open=true;}
 close(){this.open=false;}
 reportValidity(){return true;}
}
async function setup(admin=false,customFetch=null){
 const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 get('workspace').hidden=true;get('email').value='member@example.com';get('password').value='TemporaryPassword!123';
 const calls=[];
 const context={config:{region:'us-east-1',apiUrl:'https://api',staffClientId:'staff',adminClientId:'admin'},location:{pathname:admin?'/admin.html':'/',reload(){}},document:{getElementById:get,createElement:()=>new Element()},window:{addEventListener(){}},renderMarkdown:(node,text)=>{node.textContent=text;},console,FormData,confirm:()=>false,
 fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body,headers:options.headers});let data;
 if(url.includes('cognito-idp'))data={AuthenticationResult:{IdToken:admin?'admin-token':'staff-token'}};
 else if(url.endsWith('/me'))data={user:{id:'1',name:'Alice',department:admin?null:'hr',admin}};
 else if(url.endsWith('/departments'))data={departments:[{id:'hr',name:'HR',status:'ACTIVE'},{id:'cloud',name:'Cloud',status:'ACTIVE'},{id:'genai',name:'GenAI',status:'ACTIVE'}]};
 else if(url.endsWith('/list'))data={documents:[]};
 else data={answer:'Approved answer [D1]',citations:[{id:'D1',name:'policy.pdf'}],modelId:'configured-model'};
 return {ok:true,status:200,json:async()=>data};}};
 if(customFetch)context.fetch=customFetch;
 vm.createContext(context);let source=fs.readFileSync('dist/workspace.js','utf8').replace(/^import .*;\n/gm,'');vm.runInContext(source,context);
 return {get,calls};
}
const e={preventDefault(){}};
const staff=await setup();assert.equal(staff.calls.length,0,'No anonymous calls on page load');
await staff.get('loginForm').onsubmit(e);assert.equal(staff.get('login').hidden,true);assert.equal(staff.get('displayName').textContent,'Alice');
for(let i=0;i<4;i++){staff.get('prompt').value='Question '+i;await staff.get('chatForm').onsubmit(e);}
assert.equal(staff.get('recents').children.length,1,'Current chat appears in Recents without duplicate entries');
assert.equal(staff.get('recentSection').hidden,false);
const chat=staff.calls.filter(x=>x.url.endsWith('/chat'));assert.equal(chat.length,4);assert.equal(chat[3].body.history.length,5);assert.equal(chat[0].headers.Authorization,'staff-token');assert.equal(Object.hasOwn(chat[0].body,'document'),false);
staff.get('newConversation').onclick();assert.equal(staff.get('conversation').children.length,0);assert.equal(staff.get('recents').children.length,1);
staff.get('recents').children[0].onclick();assert.equal(staff.get('conversation').children.length,8,'Closed chat reopens with all messages');
staff.get('newConversation').onclick();staff.get('prompt').value='Another conversation';await staff.get('chatForm').onsubmit(e);assert.equal(staff.get('recents').children.length,2,'New live chat and saved chat share Recents');
assert(staff.get('recents').children[0].className.includes('current-conversation'));
staff.get('logout').onclick();assert.equal(staff.get('workspace').hidden,true);assert.equal(staff.get('password').value,'');
const admin=await setup(true);await admin.get('loginForm').onsubmit(e);assert(admin.calls.some(x=>x.url.endsWith('/admin/me')));assert(admin.calls.some(x=>x.url.endsWith('/admin/list')));assert.equal(admin.calls[0].body.ClientId,'admin');
const html=fs.readFileSync('dist/index.html','utf8');assert(!/type="file"|Projects|My Documents|Upgrade to Pro/.test(html));
console.log('Passed: login gate, staff/admin client separation, document-free chat payload, five-message request context and unified Recents, Recents and logout.');

// A successful password change consumes the challenge even if /me fails afterward.
let initiated=0,responded=0,meCalls=0;
const reset=await setup(false,async(url,options)=>{
 const payload=JSON.parse(options.body);let data,ok=true,status=200;
 if(url.includes('cognito-idp')){
  if(options.headers['X-Amz-Target'].endsWith('InitiateAuth')){
   initiated++;data=initiated===1?{ChallengeName:'NEW_PASSWORD_REQUIRED',Session:'one-time-session',ChallengeParameters:{USERNAME:'real-user'}}:{AuthenticationResult:{IdToken:'fresh-token'}};
  }else{responded++;assert.equal(payload.Session,'one-time-session');assert.equal(payload.ChallengeResponses.USERNAME,'real-user');data={AuthenticationResult:{IdToken:'first-token'}};}
 }else{meCalls++;if(meCalls===1){ok=false;status=403;data={error:'Department not assigned.'};}else data={user:{name:'Alice',department:'hr'}};}
 return {ok,status,json:async()=>data};
});
await reset.get('loginForm').onsubmit(e);assert.equal(reset.get('signIn').textContent,'Set password & sign in');
reset.get('password').value='NewPassword!123';await reset.get('loginForm').onsubmit(e);
assert.equal(reset.get('signIn').textContent,'Sign in');assert.equal(reset.get('workspace').hidden,true);assert.match(reset.get('notice').textContent,/password was updated/);
reset.get('password').value='NewPassword!123';await reset.get('loginForm').onsubmit(e);
assert.equal(responded,1,'Never resubmit a consumed session');assert.equal(initiated,2);assert.equal(reset.get('workspace').hidden,false);
console.log('Passed: one-time password challenge cleared before authorization, failed authorization returns to sign-in, subsequent login uses fresh authentication.');
// Administrator account controls and public password recovery.
const accountCalls=[];
const people=await setup(true,async(url,options)=>{
 const payload=JSON.parse(options.body);accountCalls.push({url,payload,action:options.headers['X-Amz-Target']});let data;
 if(url.includes('cognito-idp'))data=options.headers['X-Amz-Target'].endsWith('InitiateAuth')?{AuthenticationResult:{IdToken:'admin'}}:{};
 else if(url.endsWith('/admin/me'))data={user:{id:'1',name:'Admin',admin:true}};
 else if(url.endsWith('/admin/departments'))data={departments:[{id:'hr',name:'HR',status:'ACTIVE'},{id:'cloud',name:'Cloud',status:'ACTIVE'},{id:'genai',name:'GenAI',status:'ACTIVE'}]};
 else if(url.endsWith('/admin/list'))data={documents:[]};
 else if(payload.action==='list')data={users:[{username:'me',id:'1',name:'Admin',email:'admin@example.com',roles:['admin'],enabled:true,status:'CONFIRMED'},{username:'staff',id:'2',name:'Staff',email:'staff@example.com',roles:['cloud'],enabled:true,status:'CONFIRMED'}]};
 else data={message:'Invitation sent.'};
 return {ok:true,status:200,json:async()=>data};
});
await people.get('loginForm').onsubmit(e);await people.get('accountsTab').onclick();
assert.equal(people.get('documentPanel').hidden,true);assert.equal(people.get('accountPanel').hidden,false);
assert.equal(people.get('accountsList').children.length,2);
const selfButtons=people.get('accountsList').children[0].lastElementChild.children;assert(selfButtons.every(x=>x.disabled),'Self management disabled in UI');
people.get('accountName').value='New HR User';people.get('accountEmail').value='new@example.com';people.get('accountRole').value='hr';await people.get('createAccountForm').onsubmit(e);
assert(accountCalls.some(x=>x.payload.action==='create'&&x.payload.role==='hr'&&x.payload.email==='new@example.com'));
people.get('openRecovery').onclick();assert.equal(people.get('recoveryDialog').open,true);
people.get('recoveryEmail').value='staff@example.com';await people.get('requestCode').onclick();
people.get('recoveryCode').value='123456';people.get('recoveryPassword').value='NewPassword!123';await people.get('recoveryForm').onsubmit(e);
assert(accountCalls.some(x=>x.action?.endsWith('ConfirmForgotPassword')&&x.payload.ConfirmationCode==='123456'));
assert.equal(people.get('recoveryPassword').value,'');assert.equal(people.get('recoveryDialog').open,false);
console.log('Passed: account tab, account listing, self protection, invitation role, password-reset code request and confirmation.');
// Upload validation and selected team payload.
const uploadCalls=[];
const sharing=await setup(true,async(url,options)=>{
 if(url==='https://upload'){uploadCalls.push({url});return {ok:true,status:204};}
 const payload=JSON.parse(options.body);uploadCalls.push({url,payload});let data;
 if(url.includes('cognito-idp'))data={AuthenticationResult:{IdToken:'admin'}};
 else if(url.endsWith('/admin/me'))data={user:{id:'1',name:'Admin',admin:true}};
 else if(url.endsWith('/admin/departments'))data={departments:[{id:'hr',name:'HR',status:'ACTIVE'},{id:'cloud',name:'Cloud',status:'ACTIVE'},{id:'genai',name:'GenAI',status:'ACTIVE'}]};
 else if(url.endsWith('/admin/list'))data={documents:[]};
 else if(url.endsWith('/admin/prepare'))data={id:'upload-1',upload:{url:'https://upload',fields:{key:'key'}}};
 else data={message:'Published to selected teams.',job:{status:'PENDING'}};
 return {ok:true,status:200,json:async()=>data};
});
await sharing.get('loginForm').onsubmit(e);
sharing.get('file').files=[{name:'big.pdf',size:50*1024*1024+1}];await sharing.get('uploadForm').onsubmit(e);assert.match(sharing.get('adminStatus').textContent,/50 MB/);
const documentFile=new Blob(['test document']);documentFile.name='policy.pdf';sharing.get('file').files=[documentFile];await sharing.get('uploadForm').onsubmit(e);assert.match(sharing.get('adminStatus').textContent,/Select at least one team/);
sharing.get('uploadHr').checked=true;sharing.get('uploadHr').value='hr';sharing.get('uploadCloud').checked=true;sharing.get('uploadCloud').value='cloud';await sharing.get('uploadForm').onsubmit(e);
const prepared=uploadCalls.find(x=>x.url.endsWith('/admin/prepare'));assert.deepEqual(Array.from(prepared.payload.departments),['hr','cloud']);assert.equal(uploadCalls.filter(x=>x.url==='https://upload').length,1);
assert.equal(sharing.get('uploadButton').textContent,'Upload & index');assert.equal(sharing.get('file').disabled,false);
console.log('Passed: 50 MB browser validation, required team selection, multi-team payload and one browser file upload.');

let enterSubmissions=0,prevented=0;staff.get('chatForm').requestSubmit=()=>{enterSubmissions++;};staff.get('prompt').value='Send this';
const key=(extra={})=>({key:'Enter',shiftKey:false,isComposing:false,preventDefault(){prevented++;},...extra});
staff.get('prompt').listeners.keydown(key());assert.equal(enterSubmissions,1);assert.equal(prevented,1);
staff.get('prompt').listeners.keydown(key({shiftKey:true}));assert.equal(enterSubmissions,1);assert.equal(prevented,1);
staff.get('prompt').listeners.keydown(key({isComposing:true}));assert.equal(enterSubmissions,1);
console.log('Passed: current and closed chats share Recents, reopening retains messages, Enter sends, Shift+Enter and IME composition do not send.');
const departmentCalls=[];const teams=[{id:'hr',name:'HR',status:'ACTIVE'},{id:'cloud',name:'Cloud',status:'ACTIVE'}];
const departments=await setup(true,async(url,options)=>{
 const payload=JSON.parse(options.body);departmentCalls.push({url,payload});let data;
 if(url.includes('cognito-idp'))data={AuthenticationResult:{IdToken:'admin'}};
 else if(url.endsWith('/admin/me'))data={user:{id:'1',name:'Admin',admin:true}};
 else if(url.endsWith('/admin/list'))data={documents:[]};
 else if(url.endsWith('/admin/departments')){if(payload.action==='create'){teams.push({id:payload.id,name:payload.name,status:'ACTIVE'});data={message:'Created.'};}else data={departments:teams};}
 else data={users:[]};
 return {ok:true,status:200,json:async()=>data};
});
await departments.get('loginForm').onsubmit(e);await departments.get('departmentsTab').onclick();assert.equal(departments.get('departmentPanel').hidden,false);
departments.get('departmentId').value='finance';departments.get('departmentName').value='Finance';await departments.get('createDepartmentForm').onsubmit(e);
assert(departmentCalls.some(x=>x.payload.action==='create'&&x.payload.id==='finance'));
assert(departments.get('accountRole').children.some(x=>x.value==='finance'));
assert.equal(departments.get('teamChoices').children.length,3);
console.log('Passed: department creation panel, create payload, new upload team and account role options.');
// Fallback indexing controls expose real API operations, not mock AI answers.
const fallbackCalls=[];const fallbacks=await setup(true,async(url,options)=>{
 const payload=JSON.parse(options.body);fallbackCalls.push({url,payload});let data;
 if(url.includes('cognito-idp'))data={AuthenticationResult:{IdToken:'admin'}};
 else if(url.endsWith('/admin/me'))data={user:{id:'1',name:'Admin',admin:true}};
 else if(url.endsWith('/admin/departments'))data={departments:[{id:'cloud',name:'Cloud',status:'ACTIVE'}]};
 else if(url.endsWith('/admin/list'))data={documents:[{id:'doc1',name:'policy.pdf',department:'cloud',status:'ACTIVE',fallbackStatus:'READY'}]};
 else data={fallback:{queued:1,message:'Queued for text indexing.'}};
 return {ok:true,status:200,json:async()=>data};
});
await fallbacks.get('loginForm').onsubmit(e);await fallbacks.get('buildFallback').onclick();
assert(fallbackCalls.some(x=>x.url.endsWith('/admin/fallback-index')&&x.payload.force===false));
const row=fallbacks.get('documents').children[0];assert(row.children.some(x=>x.textContent.includes('Text search: READY')));
assert(row.children.some(x=>x.textContent==='Rebuild text index'));await fallbacks.get('refreshDocuments').onclick();
console.log('Passed: fallback index build API, READY state, per-document rebuild and refresh controls.');
