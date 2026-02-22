// ── Configuration ────────────────────────────────────────────────────────────

const PROFILES = ['UMA', 'AK'];

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  apiUrl: '',
  apiKey: '',
  profile: 'UMA',
  events: [],
  selectedEventId: null,
};

// ── Boot ─────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
  const url = localStorage.getItem('apiUrl');
  const key = localStorage.getItem('apiKey');
  if (url && key) {
    state.apiUrl = url;
    state.apiKey = key;
    showApp();
  } else {
    document.getElementById('setup').style.display = 'flex';
  }
});

// ── Setup / Config ────────────────────────────────────────────────────────────

async function saveConfig() {
  const url = document.getElementById('cfgUrl').value.trim().replace(/\/$/, '');
  const key = document.getElementById('cfgKey').value.trim();
  const errEl = document.getElementById('setupErr');
  errEl.textContent = '';

  if (!url || !key) { errEl.textContent = 'Both fields are required.'; return; }

  try {
    const res = await fetch(`${url}/api/validate_key`, { headers: { 'X-API-Key': key } });
    const data = await res.json();
    if (!data.valid) { errEl.textContent = 'API key rejected: ' + (data.error || 'invalid'); return; }
  } catch (e) {
    errEl.textContent = `Cannot reach API: ${e.message}`;
    return;
  }

  localStorage.setItem('apiUrl', url);
  localStorage.setItem('apiKey', key);
  state.apiUrl = url;
  state.apiKey = key;
  document.getElementById('setup').style.display = 'none';
  showApp();
}

function logout() {
  localStorage.removeItem('apiUrl');
  localStorage.removeItem('apiKey');
  document.getElementById('app').style.display = 'none';
  document.getElementById('setup').style.display = 'flex';
  document.getElementById('cfgUrl').value = '';
  document.getElementById('cfgKey').value = '';
  document.getElementById('setupErr').textContent = '';
}

// ── App Init ──────────────────────────────────────────────────────────────────

function showApp() {
  document.getElementById('app').style.display = 'flex';
  buildTabs();
  loadEvents();
}

function buildTabs() {
  const nav = document.getElementById('profileTabs');
  nav.innerHTML = '';
  for (const p of PROFILES) {
    const btn = document.createElement('button');
    btn.textContent = p;
    btn.dataset.profile = p;
    if (p === state.profile) btn.classList.add('active');
    btn.onclick = () => switchProfile(p);
    nav.appendChild(btn);
  }
}

function switchProfile(profile) {
  state.profile = profile;
  state.selectedEventId = null;
  hideForm();
  closeNotifs();
  document.querySelectorAll('#profileTabs button').forEach(b =>
    b.classList.toggle('active', b.dataset.profile === profile)
  );
  loadEvents();
}

// ── API Helper ────────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${state.apiUrl}${path}`, opts);
  return res.json();
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer;
function toast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

// ── Date Helpers ──────────────────────────────────────────────────────────────

// datetime-local value ("YYYY-MM-DDTHH:MM") → unix timestamp (UTC)
function toUnix(dtLocalValue) {
  return Math.floor(new Date(dtLocalValue + ':00Z').getTime() / 1000);
}

