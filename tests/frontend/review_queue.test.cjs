// Do tests with the dashboard event queue when a replay tick changes the evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../../src/amlens/components/dashboard/script.js'), 'utf8');
const sendStart = source.indexOf('  function send(');
const sendEnd = source.indexOf('  function updateHTML(', sendStart);
const queueStart = source.indexOf('    const next=local.commands.shift();');
const queueEnd = source.indexOf('\n', queueStart);
assert(sendStart >= 0 && sendEnd > sendStart && queueStart > sendEnd);
const factory = new Function('local', 'detail', 'setTriggerValue', 'crypto', 'setTimeout', 'clearTimeout', 'get',
  'let deadline;\n' + source.slice(sendStart, sendEnd) +
  '\nreturn { send, drain: () => {' + source.slice(queueStart, queueEnd) + '} };');
const local = {pending: true, commands: [], revision: 1};
const packets = [];
const renderer = evidenceId => factory(local, {evidenceId}, (_, packet) => packets.push(packet), crypto,
  () => 1, () => {}, () => ({}));
renderer('evidence-before-tick').send('status', 'reviewed');
assert.equal(packets.length, 0);
assert.equal(local.commands.length, 1);
local.pending = false;
local.revision = 2;
renderer('new-evidence-after-tick').drain();
assert.equal(packets.length, 1);
assert.equal(packets[0].action, 'status');
assert.equal(packets[0].value, 'reviewed');
assert.equal(packets[0].evidenceId, 'evidence-before-tick');
console.log('PASS: queued review keeps the clicked evidence identity across a detection tick.');
