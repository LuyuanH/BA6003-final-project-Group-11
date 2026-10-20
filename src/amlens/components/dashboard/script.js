// Use the dashboard color palette.
const P = {BG:'#F7F2EB',TXT:'#081F5C',DATA:'#334EAC',DATA2:'#7096D1',PALE:'#BAD6EB',LIGHT:'#D0E3FF',MUT:'rgba(8,31,92,.72)',GRID:'rgba(8,31,92,.16)',DK:['#EDEFF1','#D5DBE2','#BCC7D7','#9EB3CD','#809EC6','#6C93C7','#4D82C6','#3472C2']};
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => Number(n).toLocaleString('en-US');
const money = n => String(n).split('.')[0].replace(/\B(?=(\d{3})+(?!\d))/g,',')+'.'+(String(n).split('.')[1]||'').padEnd(2,'0');
const caseId = id => 'C-'+String(id+1).padStart(4,'0');
const key = (bank,account) => Number(bank)+':'+account;
const rnd = (i,k) => Math.abs(((i*73856093)^(k*19349663))%1000)/1000;
const NS='http://www.w3.org/2000/svg';
function svgEl(p,t,a){const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);p.appendChild(n);return n;}

export default function({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('.amlens');
  const get = name => root.querySelector(`[data-role="${name}"]`);
  const text = (name,v) => {get(name).textContent=v;};
  const state=data.state, detail=data.detail;
  const L=createLocale(state.language),t=L.t, pattern=L.pattern,entity=L.entity,currency=L.currency;
  const statusName=s=>t(s), summary=c=>t('summary',{accounts:num(c.nodes.length),tx:num(c.transactions.length)});
  root.lang=L.zh?'zh-CN':'en';
  root.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
  root.querySelector('[data-i18n="workspace"]').textContent=L.zh?'历史检测结果回放':'Historical detection replay';
  root.querySelector('[data-i18n="waitHint"]').textContent=L.zh?'开始回放，等待检测批次完成':'Start replay and wait for a detection batch';
  for(const [key,attr] of [['aria','aria-label'],['title','title'],['placeholder','placeholder']])root.querySelectorAll(`[data-${key}]`).forEach(el=>el.setAttribute(attr,t(el.dataset[key])));
  root.querySelectorAll('[data-action="language"]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.value===L.lang)));
  const local=root._local ||= {account:null,tx:null,tab:'transactions',search:'',...state.ui,graphs:{}};
  cancelAnimationFrame(local.disposeFrame);
  if(local.caseId!==detail?.id || local.evidenceId!==detail?.evidenceId){local.account=null;local.tx=null;local.caseId=detail?.id;local.evidenceId=detail?.evidenceId;local.tab='transactions';}
  if(local.revision!==state.revision){local.pending=false;local.revision=state.revision;get('connection-message').hidden=true;}
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let timer,deadline,commandTimer,alive=true;
  local.commands ||= [];
  function send(action,value,evidenceId=detail?.evidenceId){
    if(local.pending){
      if(action!=='tick')local.commands.push({action,value,evidenceId});
      return;
    }
    local.pending=true;
    clearTimeout(deadline);
    const sentRevision=local.revision;
    deadline=setTimeout(()=>{if(local.revision===sentRevision){local.pending=false;get('connection-message').hidden=false;}},8000);
    setTriggerValue('action',{id:crypto.randomUUID(),action,value,evidenceId,ui:{caseId:local.caseId,account:local.account,tx:local.tx,tab:local.tab,search:local.search}});
  }
  function updateHTML(el,html){if(el.innerHTML!==html)el.innerHTML=html;}
  const inDetail=state.view==='detail' && Boolean(detail);
  root.classList.toggle('detail-mode',inDetail);
  if(local.view!==inDetail){local.view=inDetail;requestAnimationFrame(()=>{if(root.isConnected)root.scrollIntoView({block:'start',behavior:'instant'});});}
  get('overview').hidden=inDetail;get('investigation').hidden=!inDetail;
  root.querySelector('.nav[data-action="overview"]').classList.toggle('active',!inDetail);
  get('nav-investigate').classList.toggle('active',inDetail);
  root.querySelector('.workspace-head').hidden=inDetail;
  root.querySelector('.metrics').hidden=inDetail;
  text('processed',num(data.processed));text('hold',num(data.hold));text('pending',num(data.pending));
  text('nav-count',num(data.pending+data.investigating));
  text('clock',L.time(data.date));text('day',L.date(data.date));
  text('processed-note',t('since',{date:L.shortStamp(data.startDate+' 00:00')}));
  text('case-note',t('caseNote',{active:num(data.investigating),done:num(data.reviewed)}));
  text('play-state',t(state.playing?'playing':state.cursor>=data.rangeEnd?'ended':data.processed?'paused':'ready'));
  text('play',t(state.playing?'playing':state.cursor>=data.rangeEnd?'ended':'start'));
  get('play').disabled=state.playing||state.cursor>=data.rangeEnd;
  get('start-date').disabled=true;get('seek').disabled=true;
  root.querySelectorAll('[data-action="reset"],[data-action="next"]').forEach(el=>el.disabled=true);
  updateHTML(get('start-date'),data.dates.map(d=>`<option value="${d}">${L.date(d)}</option>`).join(''));
  get('start-date').value=data.startDate;get('speed').value=String(state.speed);
  const seek=get('seek');seek.min=state.start-1;seek.max=data.rangeEnd;seek.value=Math.floor(state.cursor);seek.setAttribute('aria-valuetext',L.stamp(data.date));
  text('footer-time',L.stamp(data.date));
  text('trend-start',L.shortStamp(data.startDate+' 00:00'));text('trend-end',L.shortStamp(data.date));
  const visibleQueue=()=>data.queue.filter(q=>(!state.pattern||q.pattern===state.pattern) &&
      `${caseId(q.id)} ${q.pattern} ${pattern(q.pattern)} ${entity(q.search||q.lead.account+' '+q.lead.entity)}`.toLowerCase().includes(local.search.toLowerCase()));
  function renderQueue(){
    const qs=visibleQueue();text('queue-count',String(qs.length));
    get('queue-empty').hidden=qs.length>0;
    text('queue-empty',t(data.queue.length?'noMatch':'noCases'));
    updateHTML(get('queue'),qs.map(q=>`<tr tabindex="0" data-case="${q.id}" aria-label="${esc(t('investigateCase',{id:caseId(q.id),pattern:pattern(q.pattern)}))}" class="${q.id===detail?.id?'selected':''}"><td><strong>${caseId(q.id)}</strong><small>${esc(pattern(q.pattern))}</small></td><td><strong>${esc(entity(q.lead.entity))}</strong><small>${esc(q.lead.account)} · ${t('accountsCount',{n:num(q.accounts)})}</small></td><td class="numeric">${q.count}</td><td>${L.shortDate(q.end)}<small>${L.time(q.end)}</small></td><td><span class="badge ${q.status}">${statusName(q.status)}</span></td><td>↗</td></tr>`).join(''));
  }
  renderQueue();get('queue-search').value=local.search;
  // Draw one tick per unit, a dot at every fifth unit, and the total count.
  const max=Math.max(1,...data.patterns.map(p=>p.count));
  const unit=max<=40?1:max<=200?5:max<=400?10:20;
  get('patterns').replaceChildren();
  data.patterns.forEach((p,i)=>{
    const selected=state.pattern===p.id;
    const button=document.createElement('button');button.className='pattern-row'+(selected?' selected':'');
    button.dataset.pattern=p.id;button.setAttribute('aria-label',t('patternAria',{pattern:pattern(p.id),count:num(p.count)}));button.setAttribute('aria-pressed',String(selected));
    if(p.enabled===false)button.setAttribute('aria-label',pattern(p.id)+(L.zh?'，规则未启用':', rule not enabled'));
    button.title=p.enabled===false?(L.zh?'规则未启用':'Rule not enabled'):t('patternHint',{pattern:pattern(p.id),cases:num(p.cases),unit});
    button.innerHTML=`<span><strong>${esc(pattern(p.id))}</strong></span><svg class="ticks" viewBox="0 0 140 24" aria-hidden="true"></svg><span class="value">${p.enabled===false?'—':p.count}</span>`;
    get('patterns').appendChild(button);
    const s=button.querySelector('svg'), count=p.count/unit, step=3.4;
    svgEl(s,'line',{x1:0,y1:17,x2:136,y2:17,stroke:selected?P.DATA2:P.GRID,'stroke-width':1});
    const shade=selected?P.BG:p.count>max*.66?P.TXT:p.count>max*.33?P.DATA:P.DATA2;
    for(let k=0;k<Math.ceil(count);k++){
      const h=(9+rnd(k+1,i+2)*6)*Math.min(1,count-k),x=k*step+step/2;
      svgEl(s,'line',{x1:x,y1:17,x2:x,y2:17-h,stroke:shade,'stroke-width':1.6,opacity:1});
      if(k%5===4)svgEl(s,'circle',{cx:x,cy:21,r:.85,fill:selected?P.PALE:P.DATA2});
    }
  });
  const activePattern=data.patterns.find(p=>p.id===state.pattern);
  text('clear-pattern',t(activePattern?'clearFilter':'all'));
  function graph(role,c){
    const el=get(role);if(!el.clientWidth)return;
    const projection=role==='detail-network';
    let g=local.graphs[role];if(!g||g.isDisposed())g=local.graphs[role]=window.echarts.init(el,null,{renderer:'svg'});
    g.resize();g.off('click');
    const signature=c?`${c.id}:${c.evidenceId}:${c.transactions.length}`:'empty';
    if(el.dataset.signature!==signature){
      el.dataset.signature=signature;g.clear();
      if(c){
        const degree={};c.nodes.forEach(n=>degree[n.key]=0);
        c.transactions.forEach(t=>{const a=key(t.fromBank,t.from),b=key(t.toBank,t.to);degree[a]++;if(a!==b)degree[b]++;});
        const ordered=[...c.nodes].sort((a,b)=>degree[b.key]-degree[a.key]);
        // Draw accounts and directed transactions. Set node area in proportion to node degree.
        g.setOption({animationDuration:reduced?0:900,animationEasing:'quarticOut',
          series:[{type:'graph',layout:'force',force:{initLayout:'circular',repulsion:Math.min(430,80+1900/c.nodes.length)*(projection?.55:1),edgeLength:projection?[55,100]:[65,120],gravity:.1,friction:.3,layoutAnimation:!reduced},
            roam:true,draggable:true,zoom:projection?1:el.clientHeight<210?.6:.75,left:projection?55:40,right:projection?150:75,top:projection?55:35,bottom:projection?55:30,
            labelLayout:{hideOverlap:true},
            data:ordered.map((n,i)=>({...n,id:n.key,name:n.key,value:degree[n.key],
              symbolSize:(projection?14:11)*Math.sqrt(degree[n.key]),itemStyle:{color:degree[n.key]>=5?P.DK[0]:degree[n.key]>=2?P.DK[2]:P.DK[4],borderWidth:0},
              label:{show:ordered.length<=12||i<4,formatter:n.account,position:'right',distance:8,color:P.DK[1],fontFamily:'Inter, sans-serif',fontSize:13,fontWeight:600}})),
            links:c.transactions.map(t=>({source:key(t.fromBank,t.from),target:key(t.toBank,t.to),raw:t,id:String(t.id),symbol:['none','arrow'],symbolSize:[0,projection?8:6],
              lineStyle:{width:1.8,color:P.DATA2,opacity:.85,curveness:.12}})),
            emphasis:{focus:'adjacency',lineStyle:{color:P.DK[0],opacity:1,width:2.4},label:{show:true,color:P.DK[0]}},
            blur:{itemStyle:{opacity:.28},lineStyle:{opacity:.15}}}]
        });
      }
    }
    // Update tooltip translations. Keep the current graph layout.
    if(c)g.setOption({tooltip:{backgroundColor:P.BG,borderWidth:0,confine:true,textStyle:{color:P.TXT,fontFamily:'Inter, sans-serif',fontSize:15,lineHeight:22},padding:[12,16],extraCssText:'box-shadow:none;border-radius:12px;max-width:440px;white-space:normal;overflow-wrap:anywhere',
      formatter:p=>p.dataType==='node'?`${esc(entity(p.data.entity))}<br/>${esc(p.data.account)}<br/>${esc(p.data.bank)}<br/>${t('relatedCount',{n:num(p.value)})}`:
      `${esc(p.data.raw.from)} → ${esc(p.data.raw.to)}<br/>${money(p.data.raw.paid)} ${esc(currency(p.data.raw.paymentCurrency))}<br/>${L.stamp(p.data.raw.timestamp)}`}});
    g.on('click',p=>{
      if(!inDetail){if(c)send('open',c.id);return;}
      if(p.dataType==='node'){local.account=p.data.key;local.tx=null;}
      else if(p.dataType==='edge'){local.tx=p.data.raw.id;local.account=null;}
      local.tab='transactions';renderDetail();highlight();
    });
  }
  function highlight(){
    const g=local.graphs['detail-network'];if(!g)return;
    g.dispatchAction({type:'downplay'});
    if(local.account)g.dispatchAction({type:'highlight',seriesIndex:0,name:local.account});
    if(local.tx!==null&&detail)g.dispatchAction({type:'highlight',seriesIndex:0,dataType:'edge',dataIndex:detail.transactions.findIndex(t=>t.id===local.tx)});
  }
  function accountMarkup(n){return `<strong title="${esc(entity(n?.entity))}">${esc(entity(n?.entity))}</strong><small title="${esc(n?.account)} · ${esc(n?.bank)}">${esc(n?.account)} · ${esc(n?.bank)}</small>`;}
  function renderDetail(){
    if(!detail)return;
    const account=detail.nodes.find(n=>n.key===local.account),nodes=Object.fromEntries(detail.nodes.map(n=>[n.key,n]));
    text('case-title',`${caseId(detail.id)} · ${pattern(detail.pattern)}`);text('case-status',statusName(detail.status));get('case-status').className='badge '+detail.status;
    get('reopen').hidden=detail.status!=='reviewed';
    root.querySelector('[data-action="status"][data-value="investigating"]').hidden=detail.status!=='pending';
    root.querySelector('[data-action="status"][data-value="reviewed"]').hidden=detail.status==='reviewed';
    text('detail-summary',summary(detail));text('account-title',t(account?'accountProfile':'caseProfile'));
    const stats=account?`<div class="profile-top"><strong>${esc(account.account)}</strong><p>${esc(entity(account.entity))}</p></div><dl class="profile-list"><dt>${t('entityId')}</dt><dd>${esc(account.entityId)}</dd><dt>${t('bank')}</dt><dd>${esc(account.bank)}</dd><dt>${t('bankId')}</dt><dd>${esc(account.bankId)}</dd><dt>${t('relatedTx')}</dt><dd>${t('txCount',{n:detail.transactions.filter(v=>key(v.fromBank,v.from)===account.key||key(v.toBank,v.to)===account.key).length})}</dd></dl>`:
      `<div class="profile-top"><strong>${esc(pattern(detail.pattern))}</strong></div><dl class="profile-list"><dt>${t('started')}</dt><dd>${L.stamp(detail.start)}</dd><dt>${t('queued')}</dt><dd>${L.stamp(detail.end)}</dd><dt>${t('involved')}</dt><dd>${t('accountEntityCount',{accounts:detail.nodes.length,entities:new Set(detail.nodes.map(n=>n.entityId)).size})}</dd></dl>`;
    get('account-info').innerHTML=stats+`<div class="amount-list"><p>${t('amounts')}</p>${detail.amounts.map(a=>`<div class="amount-line"><span>${esc(currency(a.currency))}</span><strong>${money(a.amount)}</strong></div>`).join('')}</div>`;
    const txs=detail.transactions.filter(v=>!local.account || key(v.fromBank,v.from)===local.account || key(v.toBank,v.to)===local.account);
    text('tx-count',txs.length);text('account-count',detail.nodes.length);
    text('clear-evidence',t(local.account||local.tx!==null?'clearFocus':'allTx'));
    root.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===local.tab));
    if(local.tab==='accounts'){
      get('evidence').innerHTML=`<table><thead><tr><th style="width:18%">${t('account')}</th><th style="width:27%">${t('entity')}</th><th style="width:24%">${t('bank')}</th><th>${t('entityId')}</th><th class="numeric" style="width:12%">${t('relatedTx')}</th></tr></thead><tbody>${detail.nodes.map(n=>`<tr tabindex="0" data-account="${esc(n.key)}" aria-label="${esc(t('selectAccount',{account:n.account}))}"><td><strong>${esc(n.account)}</strong></td><td>${esc(entity(n.entity))}</td><td>${esc(n.bank)}</td><td>${esc(n.entityId)}</td><td class="numeric">${detail.transactions.filter(v=>key(v.fromBank,v.from)===n.key||key(v.toBank,v.to)===n.key).length}</td></tr>`).join('')}</tbody></table>`;
    }else{
      get('evidence').innerHTML=`<table><thead><tr><th style="width:12%">${t('txTime')}</th><th style="width:25%">${t('payer')}</th><th style="width:25%">${t('payee')}</th><th class="numeric" style="width:17%">${t('paid')}</th><th class="numeric" style="width:17%">${t('received')}</th><th style="width:4%"></th></tr></thead><tbody>${txs.map(v=>`<tr tabindex="0" data-tx="${v.id}" aria-label="${esc(t(local.tx===v.id?'collapse':'expand',{n:v.lines.join(', ')}))}" aria-expanded="${local.tx===v.id}" class="${local.tx===v.id?'selected':''}"><td class="date-cell">${L.shortDate(v.timestamp)}<small>${L.time(v.timestamp)}</small></td><td>${accountMarkup(nodes[key(v.fromBank,v.from)])}</td><td>${accountMarkup(nodes[key(v.toBank,v.to)])}</td><td class="numeric"><strong>${money(v.paid)}</strong><small>${esc(currency(v.paymentCurrency))}</small></td><td class="numeric"><strong>${money(v.received)}</strong><small>${esc(currency(v.receivingCurrency))}</small></td><td>${local.tx===v.id?'−':'+'}</td></tr>${local.tx===v.id?`<tr class="expanded"><td colspan="6"><div class="expanded-info"><div><span>${t('paymentFormat')}</span><strong>${esc(L.payment(v.format))}</strong></div><div><span>${t('sourceRows')}</span><strong>${v.lines.join(', ')}</strong></div><div><span>${t('payerId')}</span><strong>${esc(nodes[key(v.fromBank,v.from)].entityId)}</strong></div><div><span>${t('payeeId')}</span><strong>${esc(nodes[key(v.toBank,v.to)].entityId)}</strong></div></div></td></tr>`:''}`).join('')}</tbody></table>`;
    }
  }
  get('graph-empty').hidden=Boolean(detail);get('graph-open').disabled=!detail;
  get('nav-investigate').disabled=!detail;
  get('graph-context').innerHTML=detail?`<strong>${caseId(detail.id)}</strong>${esc(pattern(detail.pattern))}`:'';
  text('graph-summary',detail?summary(detail):t('accountsArrow'));
  if(inDetail){renderDetail();graph('detail-network',detail);highlight();}
  else{
    graph('network',detail);
    let trend=local.graphs.trend;
    if(!trend||trend.isDisposed())trend=local.graphs.trend=window.echarts.init(get('trend'),null,{renderer:'svg'});
    trend.resize();
    // Update the cumulative series and its total together.
    trend.setOption({animationDuration:reduced?0:900,animationDurationUpdate:reduced?0:350,animationEasing:'quarticOut',
      tooltip:{trigger:'axis',backgroundColor:P.BG,borderWidth:0,textStyle:{color:P.TXT,fontSize:15},extraCssText:'box-shadow:none',formatter:ps=>`${L.stamp(ps[0].value[0])}<br/>${t('txCount',{n:num(ps[0].value[1])})}`},
      grid:{left:50,right:8,top:16,bottom:8},xAxis:{type:'value',min:state.start,max:Math.max(state.start+1,Math.floor(state.cursor)),show:false},
      yAxis:{type:'value',min:0,splitNumber:3,axisLabel:{fontSize:13,color:P.MUT,formatter:L.axis},splitLine:{lineStyle:{color:P.GRID,type:'dashed'}},axisLine:{show:false},axisTick:{show:false}},
      series:[{type:'line',data:data.trend,smooth:false,symbol:'none',lineStyle:{color:P.TXT,width:2.6},areaStyle:{color:P.DATA2,opacity:.85}}]});
  }
  root.onclick=e=>{
    const action=e.target.closest('[data-action]');
    if(action){e.preventDefault();send(action.dataset.action,action.dataset.value);return;}
    const pat=e.target.closest('[data-pattern]');if(pat){send('pattern',state.pattern===pat.dataset.pattern?'':pat.dataset.pattern);return;}
    const row=e.target.closest('[data-case]');if(row){send('open',Number(row.dataset.case));return;}
    const tx=e.target.closest('[data-tx]');if(tx){local.tx=local.tx===Number(tx.dataset.tx)?null:Number(tx.dataset.tx);renderDetail();highlight();return;}
    const account=e.target.closest('[data-account]');if(account){local.account=account.dataset.account;local.tx=null;local.tab='transactions';renderDetail();highlight();return;}
    const tab=e.target.closest('[data-tab]');if(tab){local.tab=tab.dataset.tab;renderDetail();return;}
    const role=e.target.closest('[data-role]')?.dataset.role;
    if(['graph-open','nav-investigate'].includes(role)&&detail)send('open',detail.id);
    if(role==='clear-pattern')send('pattern','');
    if(['clear-account','clear-evidence'].includes(role)){local.account=null;local.tx=null;renderDetail();highlight();}
  };
  root.onchange=e=>{const r=e.target.dataset.role;if(r==='start-date')send('date',e.target.value);if(r==='speed')send('speed',Number(e.target.value));if(r==='seek')send('seek',Number(e.target.value));};
  root.oninput=e=>{if(e.target.dataset.role==='queue-search'){local.search=e.target.value;renderQueue();}};
  root.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('tr[tabindex]')){e.preventDefault();e.target.click();}};
  const resize=new ResizeObserver(()=>{if(alive)Object.entries(local.graphs).forEach(([role,g])=>{if(!g.isDisposed()&&g.getDom().clientWidth){g.resize();const el=g.getDom();if(role!=='trend' && el.dataset.fitHeight!==String(el.clientHeight) && g.getOption().series?.length){el.dataset.fitHeight=String(el.clientHeight);g.setOption({series:[{zoom:role==='detail-network'?1:el.clientHeight<210?.6:.75}]});}}});});resize.observe(root);
  if(local.commands.length && !local.pending)commandTimer=setTimeout(()=>{
    const next=local.commands.shift();send(next.action,next.value,next.evidenceId);
  },0);
  else if(state.playing)timer=setTimeout(()=>send('tick'),700);
  return ()=>{
    alive=false;clearTimeout(timer);clearTimeout(deadline);clearTimeout(commandTimer);resize.disconnect();root.onclick=null;root.onchange=null;root.oninput=null;root.onkeydown=null;
    Object.values(local.graphs).forEach(g=>g.off('click'));
    local.disposeFrame=requestAnimationFrame(()=>{if(!root.isConnected)Object.values(local.graphs).forEach(g=>g.dispose());});
  };
}
