/* Presentation layer only: preserves every original endpoint and underlying request handler. */
(() => {
'use strict';
const el=id=>document.getElementById(id);
const motion=window.RouterMotion||{suggestionStaggerMs:60,menuStaggerMs:30,successMs:1500};
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const ICONS={
 'plus':'<path d="M12 5v14M5 12h14"/>',
 'search':'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
 'settings':'<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"/><path d="M19 13a1.6 1.6 0 0 0 0-2l1.6-1.3-1.5-2.6-2 .5a1.6 1.6 0 0 0-1.7-1l-.3-2.1h-3l-.3 2.1a1.6 1.6 0 0 0-1.7 1l-2-.5-1.5 2.6L8.2 11a1.6 1.6 0 0 0 0 2l-1.6 1.3 1.5 2.6 2-.5a1.6 1.6 0 0 0 1.7 1l.3 2.1h3l.3-2.1a1.6 1.6 0 0 0 1.7-1l2 .5 1.5-2.6z"/>',
 'user-round':'<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/>',
 'panel-right-close':'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18m-4-5-3-4 3-4"/>',
 'ellipsis':'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 'pencil':'<path d="m16 5 3 3-12 12H4v-3z"/><path d="m14 7 3 3"/>',
 'trash-2':'<path d="M3 6h18M8 6V4h8v2M5 6l1 15h12l1-15M10 11v6M14 11v6"/>',
 'chevron-down':'<path d="m6 9 6 6 6-6"/>',
 'sliders-horizontal':'<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
 'list-checks':'<path d="m3 7 2 2 4-4M13 7h8m-18 9 2 2 4-4m4 2h8"/>',
 'x':'<path d="M18 6 6 18M6 6l12 12"/>',
 'paperclip':'<path d="m21 11.5-8.5 8.5a6 6 0 0 1-8.5-8.5l9.5-9.5a4 4 0 0 1 5.7 5.7l-9.5 9.5a2 2 0 0 1-2.8-2.8l8.5-8.5"/>',
 'mic':'<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5m-4 0h8"/>',
 'square':'<rect x="5" y="5" width="14" height="14" rx="2"/>',
 'arrow-up':'<path d="M12 19V5m-7 7 7-7 7 7"/>',
 'message-square-text':'<path d="M21 14a5 5 0 0 1-5 5H8l-5 3V8a5 5 0 0 1 5-5h8a5 5 0 0 1 5 5zM8 10h8m-8 4h5"/>',
 'code-2':'<path d="m8 8-4 4 4 4m8-8 4 4-4 4M14 4l-4 16"/>',
 'file-text':'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8m-8 4h8"/>',
 'languages':'<path d="m5 8 6 6M4 14l6-6M3 4h12M9 2v2M7 18h10m-8 4 5-12 5 12"/>',
 'book-open':'<path d="M12 7c-4-2-7-2-10-1v14c3-1 6-1 10 1 4-2 7-2 10-1V6c-3-1-6-1-10 1zm0 0v14"/>',
 'check':'<path d="m4 12 5 5L20 6"/>',
 'loader-circle':'<path d="M12 2a10 10 0 1 1-10 10"/>',
 'folder-open':'<path d="M3 6h7l2 2h9v12H3zM3 13h18"/>',
 'sparkles':'<path d="m12 3 2.1 6.9L21 12l-6.9 2.1L12 21l-2.1-6.9L3 12l6.9-2.1z"/>',
 'circle-alert':'<circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/>',
 'cloud':'<path d="M20 18H7a5 5 0 1 1 1-10 7 7 0 0 1 13 3 4 4 0 0 1-1 7"/>',
 'cpu':'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/>',
 'copy':'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
 'refresh-cw':'<path d="M20 7v5h-5M4 17v-5h5M5 9a8 8 0 0 1 14-2l1 5M4 12l1 5a8 8 0 0 0 14-2"/>',
 'info':'<circle cx="12" cy="12" r="10"/><path d="M12 11v5m0-9h.01"/>'
};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('class','icon');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','18');svg.setAttribute('height','18');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.75');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');svg.innerHTML=ICONS[name]||ICONS.info;return svg;}
function decorateIcons(root=document){root.querySelectorAll('[data-icon]').forEach(holder=>{if(holder.querySelector(':scope > .icon'))return;holder.prepend(icon(holder.dataset.icon));});}
function switchIcon(button,name){button.querySelector(':scope > .icon')?.remove();button.dataset.icon=name;button.prepend(icon(name));}
function friendlyText(v){return String(v||'').replace(/[\u{1F000}-\u{1FFFF}\u2600-\u27BF\uFE0F]/gu,'').replace(/\s{2,}/g,' ').trim();}
decorateIcons();
document.querySelector('.mark')?.append(icon('sparkles'));
// Preserve the original mark but express it as a vector using the same icon family.
el('new').classList.add('btn','btn-primary');
el('agentApprove').classList.add('btn','btn-primary');el('agentDiscard').classList.add('btn','btn-secondary');
let settingsReturnFocus=null,dialogReturnFocus=null;
let modalOpen=null;
const focusable=root=>Array.from(root.querySelectorAll('button:not([disabled]):not([hidden]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[href],[tabindex]:not([tabindex="-1"])')).filter(x=>x.offsetParent!==null);
function modalTrap(event,root){if(event.key==='Escape'){event.preventDefault();root===el('settingsModal')?closeSettings():closeDelete();return;}if(event.key!=='Tab')return;const list=focusable(root);if(!list.length)return;const first=list[0],last=list.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}
function showSettings(panel='settingsPanelModels'){settingsReturnFocus=document.activeElement;el('settingsModal').hidden=false;modalOpen='settings';selectSettingsPanel(panel);el('closeSettings').focus()}
function closeSettings(){el('settingsModal').hidden=true;modalOpen=null;(settingsReturnFocus||el('topSettings')).focus()}
function selectSettingsPanel(id){document.querySelectorAll('.settings-tab').forEach(tab=>{let selected=tab.dataset.panel===id;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1});document.querySelectorAll('.settings-panel').forEach(panel=>panel.hidden=panel.id!==id)}
['openSettings','topSettings'].forEach(id=>el(id).addEventListener('click',()=>showSettings()));el('closeSettings').onclick=closeSettings;
document.querySelectorAll('.settings-tab').forEach(tab=>tab.addEventListener('click',()=>selectSettingsPanel(tab.dataset.panel)));
el('settingsModal').addEventListener('keydown',e=>modalTrap(e,el('settingsModal')));
el('settingsModal').addEventListener('click',e=>{if(e.target===el('settingsModal'))closeSettings()});
document.querySelector('.settings-tabs').addEventListener('keydown',e=>{const tabs=Array.from(document.querySelectorAll('.settings-tab'));let index=tabs.findIndex(t=>t===document.activeElement);if(index<0)return;let delta=(e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0);if(delta){e.preventDefault();index=(index+delta+tabs.length)%tabs.length;selectSettingsPanel(tabs[index].dataset.panel);tabs[index].focus()}});

// Change only sidebar placement and behaviors; keep same chats array and persistence layer.
function blankChat(c){return !c||!Array.isArray(c.messages)||c.messages.length===0}
function ensureUniqueEmpty(){const keep=active()&&blankChat(active())?current:chats.find(x=>blankChat(x))?.id;chats=chats.filter(x=>!blankChat(x)||x.id===keep);if(!current||!chats.some(x=>x.id===current))current=chats[0]?.id||null}
ensureUniqueEmpty();
newChat=()=>{
  if(blankChat(active())){el('prompt').focus();return;}
  const existing=chats.find(x=>blankChat(x));
  if(existing){current=existing.id;render();el('prompt').focus();return;}
  current=randomId();chats.unshift({id:current,title:'محادثة جديدة',messages:[],createdAt:Date.now(),updatedAt:Date.now()});save();render();el('prompt').focus();
};
const firstMeaningfulTitle=msg=>String(msg||'').replace(/\s+/g,' ').replace(/^\[مرفق:.*?\]/,'').trim().slice(0,40)||'محادثة جديدة';
const baseSave=save;
// Existing save() is a top-level const and stays unchanged. Update timestamps at the UI boundaries.
function dateGroup(c){if(!c.createdAt&&!c.updatedAt)return blankChat(c)?'اليوم':'السابق';const t=+(c.createdAt||c.updatedAt),n=new Date(),start=new Date(n.getFullYear(),n.getMonth(),n.getDate()).getTime(),day=86400000;return t>=start?'اليوم':t>=start-day?'أمس':t>=start-7*day?'آخر 7 أيام':'السابق'}
let historyFilter='';
function enterRename(c){const item=el('history').querySelector(`[data-chat-id="${CSS.escape(c.id)}"]`);if(!item)return;const select=item.querySelector('.history-select');const input=document.createElement('input');input.className='inline-rename';input.value=c.title;input.maxLength=120;input.setAttribute('aria-label','اسم المحادثة الجديد');select.replaceWith(input);input.focus();input.select();let committed=false;function complete(ok){if(committed)return;committed=true;if(ok){const name=input.value.trim().slice(0,120);if(name){c.title=name;c.updatedAt=Date.now();save()}}render()}input.addEventListener('keydown',e=>{if(e.key==='Enter')complete(true);if(e.key==='Escape')complete(false)});input.addEventListener('blur',()=>complete(true),{once:true})}
function historyRow(c){const row=document.createElement('div');row.className='history-item'+(c.id===current?' active':'');row.dataset.chatId=c.id;const b=document.createElement('button');b.type='button';b.className='history-select';b.textContent=c.title||'محادثة';b.title=c.title||'محادثة';b.onclick=()=>{current=c.id;render();el('messages').scrollTop=el('messages').scrollHeight};const more=document.createElement('button');more.type='button';more.className='history-more';more.setAttribute('aria-label','خيارات محادثة '+c.title);more.title='خيارات المحادثة';more.append(icon('ellipsis'));more.addEventListener('click',e=>{e.stopPropagation();current=c.id;render();openChatMenu(more);});row.append(b,more);row.addEventListener('contextmenu',e=>{e.preventDefault();current=c.id;render();openChatMenu(more);});return row}
function renderHistory(){const container=el('history');container.replaceChildren();const order=['اليوم','أمس','آخر 7 أيام','السابق'];for(const group of order){const items=chats.filter(c=>dateGroup(c)===group && (c.title||'').toLowerCase().includes(historyFilter));if(!items.length)continue;const box=document.createElement('section');box.className='history-group';const h=document.createElement('h4');h.textContent=group;box.append(h);items.forEach(c=>box.append(historyRow(c)));container.append(box)}if(!container.children.length){const no=document.createElement('p');no.className='small history-empty';no.textContent='لا توجد محادثات مطابقة';container.append(no)}}
el('chatSearch').addEventListener('input',e=>{historyFilter=e.target.value.trim().toLowerCase();renderHistory()});
const prompts=[
 {icon:'code-2',title:'كتابة كود',description:'كود منظم ومناسب لمشروعك',prompt:'اكتب لي كودًا منظمًا وقابلًا للاختبار للمهمة التالية: '},
 {icon:'file-text',title:'تلخيص نص',description:'تلخيص واضح يحافظ على النقاط المهمة',prompt:'لخّص النص التالي مع الحفاظ على أبرز التفاصيل: '},
 {icon:'languages',title:'ترجمة',description:'ترجمة طبيعية ودقيقة',prompt:'ترجم النص التالي إلى الإنجليزية مع الحفاظ على المعنى: '},
 {icon:'book-open',title:'شرح مفهوم',description:'شرح تدريجي مع أمثلة عملية',prompt:'اشرح لي المفهوم التالي ببساطة مع مثال عملي: '},
];
function emptyState(){const w=document.createElement('div');w.className='welcome';const logo=document.createElement('span');logo.className='welcome-icon';const brand=document.createElement('img');brand.src='/brand/barq-mark-dark.png';brand.alt='';brand.width=62;brand.height=72;logo.append(brand);const title=document.createElement('h1');title.textContent='أقدر أساعدك في إيه؟';const p=document.createElement('p');p.textContent='اكتب سؤالك، وسيوجّه BARQ مهمتك إلى نموذج مناسب، مع إمكانية العمل محليًا عند انقطاع الإنترنت.';const grid=document.createElement('div');grid.className='suggestions';prompts.forEach((item,i)=>{const button=document.createElement('button');button.type='button';button.className='suggestion-card';button.style.animationDelay=reduced.matches?'0ms':i*motion.suggestionStaggerMs+'ms';button.append(icon(item.icon));const words=document.createElement('span');const strong=document.createElement('strong');strong.textContent=item.title;const small=document.createElement('small');small.textContent=item.description;words.append(strong,small);button.append(words);button.addEventListener('click',()=>{el('prompt').value=item.prompt;updateComposer();el('prompt').focus();el('prompt').setSelectionRange(item.prompt.length,item.prompt.length)});grid.append(button)});w.append(logo,title,p,grid);return w}
function messageCard(m){const d=document.createElement('article');d.className='bubble '+m.role;d.setAttribute('dir','auto');if(m.role==='assistant'){const head=document.createElement('div');head.className='bubble-head';const avatar=document.createElement('span');avatar.className='ai-avatar';const brand=document.createElement('img');brand.src='/brand/barq-mark-dark.png';brand.alt='';brand.width=22;brand.height=26;avatar.append(brand);const name=document.createElement('strong');name.className='ai-label';name.textContent='BARQ';head.append(avatar,name);d.append(head)}const body=document.createElement('div');body.className='bubble-body';body.dir='auto';body.textContent=String(m.content||'');d.append(body);if(m.role==='assistant'){if(m.incomplete){const warning=document.createElement('p');warning.className='meta';warning.textContent='الرد انقطع؛ حاول مجددًا.';d.append(warning)}
 const bar=document.createElement('div');bar.className='message-actions';
 const copy=document.createElement('button');copy.type='button';copy.className='btn btn-icon';copy.title='نسخ الإجابة';copy.setAttribute('aria-label','نسخ الإجابة');copy.append(icon('copy'));
 copy.addEventListener('click',async()=>{
   try{await navigator.clipboard.writeText(String(m.content||''));flashSuccess(copy,'نسخ الإجابة')}
   catch{copy.classList.add('is-error');setTimeout(()=>copy.classList.remove('is-error'),300)}
 });bar.append(copy);d.append(bar);
 }return d}
render=()=>{
 ensureUniqueEmpty();const c=active();renderHistory();el('chatTitle').textContent=c?.title||'محادثة جديدة';const target=el('content');const scroll=el('messages');const isNearBottom=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<90;
 target.replaceChildren();if(!c||blankChat(c))target.append(emptyState());else c.messages.forEach(m=>target.append(messageCard(m)));
 syncPlanCard();updateComposer();if(isNearBottom||!c?.messages?.length)requestAnimationFrame(()=>scroll.scrollTop=scroll.scrollHeight);
};
// Override only presentation of title and attach a small delete confirmation modal.
let menuOpen=false;
function openChatMenu(anchor=el('chatMore')){
 const menu=el('chatMenu');menu.style.cssText='';
 if(anchor!==el('chatMore')){const rect=anchor.getBoundingClientRect();menu.style.position='fixed';menu.style.top=Math.max(8,Math.min(innerHeight-110,rect.top))+'px';menu.style.left=Math.max(8,rect.left-215)+'px';}
 menu.hidden=false;menuOpen=true;el('chatMore').setAttribute('aria-expanded','true');el('renameChat').focus()
}
function closeChatMenu(){el('chatMenu').hidden=true;menuOpen=false;el('chatMore').setAttribute('aria-expanded','false')}
el('chatMore').addEventListener('click',()=>menuOpen?closeChatMenu():openChatMenu());
el('renameChat').onclick=()=>{const c=active();closeChatMenu();if(c)enterRename(c)};
el('chatTitle').onclick=()=>{const c=active();if(c)enterRename(c)};
let targetDelete=null;
function openDelete(){targetDelete=active();if(!targetDelete)return;dialogReturnFocus=document.activeElement;el('confirmMessage').textContent='هل تريد حذف المحادثة «'+targetDelete.title+'»؟ لا يمكن التراجع عن الحذف.';el('confirmModal').hidden=false;modalOpen='delete';closeChatMenu();el('cancelDelete').focus()}
function closeDelete(){el('confirmModal').hidden=true;targetDelete=null;modalOpen=null;(dialogReturnFocus||el('chatMore')).focus()}
el('deleteChat').onclick=openDelete;el('cancelDelete').onclick=closeDelete;
el('confirmDelete').onclick=()=>{if(!targetDelete||busy)return;const id=targetDelete.id;chats=chats.filter(c=>c.id!==id);current=chats[0]?.id||null;fetch('/v1/conversations/'+encodeURIComponent(id),{method:'DELETE'}).catch(()=>{});targetDelete=null;el('confirmModal').hidden=true;modalOpen=null;save();render();el('new').focus()};
el('confirmModal').addEventListener('keydown',e=>modalTrap(e,el('confirmModal')));
el('confirmModal').addEventListener('click',e=>{if(e.target===el('confirmModal'))closeDelete()});
document.addEventListener('pointerdown',e=>{if(menuOpen&&!e.target.closest('.chat-more-wrap'))closeChatMenu();if(modelOpen&&!e.target.closest('.model-select-wrap'))closeModel()});

// Approvals belong within the chat timeline, never the sidebar or settings.
let planInFlight=false;
window.addEventListener('router:plan',event=>{
 const steps=el('agentSteps');steps.replaceChildren();
 const data=event.detail||{};
 if(data.reason){const li=document.createElement('li');li.textContent=String(data.reason).slice(0,400);steps.append(li)}
 (Array.isArray(data.steps)?data.steps:[]).forEach(step=>{
   const li=document.createElement('li');
   li.textContent=String(step.description||step.tool||step.name||'خطوة تنفيذ').slice(0,200);
   steps.append(li);
 });
 syncPlanCard();
});
function syncPlanCard(){const card=el('agentPlanCard');if(!card)return;const show=!!pendingAgent||planInFlight||!el('agentEditReview').hidden;card.hidden=!show;el('agentApprove').disabled=planInFlight||!pendingAgent;el('agentDiscard').disabled=planInFlight||!pendingAgent;el('agentApprove').textContent=planInFlight?'جار التنفيذ...':'تشغيل الخطة';el('agentDiscard').textContent='إلغاء';}
const oldApprove=el('agentApprove').onclick;
el('agentApprove').onclick=async e=>{if(!pendingAgent)return;planInFlight=true;syncPlanCard();try{await oldApprove(e)}finally{planInFlight=false;syncPlanCard()}};
const oldDiscard=el('agentDiscard').onclick;
el('agentDiscard').onclick=e=>{oldDiscard(e);el('agentSteps').replaceChildren();syncPlanCard()};
const planObserver=new MutationObserver(()=>syncPlanCard());planObserver.observe(el('agentPlanOutput'),{childList:true,characterData:true,subtree:true});planObserver.observe(el('agentEditReview'),{attributes:true,attributeFilter:['hidden']});

// Custom searchable model selector. The existing #model select remains the canonical value.
let modelOpen=false,modelIndex=-1,providerData=[],modelData=[];
const modelTrigger=el('modelTrigger'),modelPopover=el('modelPopover'),modelOptions=el('modelOptions'),modelSearch=el('modelSearch');
function closeModel(){modelOpen=false;modelPopover.hidden=true;modelTrigger.setAttribute('aria-expanded','false');modelIndex=-1}
function openModel(){modelOpen=true;modelPopover.hidden=false;modelTrigger.setAttribute('aria-expanded','true');modelSearch.value='';paintModels();modelSearch.focus()}
function setModel(id){el('model').value=id;el('model').dispatchEvent(new Event('change',{bubbles:true}));modelTrigger.querySelector('#modelTriggerLabel').textContent=id==='auto'?'Auto — أفضل نموذج مجاني':id;closeModel();modelTrigger.focus()}
function paintModels(){modelOptions.replaceChildren();let q=modelSearch.value.trim().toLowerCase();const makeOpt=(id,title,tag)=>{const b=document.createElement('button');b.type='button';b.className='model-option';b.setAttribute('role','option');b.dataset.value=id;b.setAttribute('aria-selected',String(el('model').value===id));b.tabIndex=-1;b.append(icon(id==='auto'?'sparkles':id.startsWith('ollama/')?'cpu':'cloud'));const name=document.createElement('span');name.className='model-option-label';name.textContent=title;b.append(name);if(tag){const label=document.createElement('span');label.className='model-tag';label.textContent=tag;b.append(label)}b.addEventListener('click',()=>setModel(id));return b};if(!q||'auto أفضل نموذج مجاني'.includes(q))modelOptions.append(makeOpt('auto','Auto — أفضل نموذج مجاني','ذكي'));
 const byProvider=new Map();Array.from(el('model').options).filter(o=>o.value!=='auto').forEach(o=>{const id=o.value;if(!id.toLowerCase().includes(q))return;const provider=id.split('/')[0]||'أخرى';if(!byProvider.has(provider))byProvider.set(provider,[]);byProvider.get(provider).push(id)});
 for(const [provider,models] of byProvider){const label=document.createElement('div');label.className='model-group';label.textContent=provider;modelOptions.append(label);for(const id of models){const entry=modelData.find(m=>m.id===id);const tag=entry?.strengths?.includes('code')?'برمجة':entry?.strengths?.includes('fast')?'سريع':'متاح';modelOptions.append(makeOpt(id,id.split('/').slice(1).join('/')||id,tag))}}
 Array.from(modelOptions.querySelectorAll('.model-option')).forEach((x,i)=>{x.style.animationDelay=reduced.matches?'0ms':i*motion.menuStaggerMs+'ms'});
 modelIndex=-1;
}
modelTrigger.addEventListener('click',()=>modelOpen?closeModel():openModel());modelSearch.addEventListener('input',paintModels);
function navModels(e){if(e.key==='Escape'){e.preventDefault();closeModel();modelTrigger.focus();return}if(e.key==='Tab'){closeModel();return}if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();let options=Array.from(modelOptions.querySelectorAll('.model-option'));if(!options.length)return;modelIndex=(modelIndex+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;options.forEach((o,i)=>o.classList.toggle('is-focused',i===modelIndex));options[modelIndex].scrollIntoView({block:'nearest'});return}if(e.key==='Enter'){e.preventDefault();let options=modelOptions.querySelectorAll('.model-option');if(options.length)options[Math.max(0,modelIndex)]?.click()}}
modelPopover.addEventListener('keydown',navModels);modelTrigger.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){e.preventDefault();openModel()}});
const legacyLoadModels=loadModels;
loadModels=async()=>{await legacyLoadModels();paintModels();modelTrigger.querySelector('#modelTriggerLabel').textContent=el('model').value==='auto'?'Auto — أفضل نموذج مجاني':el('model').value};
new MutationObserver(()=>{if(modelOpen)paintModels();modelTrigger.querySelector('#modelTriggerLabel').textContent=el('model').value==='auto'?'Auto — أفضل نموذج مجاني':el('model').value}).observe(el('model'),{childList:true});
async function updateQuota(){try{const [p,m]=await Promise.all([fetch('/v1/router/providers'),fetch('/v1/router/models')]);if(!p.ok)throw Error('status');providerData=(await p.json()).providers||[];if(m.ok)modelData=(await m.json()).models||[];let ready=providerData.filter(x=>x.enabled&&x.configured),exhausted=ready.filter(x=>Number(x.remaining_today)===0);let state=!ready.length?'error':exhausted.length===ready.length?'error':exhausted.length?'warning':'success';el('quotaDot').dataset.state=state;const cloudReady=ready.filter(x=>x.kind!=='local');const sums=cloudReady.map(x=>Number(x.remaining_today)).filter(Number.isFinite);el('quotaText').textContent=sums.length?'سحابي '+sums.reduce((a,b)=>a+b,0):ready.length+' مزودين';el('quotaTooltip').textContent=providerData.map(x=>x.name+' — '+(!x.enabled?'معطل':!x.configured?'غير مهيأ':Number(x.remaining_today)===0?'نفدت الحصة':'متاح')+(x.configured&&x.enabled?' · '+x.remaining_today+' متبقٍ':'')).join('\n');el('quotaButton').title=el('quotaTooltip').textContent;}
catch{el('quotaDot').dataset.state='warning';el('quotaText').textContent='غير معروف';el('quotaTooltip').textContent='تعذر جلب بيانات المزودين'}}
el('quotaButton').addEventListener('mouseenter',()=>el('quotaTooltip').hidden=false);el('quotaButton').addEventListener('mouseleave',()=>el('quotaTooltip').hidden=true);el('quotaButton').addEventListener('focus',()=>el('quotaTooltip').hidden=false);el('quotaButton').addEventListener('blur',()=>el('quotaTooltip').hidden=true);
updateQuota();setInterval(updateQuota,60000);

