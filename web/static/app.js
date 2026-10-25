const params = new URLSearchParams(location.search);
if (params.get('replay') === '1') {
  const cb = document.getElementById('replay');
  if (cb) cb.checked = true;
}

const timelineEl = document.getElementById('timeline');
const graveyardEl = document.getElementById('graveyard');
const evidenceEl = document.getElementById('evidence');
const resurrectAllBtn = document.getElementById('resurrect-all');
const downloadA = document.getElementById('download');
let currentJob = null;

function addEvent(msg) {
  const li = document.createElement('li');
  li.textContent = msg;
  timelineEl.prepend(li);
}

document.getElementById('run').onclick = async () => {
  timelineEl.innerHTML = '';
  graveyardEl.innerHTML = '';
  resurrectAllBtn.disabled = true;
  downloadA.hidden = true;
  const fd = new FormData();
  fd.append('demo_id', document.getElementById('demo').value);
  if (document.getElementById('replay').checked) fd.append('replay', 'true');
  const res = await fetch('/api/jobs', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) { addEvent('Error: ' + (data.detail || res.status)); return; }
  currentJob = data.job_id;
  addEvent('Job ' + currentJob + ' queued');
  poll(currentJob);
};

async function poll(jobId) {
  const es = new EventSource('/api/jobs/' + jobId + '/events');
  es.addEventListener('timeline', (e) => {
    try {
      const ev = JSON.parse(e.data);
      addEvent((ev.kind || '') + ': ' + (ev.message || e.data));
    } catch {
      addEvent(e.data);
    }
  });
  es.addEventListener('done', async () => {
    es.close();
    const job = await (await fetch('/api/jobs/' + jobId)).json();
    const result = job.result || {};
    renderGraveyard(jobId, result.removals || []);
    if (result.containment) { evidenceEl.dataset.live = '1'; evidenceEl.textContent = JSON.stringify(result.containment, null, 2); }
    else evidenceEl.textContent = 'Host-local run (no container evidence). Sandbox evidence appears when Docker/gVisor is available.';
    downloadA.hidden = false;
    downloadA.href = '/api/jobs/' + jobId + '/download';
    resurrectAllBtn.disabled = !(result.removals || []).length;
  });
}

function renderGraveyard(jobId, removals) {
  graveyardEl.innerHTML = '';
  for (const r of removals) {
    const div = document.createElement('div');
    div.className = 'gcard';
    div.innerHTML = `<strong>${r.id}</strong> · <code>${r.file}</code><div>${r.symbol || r.kind}</div>`;
    const btn = document.createElement('button');
    btn.textContent = 'Resurrect';
    btn.onclick = async () => {
      await fetch(`/api/jobs/${jobId}/resurrect/${r.id}`, { method: 'POST' });
      btn.textContent = 'Resurrected';
      btn.disabled = true;
    };
    div.appendChild(btn);
    graveyardEl.appendChild(div);
  }
}

resurrectAllBtn.onclick = async () => {
  if (!currentJob) return;
  await fetch('/api/jobs/' + currentJob + '/resurrect', { method: 'POST' });
  graveyardEl.innerHTML = '<p>All resurrected.</p>';
  resurrectAllBtn.disabled = true;
};

// Prefill containment panel with real runsc evidence
fetch('/api/containment/evidence').then(r => r.json()).then(ev => {
  if (!evidenceEl || evidenceEl.dataset.live) return;
  evidenceEl.textContent = JSON.stringify({
    runtime: ev.runtime,
    uid: ev.uid,
    summary_pass: ev.summary_pass,
    attacks: Object.fromEntries(Object.entries(ev.attacks || {}).map(([k,v]) => [k, {pass: v.pass}])),
    host: ev.host_notes,
    note: 'Recorded runsc evidence. Live job evidence replaces this after a run.',
  }, null, 2);
}).catch(() => {});
