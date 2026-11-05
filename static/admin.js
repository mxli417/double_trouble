const statusLine = document.querySelector('#admin-status');
const content = document.querySelector('#admin-content');
const fmt = (value) => value ? new Date(value).toLocaleString() : '—';
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

async function init() {
  try {
    const me = await api('/api/auth/me');
    if (me.role !== 'admin') throw new Error('Admin role required.');
    document.querySelector('#admin-who').textContent = me.email;
    content.classList.remove('hidden');
    statusLine.classList.add('hidden');
    await Promise.all([loadOverview(), loadUsers(), loadInferences(), loadUploads(), loadActivity(), loadAudit()]);
  } catch (error) { statusLine.textContent = error.message; if (error.message.includes('Sign in')) setTimeout(() => location.replace('/'), 700); }
}

async function loadOverview() {
  const d = await api('/api/admin/overview');
  const stats = [['Active accounts', d.active_users], ['Inferences · 24h', d.inferences_24h], ['Failed inferences · 24h', d.failed_24h], ['Failed sign-ins · 24h', d.failed_logins_24h], ['Failure rate', `${Math.round(d.failure_rate_24h * 100)}%`]];
  document.querySelector('#stats').innerHTML = stats.map(([label, value]) => `<article><small>${esc(label)}</small><b>${esc(value)}</b></article>`).join('');
  document.querySelector('#volume-list').innerHTML = d.top_users_24h.map((u) => `<li>${esc(u.email)} <span>${esc(u.count)} matches${u.flagged ? ' · review suggested' : ''}</span></li>`).join('') || '<li>No matches in the last 24 hours.</li>';
}

async function loadUsers() {
  const users = await api('/api/admin/users');
  document.querySelector('#users-table').innerHTML = users.map((u) => `<tr><td>${esc(u.email)}</td><td><select data-role="${esc(u.id)}"><option value="user" ${u.role === 'user' ? 'selected' : ''}>user</option><option value="admin" ${u.role === 'admin' ? 'selected' : ''}>admin</option></select></td><td><span class="state ${esc(u.status)}">${esc(u.status)}</span></td><td>${esc(fmt(u.last_login_at))}</td><td>${u.status === 'active' ? `<button class="small-action" data-status="${esc(u.id)}" data-next="disabled">Disable</button> <button class="small-action" data-link="${esc(u.id)}" data-kind="password-reset">Reset password</button>` : u.status === 'disabled' ? `<button class="small-action" data-status="${esc(u.id)}" data-next="active">Enable</button>` : `<button class="small-action" data-link="${esc(u.id)}" data-kind="invitation">Resend invite</button>`}</td></tr>`).join('');
  document.querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', async () => { try { await api(`/api/admin/users/${encodeURIComponent(button.dataset.status)}/status?status=${button.dataset.next}`, { method: 'PATCH' }); await loadUsers(); } catch (e) { alert(e.message); } }));
  document.querySelectorAll('[data-role]').forEach((select) => select.addEventListener('change', async () => { try { await api(`/api/admin/users/${encodeURIComponent(select.dataset.role)}/role`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: select.value }) }); } catch (e) { alert(e.message); await loadUsers(); } }));
  document.querySelectorAll('[data-link]').forEach((button) => button.addEventListener('click', async () => { try { const result = await api(`/api/admin/users/${encodeURIComponent(button.dataset.link)}/${button.dataset.kind}`, { method: 'POST' }); const box = document.querySelector('#invite-result'); box.classList.remove('hidden'); box.innerHTML = `One-time link for <b>${esc(result.email)}</b> · expires ${esc(fmt(result.expires_at))}<input readonly value="${esc(result.invite_url)}"><small>Copy this link now. It is shown once and cannot be recovered later.</small>`; window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) { alert(e.message); } }));
}

async function loadInferences() {
  const rows = await api('/api/admin/inferences?limit=100');
  document.querySelector('#inference-table').innerHTML = rows.map((r) => `<tr><td>${esc(fmt(r.created_at))}</td><td>${esc(r.user_email || 'deleted account')}</td><td><span class="state ${esc(r.status)}">${esc(r.status)}${r.reason ? ` · ${esc(r.reason)}` : ''}</span></td><td>${esc(r.duration_ms)} ms</td><td>${esc(r.model_version)}</td><td>${r.results.map((x) => `${esc(x.name || x.celebrity_id)} (${esc(x.similarity)})`).join('<br>') || '—'}</td></tr>`).join('') || '<tr><td colspan="6">No inference events yet.</td></tr>';
}

async function loadUploads() {
  const rows = await api('/api/admin/consented-uploads?limit=100');
  document.querySelector('#uploads-table').innerHTML = rows.map((r) => `<tr><td>${esc(fmt(r.consented_at))}<br><small>${esc(r.consent_text_version)}</small></td><td>${esc(r.user_email || 'deleted account')}</td><td>${esc(fmt(r.expires_at))}</td><td>${esc(r.model_version)}</td><td>${esc(r.embedding_dimensions)} dimensions</td><td><a class="small-action" href="/api/admin/consented-uploads/${encodeURIComponent(r.id)}/image" target="_blank" rel="noopener">View image</a> <a class="small-action" href="/api/admin/consented-uploads/${encodeURIComponent(r.id)}/embedding" target="_blank" rel="noopener">View vector</a> <button class="small-action" data-upload-delete="${esc(r.id)}">Delete</button></td></tr>`).join('') || '<tr><td colspan="6">No consented uploads retained.</td></tr>';
  document.querySelectorAll('[data-upload-delete]').forEach((button) => button.addEventListener('click', async () => {
    if (!window.confirm('Permanently delete this encrypted upload and its vector?')) return;
    try { await api(`/api/admin/consented-uploads/${encodeURIComponent(button.dataset.uploadDelete)}`, { method: 'DELETE' }); await loadUploads(); } catch (error) { alert(error.message); }
  }));
}

async function loadAudit() {
  const rows = await api('/api/admin/audit?limit=100');
  document.querySelector('#audit-table').innerHTML = rows.map((r) => `<tr><td>${esc(fmt(r.created_at))}</td><td>${esc(r.actor_email || 'system')}</td><td>${esc(r.action)}</td><td>${esc(JSON.stringify(r.details))}</td></tr>`).join('');
}

async function loadActivity() {
  const rows = await api('/api/admin/activity?limit=100');
  document.querySelector('#activity-table').innerHTML = rows.map((r) => `<tr><td>${esc(fmt(r.created_at))}</td><td>${esc(r.user_email || 'deleted account')}</td><td>${esc(r.action)}</td><td>${esc(JSON.stringify(r.details))}</td></tr>`).join('') || '<tr><td colspan="4">No activity yet.</td></tr>';
}

document.querySelector('#invite-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  const box = document.querySelector('#invite-result');
  try {
    const result = await api('/api/admin/invitations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    box.classList.remove('hidden');
    box.innerHTML = `Invite link for <b>${esc(result.email)}</b> · expires ${esc(fmt(result.expires_at))}<input readonly value="${esc(result.invite_url)}"><small>Copy this link now. It is shown once and cannot be recovered later.</small>`;
    event.currentTarget.reset(); await loadUsers();
  } catch (error) { box.classList.remove('hidden'); box.textContent = error.message; }
});

document.querySelector('#admin-logout').addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST' }); location.replace('/'); });
init();