// unix timestamp (string or number) → human readable UTC string
function fmtDate(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = Number(val);
  const d = (!isNaN(n) && n > 1e9) ? new Date(n * 1000) : new Date(val);
  if (isNaN(d)) return String(val);
  // e.g. "2024-03-15 14:00 UTC"
  return d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

// unix timestamp (string or number) → datetime-local value for input prefill
function toDatetimeLocal(val) {
  if (!val) return '';
  const n = Number(val);
  const d = (!isNaN(n) && n > 1e9) ? new Date(n * 1000) : new Date(val);
  if (isNaN(d)) return '';
  return d.toISOString().slice(0, 16);
}

// ── XSS guard ─────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Events – Load & Render ────────────────────────────────────────────────────

async function loadEvents() {
  const el = document.getElementById('events-list');
  el.innerHTML = '<div class="loading">Loading events…</div>';
  try {
    const data = await api('GET', `/api/events/${state.profile}`);
    if (!data.success) throw new Error(data.error);
    state.events = data.events;
    renderEvents();
  } catch (e) {
    el.innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`;
  }
}

function renderEvents() {
  const el = document.getElementById('events-list');
  if (!state.events.length) {
    el.innerHTML = '<div class="empty">No events found. Add one with the button above.</div>';
    return;
  }
  el.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Title</th>
          <th>Category</th>
          <th>Start (UTC)</th>
          <th>End (UTC)</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        ${state.events.map(ev => `
          <tr id="evrow-${ev.id}" class="${ev.id === state.selectedEventId ? 'selected' : ''}">
            <td>${ev.id}</td>
            <td>${esc(ev.title)}</td>
            <td>${esc(ev.category)}</td>
            <td>${fmtDate(ev.start)}</td>
            <td>${fmtDate(ev.end)}</td>
            <td>
              <div class="actions">
                <button class="btn btn-primary btn-sm" onclick="showEditForm(${ev.id})">Edit</button>
                <button class="btn btn-danger btn-sm"  onclick="removeEvent(${ev.id})">Remove</button>
                <button class="btn btn-teal btn-sm"    onclick="showNotifs(${ev.id})">Notifs</button>
              </div>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ── Events – Add / Edit Form ──────────────────────────────────────────────────

function showAddForm() {
  document.getElementById('form-title').textContent = 'Add Event';
  document.getElementById('editId').value = '';
  document.getElementById('fTitle').value = '';
  document.getElementById('fCategory').value = '';
  document.getElementById('fImage').value = '';
  document.getElementById('fStart').value = '';
  document.getElementById('fEnd').value = '';
  document.getElementById('event-form').style.display = 'block';
  document.getElementById('fTitle').focus();
}

async function showEditForm(eventId) {
  const ev = state.events.find(e => e.id === eventId);
  if (!ev) return;

  document.getElementById('form-title').textContent = 'Edit Event';
  document.getElementById('editId').value = eventId;
  document.getElementById('fTitle').value = ev.title;
  document.getElementById('fCategory').value = ev.category;
  document.getElementById('fStart').value = toDatetimeLocal(ev.start);
  document.getElementById('fEnd').value = toDatetimeLocal(ev.end);
  document.getElementById('fImage').value = '';  // fetch separately (get_events omits image)
  document.getElementById('event-form').style.display = 'block';
  document.getElementById('fTitle').focus();

  // Fetch the image URL (only returned by get_event_by_id)
  try {
    const data = await api('GET', `/api/events/${state.profile}/${eventId}`);
    if (data.success) document.getElementById('fImage').value = data.event.image || '';
  } catch (_) { /* non-critical */ }
}

function hideForm() {
  document.getElementById('event-form').style.display = 'none';
}

async function submitForm() {
  const id       = document.getElementById('editId').value;
  const title    = document.getElementById('fTitle').value.trim();
  const category = document.getElementById('fCategory').value.trim();
  const startVal = document.getElementById('fStart').value;
  const endVal   = document.getElementById('fEnd').value;
  const image    = document.getElementById('fImage').value.trim();

  if (!title || !category || !startVal || !endVal) {
    toast('Title, category, start and end are all required.', 'error');
    return;
  }

  const body = { title, category, start_unix: toUnix(startVal), end_unix: toUnix(endVal) };
  if (image) body.image = image;

  try {
    const data = id
      ? await api('PUT',  `/api/events/${state.profile}/${id}`, body)
      : await api('POST', `/api/events/${state.profile}`, body);
    if (!data.success) throw new Error(data.error);
    toast(id ? 'Event updated.' : 'Event added.');
    hideForm();
    loadEvents();
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Events – Remove ───────────────────────────────────────────────────────────

async function removeEvent(eventId) {
  const ev = state.events.find(e => e.id === eventId);
  const name = ev ? `"${ev.title}"` : `#${eventId}`;
  if (!confirm(`Remove event ${name} and all its pending notifications?`)) return;

  try {
    const data = await api('DELETE', `/api/events/${state.profile}/${eventId}`);
    if (!data.success) throw new Error(data.error);
    toast('Event removed.');
    if (state.selectedEventId === eventId) closeNotifs();
    loadEvents();
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Dashboard Refresh ─────────────────────────────────────────────────────────

async function refreshDashboard() {
  try {
    const data = await api('POST', `/api/dashboard/${state.profile}/refresh`);
    if (!data.success) throw new Error(data.error);
    toast('Dashboard refreshed.');
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Notifications ─────────────────────────────────────────────────────────────

async function showNotifs(eventId) {
  state.selectedEventId = eventId;

  // Highlight the selected event row
  document.querySelectorAll('#events-list tr').forEach(r => r.classList.remove('selected'));
  const row = document.getElementById(`evrow-${eventId}`);
  if (row) row.classList.add('selected');

  const ev = state.events.find(e => e.id === eventId);
  document.getElementById('notif-event-name').textContent = ev ? ev.title : `Event #${eventId}`;
  document.getElementById('notifs-section').style.display = 'block';

  await loadNotifications(eventId);
}

function closeNotifs() {
  state.selectedEventId = null;
  document.getElementById('notifs-section').style.display = 'none';
  document.querySelectorAll('#events-list tr').forEach(r => r.classList.remove('selected'));
}

async function loadNotifications(eventId) {
  const el = document.getElementById('notifs-list');
  el.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const data = await api('GET', `/api/events/${state.profile}/${eventId}/notifications`);
    if (!data.success) throw new Error(data.error);
    renderNotifications(data.notifications);
  } catch (e) {
    el.innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`;
  }
}

function renderNotifications(notifs) {
  const el = document.getElementById('notifs-list');
  if (!notifs.length) {
    el.innerHTML = '<div class="empty">No pending notifications for this event.</div>';
    return;
  }
  el.innerHTML = `
    <table>
      <thead>
        <tr><th>ID</th><th>Type</th><th>Fires At (UTC)</th><th></th></tr>
      </thead>
      <tbody>
        ${notifs.map(n => `
          <tr>
            <td>${n.id}</td>
            <td>${esc(n.timing_type)}</td>
            <td>${fmtDate(n.notify_unix)}</td>
            <td>
              <button class="btn btn-danger btn-sm" onclick="removeNotification(${n.id})">Remove</button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function removeNotification(notifId) {
  try {
    const data = await api('DELETE', `/api/notifications/${notifId}`);
    if (!data.success) throw new Error(data.error);
    toast('Notification removed.');
    if (state.selectedEventId !== null) loadNotifications(state.selectedEventId);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

async function refreshNotifications() {
  if (state.selectedEventId === null) return;
  try {
    const data = await api('POST', `/api/events/${state.profile}/${state.selectedEventId}/notifications/refresh`);
    if (!data.success) throw new Error(data.error);
    toast('Notifications regenerated.');
    loadNotifications(state.selectedEventId);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}