// Preserve microphone actions, mirror only their visual state.
const mic=el('mic');function updateMicVisual(){switchIcon(mic,mic.classList.contains('recording')?'square':'mic');mic.setAttribute('aria-label',mic.classList.contains('recording')?'إنهاء تسجيل الرسالة الصوتية':'تسجيل رسالة صوتية');mic.title=mic.getAttribute('aria-label')}
const micObserver=new MutationObserver(()=>updateMicVisual());micObserver.observe(mic,{attributes:true,attributeFilter:['class']});
const originalMicClick=mic.onclick;mic.onclick=async e=>{if(originalMicClick)await originalMicClick(e);requestAnimationFrame(updateMicVisual)};
const composer=el('prompt'),sendButton=el('send');
function updateComposer(){const canSend=!!composer.value.trim()||attachedTexts.length>0;sendButton.disabled=!canSend&&!busy;sendButton.setAttribute('aria-label',busy?'إيقاف التوليد':'إرسال الرسالة');switchIcon(sendButton,busy?'square':'arrow-up');composer.style.height='auto';composer.style.height=Math.min(180,Math.max(50,composer.scrollHeight))+'px'}
composer.addEventListener('input',updateComposer);el('attachFiles').addEventListener('change',()=>requestAnimationFrame(updateComposer));
// Modify the pre-existing submit handler only via its shared runtime state; never simulate a successful stop.
sendButton.addEventListener('click',e=>{if(busy){e.preventDefault();if(typeof routerRequestController!=='undefined'&&routerRequestController)routerRequestController.abort()}});
// Route status is real only when data exists; while waiting show an honest generic routing state.
const status=el('status');let previousStatus=status.textContent;
new MutationObserver(()=>{const txt=status.textContent||'';const original=friendlyText(txt);if(txt!==original)status.textContent=original;const dot=status.closest('.status-pill')?.querySelector('.status-dot');if(dot)dot.style.background=/تعذر|فشل|خطأ/.test(original)?'var(--danger)':/جاري|توجيه|اختيار|انتظار/.test(original)?'var(--warning)':'var(--success)';}).observe(status,{childList:true,characterData:true,subtree:true});

