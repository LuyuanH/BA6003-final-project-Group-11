// Translate display text. Keep source identifiers and stored records unchanged.
const COPY = {
  zh: {
    app:'AMLens 风险总览', home:'AMLens 首页', workspace:'风险工作台', navigation:'主导航', overview:'大盘', investigate:'调查', team:'风险管理', language:'界面语言', heading:'交易风险总览',
    startDate:'起始日期', reset:'重置回放', speed:'回放速度', next:'下一事件 ⇥', nextTitle:'跳到下一案例', seek:'回放进度', timeControls:'回放时间控制', metrics:'业务指标', processed:'已处理交易', hold:'待复核交易', pendingCases:'待复核案例', transactionsUnit:'笔', casesUnit:'个', holdNote:'待复核 · 调查中', since:'自 {date} 起', caseNote:'{active} 个调查中 · {done} 个已复核',
    playing:'回放中', ended:'已结束', paused:'已暂停', ready:'待开始', pause:'Ⅱ 暂停', resume:'▶ 继续回放', start:'▶ 开始回放',
    network:'资金关系', networkAria:'案例账户及交易关系', open:'调查 ↗', waitCase:'等待首个案例', waitHint:'开始回放，或跳到下一事件', legend:'圆点为账户 · 连线为交易', accountsArrow:'账户 → 账户', summary:'{accounts} 个账户 · {tx} 笔交易',
    patterns:'八种模式', pattern:'模式', all:'全部 ↗', clearFilter:'清除筛选 ×', patternAria:'{pattern}，待复核交易 {count} 笔', patternHint:'{pattern} · {cases} 个案例 · 每刻度 {unit} 笔',
    queue:'复核队列', search:'搜索案例或账户', searchPlaceholder:'搜索案例、实体、账户', casePattern:'案例 / 模式', accountEntity:'关联账户 / 实体', tx:'交易', queued:'入队时间', status:'状态', noMatch:'没有匹配的案例', noCases:'当前没有待复核案例', investigateCase:'调查 {id} {pattern}', accountsCount:'{n} 个账户',
    trend:'累计处理', trendAria:'截至当前时间累计处理交易趋势', operations:'风险运营', back:'← 返回大盘', startInvestigation:'开始调查', finishReview:'完成复核 ✓', reopen:'重新复核',
    paths:'交易路径', allAccounts:'查看全部 ↗', pathsAria:'可选择账户与交易的资金路径', pathHint:'点击账户或连线，定位交易证据', caseProfile:'案例概况', accountProfile:'账户详情',
    evidence:'交易证据', accounts:'关联账户', allTx:'全部交易 ↗', clearFocus:'清除定位 ×', entity:'所属实体', bank:'银行', bankId:'银行编号', entityId:'实体编号', relatedTx:'关联交易', txCount:'{n} 笔', relatedCount:'{n} 笔关联交易', started:'开始时间', involved:'涉及账户', accountEntityCount:'{accounts} 个账户 · {entities} 个实体', amounts:'案例付款金额',
    account:'账户', txTime:'交易时间', payer:'付款账户 / 实体', payee:'收款账户 / 实体', paid:'付款金额', received:'收款金额', paymentFormat:'交易方式', sourceRows:'交易流水行号', payerId:'付款实体编号', payeeId:'收款实体编号', expand:'展开交易 {n}', collapse:'收起交易 {n}', selectAccount:'查看账户 {account}', connection:'连接暂未响应，请稍后重试。',
    pending:'待复核', investigating:'调查中', reviewed:'已复核'
  },
  en: {
    app:'AMLens Risk Overview', home:'AMLens Home', workspace:'Risk workspace', navigation:'Main navigation', overview:'Overview', investigate:'Investigations', team:'Risk team', language:'Interface language', heading:'Transaction risk overview',
    startDate:'Start date', reset:'Reset replay', speed:'Replay speed', next:'Next event ⇥', nextTitle:'Skip to the next case', seek:'Replay progress', timeControls:'Replay time controls', metrics:'Business metrics', processed:'Transactions processed', hold:'Transactions on hold', pendingCases:'Cases pending review', transactionsUnit:'transactions', casesUnit:'cases', holdNote:'Pending review · Investigating', since:'Since {date}', caseNote:'{active} investigating · {done} reviewed',
    playing:'Playing', ended:'Finished', paused:'Paused', ready:'Ready', pause:'Ⅱ Pause', resume:'▶ Resume', start:'▶ Start replay',
    network:'Account network', networkAria:'Case accounts and transaction relationships', open:'Investigate ↗', waitCase:'Waiting for the first case', waitHint:'Start replay or skip to the next event', legend:'Nodes: accounts · Edges: transactions', accountsArrow:'Account → Account', summary:'{accounts} accounts · {tx} transactions',
    patterns:'Eight patterns', pattern:'Pattern', all:'All ↗', clearFilter:'Clear filter ×', patternAria:'{pattern}, {count} transactions on hold', patternHint:'{pattern} · {cases} cases · {unit} transactions per tick',
    queue:'Review queue', search:'Search cases or accounts', searchPlaceholder:'Search case, entity, account', casePattern:'Case / Pattern', accountEntity:'Account / Entity', tx:'Txns', queued:'Queued at', status:'Status', noMatch:'No matching cases', noCases:'No cases awaiting review', investigateCase:'Investigate {id} {pattern}', accountsCount:'{n} accounts',
    trend:'Cumulative processing', trendAria:'Cumulative transactions processed through the current time', operations:'Risk operations', back:'← Back to overview', startInvestigation:'Start investigation', finishReview:'Complete review ✓', reopen:'Reopen review',
    paths:'Transaction paths', allAccounts:'View all ↗', pathsAria:'Select accounts and transactions in the payment network', pathHint:'Select a node or edge to inspect evidence', caseProfile:'Case profile', accountProfile:'Account details',
    evidence:'Transaction evidence', accounts:'Related accounts', allTx:'All transactions ↗', clearFocus:'Clear selection ×', entity:'Entity', bank:'Bank', bankId:'Bank ID', entityId:'Entity ID', relatedTx:'Related txns', txCount:'{n} transactions', relatedCount:'{n} related transactions', started:'Started at', involved:'Scope', accountEntityCount:'{accounts} accounts · {entities} entities', amounts:'Case payment amounts',
    account:'Account', txTime:'Transaction time', payer:'Payer account / Entity', payee:'Payee account / Entity', paid:'Amount paid', received:'Amount received', paymentFormat:'Payment method', sourceRows:'Transaction row', payerId:'Payer entity ID', payeeId:'Payee entity ID', expand:'Expand transaction {n}', collapse:'Collapse transaction {n}', selectAccount:'View account {account}', connection:'Connection is not responding. Please try again shortly.',
    pending:'Pending', investigating:'Investigating', reviewed:'Reviewed'
  }
};
const PATTERNS={
  'FAN-IN':['集中收款','Fan-in'],'FAN-OUT':['分散付款','Fan-out'],'CYCLE':['循环转账','Cycle'],'GATHER-SCATTER':['归集后分散','Gather-scatter'],
  'SCATTER-GATHER':['分散后归集','Scatter-gather'],'BIPARTITE':['双层互转','Bipartite'],'STACK':['层层转移','Stack'],'RANDOM':['混合路径','Random']
};
const CURRENCIES={
  'Australian Dollar':'澳元','Bitcoin':'比特币','Brazil Real':'巴西雷亚尔','Canadian Dollar':'加元','Euro':'欧元','Mexican Peso':'墨西哥比索','Ruble':'俄罗斯卢布','Rupee':'印度卢比','Saudi Riyal':'沙特里亚尔','Shekel':'以色列谢克尔','Swiss Franc':'瑞士法郎','UK Pound':'英镑','US Dollar':'美元','Yen':'日元','Yuan':'人民币'
};
const FORMATS={'ACH':'自动清算转账','Bitcoin':'比特币转账','Cash':'现金','Cheque':'支票','Credit Card':'信用卡','Reinvestment':'再投资','Wire':'电汇'};
const ENTITY_TYPES={'Corporation':'公司','Partnership':'合伙企业','Sole Proprietorship':'独资企业','Country':'国家'};
function createLocale(language){
  const lang=language==='en'?'en':'zh', zh=lang==='zh', copy=COPY[lang];
  const t=(id,values={})=>{
    const label=(copy[id]??id).replace(/\{(\w+)\}/g,(_,k)=>String(values[k]??''));
    return zh?label:label.replace(/\b1 transactions\b/g,'1 transaction').replace(/\b1 related transactions\b/g,'1 related transaction').replace(/\b1 accounts\b/g,'1 account').replace(/\b1 entities\b/g,'1 entity').replace(/\b1 cases\b/g,'1 case');
  };
  const parsed=v=>new Date(typeof v==='number'?v*60000:String(v).replaceAll('/','-').replace(' ','T')+(String(v).length===10?'T00:00':'')+'Z');
  const fmt=(v,options)=>new Intl.DateTimeFormat(zh?'zh-CN':'en-GB',{timeZone:'UTC',...options}).format(parsed(v));
  return {lang,zh,t,
    pattern:code=>PATTERNS[code]?.[zh?0:1]??code,
    entity:name=>zh?String(name??'').replace(/\b(Corporation|Partnership|Sole Proprietorship|Country) #(\d+)/g,(_,kind,id)=>`${ENTITY_TYPES[kind]} #${id}`):String(name??''),
    currency:name=>zh?CURRENCIES[name]??name:name,
    payment:name=>zh?FORMATS[name]??name:name==='ACH'?'ACH transfer':name==='Bitcoin'?'Bitcoin transfer':name,
    date:v=>fmt(v,{year:'numeric',month:'2-digit',day:'2-digit'}),
    shortDate:v=>fmt(v,{month:'2-digit',day:'2-digit'}),
    time:v=>fmt(v,{hour:'2-digit',minute:'2-digit',hourCycle:'h23'}),
    stamp:v=>fmt(v,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}),
    shortStamp:v=>fmt(v,{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}),
    axis:v=>zh?(v>=1e4?Number((v/1e4).toFixed(1))+'万':v.toLocaleString('zh-CN')):(v>=1e6?Number((v/1e6).toFixed(1))+'m':v>=1e3?Number((v/1e3).toFixed(0))+'k':v)
  };
}
