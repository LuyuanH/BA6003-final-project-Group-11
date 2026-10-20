// Verify evidence references and model text are safe, and queued requests retain case identity.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assets = path.join(__dirname, '../../src/amlens/components/dashboard');
const script = fs.readFileSync(path.join(assets, 'script.js'), 'utf8');
const renderer = fs.readFileSync(path.join(assets, 'analysis.js'), 'utf8');
const locale = fs.readFileSync(path.join(assets, 'i18n.js'), 'utf8');
const escLine = script.split('\n').find(line => line.startsWith('const esc ='));
const render = new Function(`${escLine}\n${renderer}\n${locale}\nreturn (entry,language) => analysisReportMarkup(entry,{span_hours:1},createLocale(language).t);`)();
const report = {
  summary:'<img src=x onerror=alert(1)>', assessment:'insufficient_evidence', reason:'A & B',
  pattern_assessment:{verdict:'partial',explanation:'<script>alert(1)</script>',transaction_ids:[17],feature_names:[]},
  supporting_evidence:[{explanation:'Transfer evidence',transaction_ids:[17],feature_names:['span_hours']}],
  counter_evidence:[], normal_explanations:['Unverified <hypothesis>'], missing_information:[], next_steps:['Check documentation']
};
for (const language of ['zh','en']) {
  const html = render({report},language);
  assert(!html.includes('<img'));
  assert(!html.includes('<script>'));
  assert(html.includes('&lt;img'));
  assert(html.includes('A &amp; B'));
  assert(html.includes('data-analysis-tx="17"'));
  assert(html.includes('span_hours: 1'));
  assert(html.includes(language==='zh'?'证据不足':'Insufficient evidence'));
}
const formatting = script.split('\n').filter(line => line.startsWith('const num =') || line.startsWith('const caseId =')).join('\n');
const renderOverview = new Function(`${escLine}\n${formatting}\n${renderer}\n${locale}\nreturn (entry,language) => {const L=createLocale(language);return overviewReportMarkup(entry,L.t,L.pattern);};`)();
const overview = {
  metrics:{pending_cases:3,'fan_in.active_cases':2},
  report:{summary:'<img src=x onerror=alert(1)>',findings:[{title:'<script>unsafe</script>',explanation:'Check A & B',metric_refs:['pending_cases','fan_in.active_cases']}],focus_cases:[{case_id:7,reason:'Inspect <evidence>'}],next_steps:['Check <documents>'],limitations:['Snapshot only']}
};
for (const language of ['zh','en']) {
  const html = renderOverview(overview,language);
  assert(!html.includes('<img'));
  assert(!html.includes('<script>'));
  assert(html.includes('&lt;img'));
  assert(html.includes('data-insight-case="7"'));
  assert(html.includes('C-0008'));
  assert(html.includes(': 3'));
  assert(html.includes(language==='zh'?'集中收款':'Fan-in'));
}
// Compile the complete component body, catching JS syntax errors across all assets.
new Function(locale+'\n'+renderer+'\n'+script.replace('export default function','return function'));
const start = script.indexOf('  function send(');
const end = script.indexOf('  function updateHTML(',start);
const drainStart = script.indexOf('    const next=local.commands.shift();');
const drainEnd = script.indexOf('\n',drainStart);
const factory = new Function('local','detail','setTriggerValue','crypto','setTimeout','clearTimeout','get',
  'let deadline;\n'+script.slice(start,end)+'\nreturn {send,drain:()=>{'+script.slice(drainStart,drainEnd)+'}};');
const local={pending:true,commands:[],revision:1};
const packets=[];
const instance=detail=>factory(local,detail,(_,packet)=>packets.push(packet),crypto,()=>1,()=>{},()=>({}));
instance({id:3,evidenceId:'clicked-version'}).send('analyze',3);
local.pending=false;
local.revision=2;
instance({id:8,evidenceId:'different-case'}).drain();
assert.equal(packets[0].value,3);
assert.equal(packets[0].evidenceId,'clicked-version');
console.log('PASS: case and overview output is escaped; metric references and queued evidence identity are preserved.');