// Sidebar responsive drawer and collapsed icon rail.
let isCollapsed=false;
function toggleSidebar(){const sidebar=document.querySelector('.sidebar');if(matchMedia('(max-width:800px)').matches){const open=!sidebar.classList.contains('mobile-open');sidebar.classList.toggle('mobile-open',open);el('sidebarBackdrop').hidden=!open;el('sidebarToggle').setAttribute('aria-expanded',String(open))}else{isCollapsed=!isCollapsed;sidebar.classList.toggle('is-collapsed',isCollapsed);try{localStorage.setItem('router-sidebar-collapsed',String(isCollapsed))}catch{}}}
el('sidebarToggle').onclick=toggleSidebar;el('sidebarBackdrop').onclick=()=>{document.querySelector('.sidebar').classList.remove('mobile-open');el('sidebarBackdrop').hidden=true};
try{isCollapsed=localStorage.getItem('router-sidebar-collapsed')==='true';document.querySelector('.sidebar').classList.toggle('is-collapsed',isCollapsed)}catch{}
window.addEventListener('resize',()=>{if(!matchMedia('(max-width:800px)').matches){document.querySelector('.sidebar').classList.remove('mobile-open');el('sidebarBackdrop').hidden=true}});

// Shortcut and focus hygiene across browser/desktop app.
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!el('settingsModal').hidden)closeSettings();el('chatSearch').focus();return;}if(e.key==='Escape'&&!modalOpen){if(modelOpen){closeModel();modelTrigger.focus()}else if(menuOpen){closeChatMenu();el('chatMore').focus()}else if(document.querySelector('.sidebar.mobile-open'))el('sidebarBackdrop').click();}});
// Strip decorative pictographs from chrome controls as they are progressively updated by legacy handlers.
function cleanChrome(root){const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let textNode;const nodes=[];while(textNode=walker.nextNode())nodes.push(textNode);for(const n of nodes){if(n.parentElement?.closest('.bubble-body'))continue;const t=friendlyText(n.nodeValue);if(t!==n.nodeValue&&/[\u{1F000}-\u{1FFFF}\u2600-\u27BF\uFE0F]/u.test(n.nodeValue))n.nodeValue=t}}
// Keep user-generated content untouched. Avoid observing our own render-heavy message area.
for(const area of document.querySelectorAll('.settings-body,.voice-controls,#selectedFiles,.sidefoot,#agentPlanCard')){cleanChrome(area);new MutationObserver(()=>cleanChrome(area)).observe(area,{childList:true,characterData:true,subtree:true})}
// Swap static microphone's original text without changing event listeners.
mic.textContent='';updateMicVisual();
el('new').onclick=newChat;
function flashSuccess(button,label){
 if(!button)return;
 const existing=button.dataset.restoringText;
 if(existing!==undefined)return;
 button.dataset.restoringText=button.dataset.savedLabel!==undefined?button.dataset.savedLabel:button.textContent;
 button.classList.remove('is-loading');button.classList.add('is-success');
 button.setAttribute('aria-label',label+' — تم بنجاح');
 button.replaceChildren(icon('check'));
 setTimeout(()=>{button.classList.remove('is-success');if(button.dataset.restoringText!==undefined){
  const original=button.dataset.restoringText;button.textContent=original;
  if(button.classList.contains('btn-icon'))button.replaceChildren(icon('copy'));
  delete button.dataset.restoringText;delete button.dataset.savedLabel;button.setAttribute('aria-label',label)
 }},motion.successMs);
}
function addLoading(id){
 const button=el(id),original=button?.onclick;if(!original)return;
 const label=button.textContent;button.dataset.savedLabel=label;
 button.onclick=async e=>{
   if(button.classList.contains('is-loading'))return;
   const width=button.getBoundingClientRect().width;button.style.minWidth=width+'px';button.classList.add('is-loading');button.setAttribute('aria-busy','true');
   button.replaceChildren(icon('loader-circle'));
   try{await original.call(button,e)}finally{
     button.classList.remove('is-loading');button.removeAttribute('aria-busy');
     if(!button.classList.contains('is-success'))button.textContent=label;
   }
 };
}
['saveApiKey','applyEdit','agentSaveEdit'].forEach(addLoading);
window.addEventListener('router:saved',event=>flashSuccess(el(event.detail.button),event.detail.button==='applyEdit'?'حفظ الملف':event.detail.button==='saveApiKey'?'حفظ المفتاح':'حفظ التعديل'));
// Measured speed, not fabricated token counts; refresh only on user request.
const perfButton=el('refreshPerformance');
if(perfButton)perfButton.addEventListener('click',async()=>{
  const panel=el('performanceData');perfButton.disabled=true;panel.textContent='جاري قراءة القياسات...';
  try{
    const response=await fetch('/v1/performance',{cache:'no-store'});
    if(!response.ok)throw Error('HTTP '+response.status);
    const perf=await response.json();
    const fmt=n=>typeof n==='number'?n.toFixed(2)+' ث':'—';
    panel.textContent='الردود المقاسة: '+perf.measured_responses+
      ' | بداية الرد (الوسيط): '+fmt(perf.ttft_seconds?.median)+
      ' | 95%: '+fmt(perf.ttft_seconds?.p95)+
      ' | تحويلات المزود: '+perf.fallback_responses;
  }catch(e){panel.textContent='لم تتوفر قياسات: '+String(e.message||e)}
  finally{perfButton.disabled=false}
});
// Existing startup may have created a blank chat; now render the polished view without duplicating it.
render();updateComposer();
})();
