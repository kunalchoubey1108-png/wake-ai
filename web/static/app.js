const params = new URLSearchParams(location.search);
if (params.get('replay') === '1') {
  const cb = document.getElementById('replay');
  if (cb) cb.checked = true;
}

const timelineEl = document.getElementById('timeline');
const graveyardEl = document.getElementById('graveyard');
const evidenceEl = document.getElementById('evidence');
const attackGrid = document.getElementById('attack-grid');
const resurrectAllBtn = document.getElementById('resurrect-all');
const downloadA = document.getElementById('download');
const statusEl = document.getElementById('status');
const toastEl = document.getElementById('resurrect-toast');
let currentJob = null;

function addEvent(msg) {
  const li = document.createElement('li');
  li.textContent = msg;
  timelineEl.prepend(li);
}

function toast(msg) {
  toastEl.hidden = false;
  toastEl.textContent = msg;
  clearTimeout(toastEl._t);
  toastEl._t = setTimeout(() => { toastEl.hidden = true; }, 4000);
}

function setStatus(msg) {
  statusEl.textContent = msg || '';
}

document.getElementById('run').onclick = async () => {
  timelineEl.innerHTML = '';
  graveyardEl.innerHTML = '';
  resurrectAllBtn.disabled = true;
  downloadA.hidden = true;
  toastEl.hidden = true;
  setStatus('Starting…');
  const fd = new FormData();
  fd.append('demo_id', document.getElementById('demo').value);
  if (document.getElementById('replay').checked) fd.append('replay', 'true');
  const res = await fetch('/api/jobs', { method: 'POST', body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    addEvent('Error: ' + (data.detail || res.status));
    setStatus('Failed to start');
    return;
  }
  currentJob = data.job_id;
  setStatus((data.replay ? 'Replay ' : 'Live ') + currentJob);
  addEvent('Job ' + currentJob + (data.replay ? ' (replay)' : '') + ' queued');
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
    if (result.containment) {
      evidenceEl.dataset.live = '1';
      evidenceEl.textContent = JSON.stringify(result.containment, null, 2);
      renderAttacksFromContainment(result);
    }
    downloadA.hidden = false;
    downloadA.href = '/api/jobs/' + jobId + '/download';
    resurrectAllBtn.disabled = !(result.removals || []).length;
    setStatus(job.status === 'succeeded' ? 'Done' : ('Finished: ' + job.status));
  });
  es.onerror = () => {
    es.close();
    setStatus('Stream closed');
  };
}

function renderGraveyard(jobId, removals) {
  graveyardEl.innerHTML = '';
  if (!removals.length) {
    graveyardEl.innerHTML = '<p class="hint">No removals in this run (containment-only demos are fine).</p>';
    return;
  }
  for (const r of removals) {
    const div = document.createElement('div');
    div.className = 'gcard';
    div.dataset.id = r.id;
    const hunk = (r.hunk || '').trim();
    div.innerHTML = `
      <div><strong>${escapeHtml(r.id)}</strong> · <code>${escapeHtml(r.symbol || r.kind || '')}</code></div>
      <div class="meta">${escapeHtml(r.file || '')}</div>
      ${hunk ? `<pre class="hunk">${escapeHtml(hunk.slice(0, 500))}</pre>` : ''}
      <div class="gactions"></div>`;
    const actions = div.querySelector('.gactions');
    const btn = document.createElement('button');
    btn.textContent = 'Resurrect';
    btn.title = 'Restore this hunk into the working tree from wake.lock.json';
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = 'Resurrecting…';
      const res = await fetch(`/api/jobs/${jobId}/resurrect/${encodeURIComponent(r.id)}`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        btn.disabled = false;
        btn.textContent = 'Retry';
        toast('Resurrect failed: ' + (data.detail || res.status));
        return;
      }
      div.classList.add('resurrected');
      btn.textContent = 'Resurrected';
      toast('Restored ' + r.id + ' from wake.lock.json');
    };
    actions.appendChild(btn);
    graveyardEl.appendChild(div);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

resurrectAllBtn.onclick = async () => {
  if (!currentJob) return;
  resurrectAllBtn.disabled = true;
  const res = await fetch('/api/jobs/' + currentJob + '/resurrect', { method: 'POST' });
  if (!res.ok) {
    resurrectAllBtn.disabled = false;
    toast('Resurrect all failed');
    return;
  }
  document.querySelectorAll('.gcard').forEach((el) => el.classList.add('resurrected'));
  graveyardEl.querySelectorAll('button').forEach((b) => { b.disabled = true; b.textContent = 'Resurrected'; });
  toast('All removals resurrected');
};

function renderAttacks(ev) {
  attackGrid.innerHTML = '';
  const attacks = ev.attacks || {};
  for (const [name, info] of Object.entries(attacks)) {
    const ok = !!(info && info.pass);
    const div = document.createElement('div');
    div.className = 'attack ' + (ok ? 'pass' : 'fail');
    div.innerHTML = `<div class="name">${escapeHtml(name)}</div>
      <span class="badge ${ok ? 'ok' : 'bad'}">${ok ? 'pass' : 'fail'}</span>`;
    attackGrid.appendChild(div);
  }
}

function renderAttacksFromContainment(result) {
  if (result.attacks) renderAttacks(result);
}

fetch('/api/containment/evidence')
  .then((r) => r.json())
  .then((ev) => {
    renderAttacks(ev);
    if (!evidenceEl.dataset.live) {
      evidenceEl.textContent = JSON.stringify({
        runtime: ev.runtime,
        uid: ev.uid,
        summary_pass: ev.summary_pass,
        container_id: ev.container_id,
        attacks: Object.fromEntries(Object.entries(ev.attacks || {}).map(([k, v]) => [k, { pass: v.pass }])),
        host: ev.host_notes,
        note: 'Recorded runsc evidence. Live job evidence replaces this after a run.',
      }, null, 2);
    }
  })
  .catch(() => {
    evidenceEl.textContent = 'Evidence unavailable.';
  });
