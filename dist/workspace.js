import config from './config.js';
import {renderMarkdown} from './markdown.js';
const admin=location.pathname.endsWith('/admin.html');
const $=id=>document.getElementById(id);
let pendingUpload='',token='',challenge='',challengeUsername='',user=null,messages=[],sessions=[],activeConversationId='',conversationSequence=0,busy=false,job='';
const clientId=admin?config.adminClientId:config.staffClientId;
async function cognito(action,body){
 const r=await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`,{method:'POST',headers:{'Content-Type':'application/x-amz-json-1.1','X-Amz-Target':'AWSCognitoIdentityProviderService.'+action},body:JSON.stringify(body)});
 const data=await r.json();if(!r.ok)throw Error(data.message||'Sign-in failed.');return data;
}
async function api(path,data={}){
 if(!token)throw Error('Please sign in.');
 const requestToken=token;
 const r=await fetch(config.apiUrl+path,{method:'POST',headers:{Authorization:token,'Content-Type':'application/json'},body:JSON.stringify(data)});
 if(token!==requestToken)throw Error('Session changed. Request discarded.');
 const result=await r.json().catch(()=>({error:'The workspace backend needs to be deployed.'}));
 if(r.status===401){logout();throw Error('Your session expired. Please sign in again.');}
 if(!r.ok)throw Error(result.error||'The workspace backend needs to be deployed.');return result;
}
function logout(){pendingUpload='';token='';challenge='';challengeUsername='';user=null;messages=[];sessions=[];activeConversationId='';$('workspace').hidden=true;$('login').hidden=false;$('password').value='';$('email').value='';$('signIn').textContent='Sign in';$('notice').textContent='';}
$('loginForm').onsubmit=async e=>{e.preventDefault();if($('signIn').disabled)return;$('signIn').disabled=true;let passwordChanged=false;$('notice').textContent='Signing in…';
 try{
 if(!clientId)throw Error('Admin login is not configured. Run configure-site.ps1 after backend deployment.');
 const data=challenge?await cognito('RespondToAuthChallenge',{ClientId:clientId,ChallengeName:'NEW_PASSWORD_REQUIRED',Session:challenge,ChallengeResponses:{USERNAME:challengeUsername,NEW_PASSWORD:$('password').value}}):await cognito('InitiateAuth',{ClientId:clientId,AuthFlow:'USER_PASSWORD_AUTH',AuthParameters:{USERNAME:$('email').value.trim(),PASSWORD:$('password').value}});
 if(data.ChallengeName==='NEW_PASSWORD_REQUIRED'){challenge=data.Session;challengeUsername=data.ChallengeParameters?.USER_ID_FOR_SRP||data.ChallengeParameters?.USERNAME||$('email').value.trim();$('password').value='';$('password').minLength=12;$('notice').textContent='Set a new password: 12+ characters, uppercase, lowercase, number and symbol.';$('signIn').textContent='Set password & sign in';return;}
 if(!data.AuthenticationResult?.IdToken)throw Error('This account needs an unsupported authentication challenge. Contact your administrator.');
 passwordChanged=!!challenge;challenge='';challengeUsername='';$('signIn').textContent='Sign in';$('password').minLength=1;
 token=data.AuthenticationResult.IdToken;
 user=(await api(admin?'/admin/me':'/me')).user;$('login').hidden=true;$('workspace').hidden=false;$('displayName').textContent=user.name;$('departmentLabel').textContent=admin?'Administrator':(user.departmentName||user.department.toUpperCase())+' team';$('password').value='';$('notice').textContent='';
 if(admin){try{await loadDepartments();await loadDocuments();}catch(error){$('adminStatus').textContent=error.message;}}else render();
 }catch(e){token='';challenge='';challengeUsername='';user=null;$('workspace').hidden=true;$('login').hidden=false;$('signIn').textContent='Sign in';$('password').minLength=1;$('password').value='';
 const invalidSession=/invalid session|session.*(?:once|expired)/i.test(e.message);
 $('notice').textContent=passwordChanged?'Your password was updated. Sign in with your new password. '+e.message:invalidSession?'Your password-change session ended. Sign in again with your new password if it was saved, or your temporary password if it was not.':e.message;
 }finally{$('signIn').disabled=false;}
};
$('logout').onclick=logout;
function element(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
function saveCurrentConversation(){
 if(!messages.length)return;
 if(!activeConversationId)activeConversationId='conversation-'+(++conversationSequence);
 const entry={id:activeConversationId,title:messages.find(x=>x.role==='user')?.text||'Conversation',messages:[...messages]};
 const index=sessions.findIndex(x=>x.id===activeConversationId);if(index>=0)sessions.splice(index,1);sessions.unshift(entry);
}
function newConversation(){if(busy)return;saveCurrentConversation();activeConversationId='';messages=[];render();}
function render(){
 const feed=$('conversation');feed.replaceChildren();$('welcome').hidden=!!messages.length;
 messages.forEach((m,i)=>{const box=element('article','',m.role);box.id='message-'+i;box.append(element('div',m.role==='user'?'You':'Thinking AI','role'));const body=element('div','');if(m.role==='assistant')renderMarkdown(body,m.text);else body.textContent=m.text;box.append(body);if(m.citations?.length)box.append(element('p',m.citations.map(x=>`[${x.id}] ${x.name}`).join(' · '),'sources'));feed.append(box);});
 saveCurrentConversation();
 const recent=$('recents');recent.replaceChildren();sessions.forEach(session=>{
  const button=element('button',session.title.slice(0,60),'history'+(session.id===activeConversationId?' current-conversation':''));button.disabled=busy;
  if(session.id===activeConversationId)button.setAttribute('aria-current','page');
  button.onclick=()=>{if(busy)return;saveCurrentConversation();activeConversationId=session.id;messages=[...session.messages];render();};recent.append(button);
 });$('recentSection').hidden=!sessions.length;
}
if(!admin){$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!busy&&$('prompt').value.trim())$('chatForm').requestSubmit();}});$('newConversation').onclick=newConversation;$('brand').onclick=newConversation;
 $('chatForm').onsubmit=async e=>{e.preventDefault();if(busy)return;const question=$('prompt').value.trim();if(!question)return;const history=messages.slice(-5).map(x=>({role:x.role,text:x.text.slice(0,3000)}));messages.push({role:'user',text:question});$('prompt').value='';busy=true;$('send').disabled=true;$('chatStatus').textContent='Searching your department’s documents…';render();
 try{const data=await api('/chat',{question,history});messages.push({role:'assistant',text:data.answer,citations:data.citations});$('chatStatus').textContent=data.modelId?`Answer model: ${data.modelId}`+(data.answerMode==='verified-excerpts'?' · Verified document excerpts':data.answerMode==='document-topic-explanation'?' · Document topic explanation':'')+(data.retrieval==='text-search'?' · Fallback text search':'')+(data.partialSearch?' · Search covers indexed excerpts only':''):'';}
 catch(e){$('chatStatus').textContent=e.message;}finally{busy=false;$('send').disabled=false;render();$('conversation').lastElementChild?.scrollIntoView({behavior:'smooth'});}};
}
async function showJob(result){if(result?.job){job=result.job.ingestionJobId||'';$('adminStatus').textContent=(result.message?result.message+' ':'')+'Indexing: '+result.job.status+(result.job.message?' — '+result.job.message:'');}if(result?.fallback)$('adminStatus').textContent+=' '+result.fallback.message;}
async function loadDocuments(){const data=await api('/admin/list');$('documents').replaceChildren();for(const d of data.documents){const row=element('div','','document');row.append(element('div',d.name),element('span',d.department.toUpperCase()+' · '+d.status+(d.cleanupPending?' · Cleanup pending':'')+' · Text search: '+(d.fallbackStatus||'NOT INDEXED')+(d.fallbackError?' ('+d.fallbackError+')':''),'sources'));const del=element('button','Delete','danger');del.onclick=async()=>{if(!confirm('Delete '+d.name+'? This immediately blocks its answers.'))return;try{await showJob(await api('/admin/delete',{id:d.id}));await loadDocuments();}catch(e){$('adminStatus').textContent=e.message;}};row.append(del);if(d.status==='ACTIVE'){const reindex=element('button','Rebuild text index','secondary');reindex.onclick=async()=>{reindex.disabled=true;try{const result=await api('/admin/fallback-index',{ids:[d.id],force:true});$('adminStatus').textContent=result.fallback.message;await loadDocuments();}catch(error){$('adminStatus').textContent=error.message;}finally{reindex.disabled=false;}};row.append(reindex);}$('documents').append(row);}}
if(admin){$('uploadForm').onsubmit=async e=>{e.preventDefault();if($('uploadButton').disabled)return;$('uploadButton').disabled=true;
 try{
  if(!pendingUpload){
   const file=$('file').files[0];if(!file)throw Error('Choose a document.');
   if(file.size>50*1024*1024)throw Error('Document limit: 50 MB.');
   const departments=uploadDepartmentOptions.filter(option=>$(option.inputId).checked).map(option=>option.id);
   if(!departments.length)throw Error('Select at least one team.');if(departments.length>10)throw Error('Select up to 10 teams per upload.');
   $('adminStatus').textContent='Preparing upload…';
   const prepared=await api('/admin/prepare',{name:file.name,size:file.size,departments});
   const form=new FormData();for(const[k,v]of Object.entries(prepared.upload.fields))form.append(k,v);form.append('file',file);
   const response=await fetch(prepared.upload.url,{method:'POST',body:form});if(!response.ok)throw Error('Upload failed. Please try again.');
   pendingUpload=prepared.id;$('file').disabled=true;$('uploadTeams').disabled=true;
  }
  $('adminStatus').textContent='Publishing approved copies to the selected teams…';
  await showJob(await api('/admin/complete',{id:pendingUpload}));
  pendingUpload='';$('file').value='';$('file').disabled=false;$('uploadTeams').disabled=false;
  await loadDocuments();
 }catch(error){$('adminStatus').textContent=error.message+(pendingUpload?' Click Retry publishing to finish this upload without sending the file again.':'');}
 finally{$('uploadButton').disabled=false;$('uploadButton').textContent=pendingUpload?'Retry publishing':'Upload & index';}
 };
 $('sync').onclick=async()=>{try{await showJob(await api('/admin/sync'));}catch(e){$('adminStatus').textContent=e.message;}};
 $('checkJob').onclick=async()=>{try{if(!job)throw Error('Start a sync first.');await showJob(await api('/admin/job',{id:job}));}catch(e){$('adminStatus').textContent=e.message;}};
}
// Tokens, recents and messages live only in this tab's memory. Refresh requires login.
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});

// Password reset codes are exchanged directly with Cognito; neither passwords nor codes reach Lambda.
$('openRecovery').onclick=()=>{$('recoveryEmail').value=$('email').value;$('recoveryStatus').textContent='';$('recoveryDialog').showModal();};
$('closeRecovery').onclick=()=>{$('recoveryPassword').value='';$('recoveryCode').value='';$('recoveryDialog').close();};
$('requestCode').onclick=async()=>{
 if(!$('recoveryEmail').reportValidity())return;
 $('requestCode').disabled=true;
 try{await cognito('ForgotPassword',{ClientId:clientId,Username:$('recoveryEmail').value.trim()});$('recoveryStatus').textContent='If your account is eligible, a reset code has been sent. Check your email.';}
 catch(error){$('recoveryStatus').textContent=error.message;}finally{$('requestCode').disabled=false;}
};
$('recoveryForm').onsubmit=async e=>{e.preventDefault();$('confirmRecovery').disabled=true;
 try{await cognito('ConfirmForgotPassword',{ClientId:clientId,Username:$('recoveryEmail').value.trim(),ConfirmationCode:$('recoveryCode').value.trim(),Password:$('recoveryPassword').value});
 $('email').value=$('recoveryEmail').value.trim();challenge='';challengeUsername='';token='';$('password').value='';$('signIn').textContent='Sign in';$('notice').textContent='Password updated. Sign in with your new password.';$('recoveryPassword').value='';$('recoveryCode').value='';$('recoveryDialog').close();
 }catch(error){$('recoveryStatus').textContent=error.message;}finally{$('confirmRecovery').disabled=false;}
};
let accountPage='',accountsBusy=false;
async function accountOperation(payload){
 if(accountsBusy)return;accountsBusy=true;$('accountsStatus').textContent='Updating account…';
 try{const result=await api('/admin/users',payload);await loadAccounts(false);$('accountsStatus').textContent=result.message;}
 catch(error){$('accountsStatus').textContent=error.message;}finally{accountsBusy=false;}
}
async function loadAccounts(append=false){
 const result=await api('/admin/users',{action:'list',...(append&&accountPage?{nextToken:accountPage}:{})});
 if(!append)$('accountsList').replaceChildren();
 accountPage=result.nextToken||'';$('moreAccounts').hidden=!accountPage;
 for(const account of result.users){
  const row=element('div','','account-row');const self=account.id===user.id;
  row.append(element('strong',account.name||account.email||account.username));
  row.append(element('p',account.email+' · '+(account.enabled?'Enabled':'Disabled')+' · '+account.status+(self?' · Your account':''),'account-meta'));
  const name=element('input','');name.value=account.name;name.maxLength=100;name.disabled=self;name.setAttribute('aria-label','Display name for '+account.email);row.append(name);
  const role=element('select','');role.setAttribute('aria-label','Role for '+account.email);
  for(const[value,label]of [['','Unassigned / mixed roles'],...workspaceDepartments.filter(x=>x.status==='ACTIVE').map(x=>[x.id,x.name+' team']),['admin','Administrator'],...workspaceDepartments.filter(x=>x.status!=='ACTIVE').map(x=>[x.id,x.name+' (inactive)'])]){const option=element('option',label);option.value=value;role.append(option);}
  role.value=account.roles.length===1?account.roles[0]:'';role.disabled=self;row.append(role);
  const actions=element('div','','actions');
  function button(label,action,extra={},confirmation=''){
   const b=element('button',label,action==='delete'?'secondary account-delete':'secondary');b.disabled=self;
   b.onclick=()=>{if(confirmation&&!confirm(confirmation))return;accountOperation({action,username:account.username,...(typeof extra==='function'?extra():extra)});};actions.append(b);
  }
  button('Save name','rename',()=>({name:name.value}));button('Assign role','role',()=>({role:role.value}),'Change this account’s role? The user will need to sign in again.');
  button(account.enabled?'Disable':'Enable',account.enabled?'disable':'enable',{},account.enabled?'Disable this account and block its access?':'Enable this account?');
  if(account.status!=='FORCE_CHANGE_PASSWORD')button('Send reset code','reset',{},'Send a password reset code to this account?');
  if(account.status==='FORCE_CHANGE_PASSWORD')button('Resend invitation','resend');
  button('Delete account','delete',{confirm:account.username},'Permanently delete '+account.email+'? This cannot be undone.');
  row.append(actions);$('accountsList').append(row);
 }
}
if(admin){
 $('documentsTab').onclick=()=>{$('documentPanel').hidden=false;$('accountPanel').hidden=true;};
 $('accountsTab').onclick=async()=>{$('documentPanel').hidden=true;$('accountPanel').hidden=false;try{await loadAccounts(false);}catch(error){$('accountsStatus').textContent=error.message;}};
 $('refreshAccounts').onclick=async()=>{try{await loadAccounts(false);$('accountsStatus').textContent='Accounts refreshed.';}catch(error){$('accountsStatus').textContent=error.message;}};
 $('moreAccounts').onclick=async()=>{try{await loadAccounts(true);}catch(error){$('accountsStatus').textContent=error.message;}};
 $('createAccountForm').onsubmit=async e=>{e.preventDefault();if(accountsBusy)return;accountsBusy=true;$('createAccount').disabled=true;
 try{const result=await api('/admin/users',{action:'create',name:$('accountName').value.trim(),email:$('accountEmail').value.trim(),role:$('accountRole').value});$('accountName').value='';$('accountEmail').value='';await loadAccounts(false);$('accountsStatus').textContent=result.message;}
 catch(error){$('accountsStatus').textContent=error.message;}finally{accountsBusy=false;$('createAccount').disabled=false;}
 };
}

let workspaceDepartments=[{id:'hr',name:'HR',status:'ACTIVE'},{id:'cloud',name:'Cloud',status:'ACTIVE'},{id:'genai',name:'GenAI',status:'ACTIVE'}];
let uploadDepartmentOptions=[{id:'hr',inputId:'uploadHr'},{id:'cloud',inputId:'uploadCloud'},{id:'genai',inputId:'uploadGenai'}];
function departmentRows(){
 $('departmentsList').replaceChildren();
 for(const department of workspaceDepartments){
  const row=element('div','','account-row');row.append(element('strong',department.name));row.append(element('p',department.id+' · '+department.status,'account-meta'));
  const name=element('input','');name.value=department.name;name.maxLength=80;name.setAttribute('aria-label','Name for '+department.id);row.append(name);
  const actions=element('div','','actions');
  function action(label,operation,extra={},confirmation=''){
   const button=element('button',label,'secondary');button.onclick=()=>{if(confirmation&&!confirm(confirmation))return;departmentOperation({action:operation,id:department.id,...(typeof extra==='function'?extra():extra)});};actions.append(button);
  }
  action('Save name','rename',()=>({name:name.value}));
  if(department.status!=='DELETING')action(department.status==='ACTIVE'?'Disable':'Enable',department.status==='ACTIVE'?'disable':'enable',{},'Change availability of this department?');
  if(!['hr','cloud','genai'].includes(department.id))action(department.status==='DELETING'?'Retry deletion':'Delete empty department','delete',{confirm:department.id},'Delete this empty department? Its ID cannot be reused.');
  row.append(actions);$('departmentsList').append(row);
 }
}
async function loadDepartments(){
 const response=await api('/admin/departments',{action:'list'});
 if(!Array.isArray(response.departments))throw Error('Department management backend needs deployment.');
 workspaceDepartments=response.departments;
 const selected=new Set(uploadDepartmentOptions.filter(x=>$(x.inputId).checked).map(x=>x.id));
 $('teamChoices').replaceChildren();uploadDepartmentOptions=[];
 for(const department of workspaceDepartments.filter(x=>x.status==='ACTIVE')){
  const inputId={hr:'uploadHr',cloud:'uploadCloud',genai:'uploadGenai'}[department.id]||'upload-'+department.id;
  const label=element('label','');const input=element('input','');input.type='checkbox';input.id=inputId;input.value=department.id;input.checked=selected.has(department.id);label.append(input,department.name+' team');$('teamChoices').append(label);uploadDepartmentOptions.push({id:department.id,inputId});
 }
 const previousRole=$('accountRole').value;$('accountRole').replaceChildren();
 for(const [value,label]of [['','Choose a role'],...workspaceDepartments.filter(x=>x.status==='ACTIVE').map(x=>[x.id,x.name+' team']),['admin','Administrator']]){const option=element('option',label);option.value=value;$('accountRole').append(option);}
 $('accountRole').value=[...workspaceDepartments.filter(x=>x.status==='ACTIVE').map(x=>x.id),'admin'].includes(previousRole)?previousRole:'';
 departmentRows();
}
let departmentBusy=false;
async function departmentOperation(payload){
 if(departmentBusy)return;departmentBusy=true;$('departmentsStatus').textContent='Updating department…';
 try{const result=await api('/admin/departments',payload);await loadDepartments();$('departmentsStatus').textContent=result.message;}
 catch(error){$('departmentsStatus').textContent=error.message;try{await loadDepartments();}catch{}}
 finally{departmentBusy=false;}
}
if(admin){
 $('departmentsTab').onclick=async()=>{$('documentPanel').hidden=true;$('accountPanel').hidden=true;$('departmentPanel').hidden=false;try{await loadDepartments();}catch(error){$('departmentsStatus').textContent=error.message;}};
 const showDocuments=$('documentsTab').onclick;$('documentsTab').onclick=()=>{$('departmentPanel').hidden=true;showDocuments();};
 const showAccounts=$('accountsTab').onclick;$('accountsTab').onclick=async()=>{$('departmentPanel').hidden=true;try{await loadDepartments();await showAccounts();}catch(error){$('accountsStatus').textContent=error.message;}};
 $('createDepartmentForm').onsubmit=async event=>{event.preventDefault();await departmentOperation({action:'create',id:$('departmentId').value.trim(),name:$('departmentName').value.trim()});};
}

if(admin){
 $('buildFallback').onclick=async()=>{$('buildFallback').disabled=true;try{const result=await api('/admin/fallback-index',{force:false});$('adminStatus').textContent=result.fallback.message;await loadDocuments();}catch(error){$('adminStatus').textContent=error.message;}finally{$('buildFallback').disabled=false;}};
 $('refreshDocuments').onclick=async()=>{try{await loadDocuments();$('adminStatus').textContent='Document indexing status refreshed.';}catch(error){$('adminStatus').textContent=error.message;}};
}
