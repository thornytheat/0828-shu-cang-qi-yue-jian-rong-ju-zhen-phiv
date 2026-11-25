import {element, request} from './client.js';

const stateLabels = {OPEN: '待补证 · 隔离中', DENIED: '已否认 · 仍隔离', RESTORED: '已恢复采信', WITHDRAWN: '补证撤回 · 退回隔离'};
const panel = document.querySelector('#supplements');
const table = document.querySelector('#supplement-rows');
const form = document.querySelector('#supplement-form');
const target = document.querySelector('#supplement-target');
const summary = document.querySelector('#adjust-summary');
const definitionFields = document.querySelector('#definition-fields');
const adjustedEvidence = document.querySelector('#adjusted-evidence');
let batch, view, busy = false;

function announce(text, failure = false) {
  const node = document.querySelector('#notice');
  node.textContent = text;
  node.dataset.failure = String(failure);
}

function currentEntry(record) {
  return view.adjustment.supplements.find(item => item.record === record);
}

function drawTable() {
  table.replaceChildren();
  const head = element('tr');
  head.append(...['记录号', '业务组', '源行', '补证状态', '操作'].map(text => element('th', text, {scope: 'col'})));
  const body = table.createTBody();
  for (const item of view.targets) {
    const entry = currentEntry(item.record);
    const state = entry?.state || 'OPEN';
    const tr = body.insertRow();
    tr.insertCell().textContent = item.record;
    tr.insertCell().textContent = item.case;
    tr.insertCell().textContent = item.lines.join('、');
    tr.insertCell().append(element('span', stateLabels[state] || state,
      {class: 'badge', 'data-result': state === 'RESTORED' ? 'READY' : state}));
    const cell = tr.insertCell();
    if (entry?.state === 'RESTORED') {
      const button = element('button', '撤回补证', {type: 'button', 'data-withdraw': entry.supplement_id,
        'data-revision': entry.revision});
      cell.append(button);
    } else if (!entry) {
      cell.append(element('button', '登记补证', {type: 'button', 'data-record': item.record, 'data-case': item.case}));
    }
  }
  table.createTHead().append(head);
}

function drawSummary() {
  const s = view.adjustment.summary;
  const balance = view.adjustment.balance;
  summary.textContent = `冲突 ${s.conflicts} · 恢复 ${s.restored} · 否认 ${s.denied} · 待补 ${s.open} · 撤回 ${s.withdrawn}
    | 重算后采信 ${balance.accepted} · 隔离 ${balance.isolated} · ${balance.releasable ? '可放行' : '不可放行'}`;
}

export function renderSupplements(currentBatch, adjustment) {
  batch = currentBatch;
  panel.hidden = !(batch?.status === 'CLOSED');
  if (!adjustment) return;
  view = adjustment;
  form.hidden = true;
  adjustedEvidence.hidden = false;
  adjustedEvidence.href = `/api/runs/${batch.id}/adjustment/evidence`;
  drawTable();
  drawSummary();
}

table.addEventListener('click', event => {
  const register = event.target.closest('[data-record]');
  const withdraw = event.target.closest('[data-withdraw]');
  if (register) {
    form.hidden = false;
    target.textContent = `记录 ${register.dataset.record}（业务组 ${register.dataset.case}）`;
    form.dataset.record = register.dataset.record;
    form.reset();
    definitionFields.hidden = true;
  }
  if (withdraw && !busy) {
    busy = true;
    document.body.setAttribute('aria-busy', 'true');
    request(`/api/runs/${batch.id}/supplements/${withdraw.dataset.withdraw}/withdraw`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({revision: Number(withdraw.dataset.revision)}),
    }).then(payload => {
      view = payload.adjustment;
      drawTable(); drawSummary();
      announce('补证已撤回，受影响组已重算');
    }).catch(error => announce(error.message, true))
      .finally(() => {busy = false; document.body.removeAttribute('aria-busy');});
  }
});

form.addEventListener('change', () => {
  definitionFields.hidden = !form.elements.action.value || form.elements.action.value === 'DENY';
});

form.addEventListener('submit', event => {
  event.preventDefault();
  if (busy) return;
  const action = form.elements.action.value;
  const payload = {record: form.dataset.record, action, note: form.elements.note.value};
  if (action === 'CORRECT') {
    payload.definition = {
      field: form.elements.field.value, data_type: Number(form.elements.data_type.value),
      scale: Number(form.elements.scale.value), nullable: Number(form.elements.nullable.value),
      has_default: Number(form.elements.has_default.value),
    };
  }
  busy = true;
  document.body.setAttribute('aria-busy', 'true');
  request(`/api/runs/${batch.id}/supplements`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  }).then(result => {
    view = result.adjustment;
    form.hidden = true;
    drawTable(); drawSummary();
    announce(action === 'DENY' ? '否认已登记，记录仍计隔离' : '正确定义已采信，受影响组已重算');
  }).catch(error => announce(error.message, true))
    .finally(() => {busy = false; document.body.removeAttribute('aria-busy');});
});
