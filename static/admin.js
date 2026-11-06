const statusLine = document.querySelector('#admin-status');
const content = document.querySelector('#admin-content');
const fmt = (value) => value ? new Date(value).toLocaleString() : '-';
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const notify = (message, type = 'info', title = '') => window.showNotification?.({ message, type, title });

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
  } catch (error) {
    statusLine.textContent = error.message;
    notify(error.message, 'error', 'Admin panel error');
    if (error.message.includes('Sign in')) setTimeout(() => location.replace('/'), 700);
  }
}

async function loadOverview() {
  const data = await api('/api/admin/overview');
  const stats = [
    ['Active accounts', data.active_users],
    ['Inferences - 24h', data.inferences_24h],
    ['Failed inferences - 24h', data.failed_24h],
    ['Failed sign-ins - 24h', data.failed_logins_24h],
    ['Failure rate', `${Math.round(data.failure_rate_24h * 100)}%`],
  ];
  document.querySelector('#stats').innerHTML = stats.map(([label, value]) => `<article><small>${esc(label)}</small><b>${esc(value)}</b></article>`).join('');
  document.querySelector('#volume-list').innerHTML = data.top_users_24h.map((user) => `<li>${esc(user.email)} <span>${esc(user.count)} matches${user.flagged ? ' - review suggested' : ''}</span></li>`).join('') || '<li>No matches in the last 24 hours.</li>';
}

async function loadUsers() {
  const users = await api('/api/admin/users');
  document.querySelector('#users-table').innerHTML = users.map((user) => `<tr><td>${esc(user.email)}</td><td><select data-role="${esc(user.id)}"><option value="user" ${user.role === 'user' ? 'selected' : ''}>user</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>admin</option></select></td><td><span class="state ${esc(user.status)}">${esc(user.status)}</span></td><td>${esc(fmt(user.last_login_at))}</td><td>${user.status === 'active' ? `<button class="small-action" data-status="${esc(user.id)}" data-next="disabled">Disable</button> <button class="small-action" data-link="${esc(user.id)}" data-kind="password-reset">Reset password</button>` : user.status === 'disabled' ? `<button class="small-action" data-status="${esc(user.id)}" data-next="active">Enable</button>` : `<button class="small-action" data-link="${esc(user.id)}" data-kind="invitation">Resend invite</button>`}</td></tr>`).join('');
  document.querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', async () => {
    try {
      await api(`/api/admin/users/${encodeURIComponent(button.dataset.status)}/status?status=${button.dataset.next}`, { method: 'PATCH' });
      notify('Account status updated.', 'success');
      await loadUsers();
    } catch (error) { notify(error.message, 'error', 'Account update failed'); }
  }));
  document.querySelectorAll('[data-role]').forEach((select) => select.addEventListener('change', async () => {
    try {
      await api(`/api/admin/users/${encodeURIComponent(select.dataset.role)}/role`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: select.value }) });
      notify('Account role updated.', 'success');
    } catch (error) {
      notify(error.message, 'error', 'Role update failed');
      await loadUsers();
    }
  }));
  document.querySelectorAll('[data-link]').forEach((button) => button.addEventListener('click', async () => {
    try {
      const result = await api(`/api/admin/users/${encodeURIComponent(button.dataset.link)}/${button.dataset.kind}`, { method: 'POST' });
      const box = document.querySelector('#invite-result');
      box.classList.remove('hidden');
      box.innerHTML = `One-time link for <b>${esc(result.email)}</b> - expires ${esc(fmt(result.expires_at))}<input readonly value="${esc(result.invite_url)}"><small>Copy this link now. It is shown once and cannot be recovered later.</small>`;
      notify('One-time account link created.', 'success');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) { notify(error.message, 'error', 'Link creation failed'); }
  }));
}

async function loadInferences() {
  const rows = await api('/api/admin/inferences?limit=100');
  document.querySelector('#inference-table').innerHTML = rows.map((row) => `<tr><td>${esc(fmt(row.created_at))}</td><td>${esc(row.user_email || 'deleted account')}</td><td><span class="state ${esc(row.status)}">${esc(row.status)}${row.reason ? ` - ${esc(row.reason)}` : ''}</span></td><td>${esc(row.duration_ms)} ms</td><td>${esc(row.model_version)}</td><td>${row.results.map((item) => `${esc(item.name || item.celebrity_id)} (${esc(item.similarity)})`).join('<br>') || '-'}</td></tr>`).join('') || '<tr><td colspan="6">No inference events yet.</td></tr>';
}

async function loadUploads() {
  const rows = await api('/api/admin/consented-uploads?limit=100');
  document.querySelector('#uploads-table').innerHTML = rows.map((row) => `<tr><td>${esc(fmt(row.consented_at))}<br><small>${esc(row.consent_text_version)}${row.hot_or_not_consented_at ? ` · Hot or Not ${esc(fmt(row.hot_or_not_consented_at))}` : ''}</small></td><td>${esc(row.user_email || 'deleted account')}</td><td>${esc(fmt(row.expires_at))}</td><td>${esc(row.model_version)}</td><td>${esc(row.embedding_dimensions)} dimensions</td><td><a class="small-action" href="/api/admin/consented-uploads/${encodeURIComponent(row.id)}/image" target="_blank" rel="noopener">View image</a> <a class="small-action" href="/api/admin/consented-uploads/${encodeURIComponent(row.id)}/embedding" target="_blank" rel="noopener">View vector</a> <button class="small-action" data-upload-delete="${esc(row.id)}">Delete</button></td></tr>`).join('') || '<tr><td colspan="6">No consented uploads retained.</td></tr>';
  document.querySelectorAll('[data-upload-delete]').forEach((button) => button.addEventListener('click', async () => {
    if (!window.confirm('Permanently delete this encrypted upload, vector, and linked Hot or Not entry?')) return;
    try {
      await api(`/api/admin/consented-uploads/${encodeURIComponent(button.dataset.uploadDelete)}`, { method: 'DELETE' });
      notify('Upload and linked Hot or Not entry deleted.', 'success');
      await loadUploads();
    } catch (error) { notify(error.message, 'error', 'Deletion failed'); }
  }));
}

async function loadAudit() {
  const rows = await api('/api/admin/audit?limit=100');
  document.querySelector('#audit-table').innerHTML = rows.map((row) => `<tr><td>${esc(fmt(row.created_at))}</td><td>${esc(row.actor_email || 'system')}</td><td>${esc(row.action)}</td><td>${esc(JSON.stringify(row.details))}</td></tr>`).join('');
}

async function loadActivity() {
  const rows = await api('/api/admin/activity?limit=100');
  document.querySelector('#activity-table').innerHTML = rows.map((row) => `<tr><td>${esc(fmt(row.created_at))}</td><td>${esc(row.user_email || 'deleted account')}</td><td>${esc(row.action)}</td><td>${esc(JSON.stringify(row.details))}</td></tr>`).join('') || '<tr><td colspan="4">No activity yet.</td></tr>';
}

document.querySelector('#invite-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  const box = document.querySelector('#invite-result');
  try {
    const result = await api('/api/admin/invitations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    box.classList.remove('hidden');
    box.innerHTML = `Invite link for <b>${esc(result.email)}</b> - expires ${esc(fmt(result.expires_at))}<input readonly value="${esc(result.invite_url)}"><small>Copy this link now. It is shown once and cannot be recovered later.</small>`;
    event.currentTarget.reset();
    notify('Invitation created.', 'success');
    await loadUsers();
  } catch (error) {
    box.classList.remove('hidden');
    box.textContent = error.message;
    notify(error.message, 'error', 'Invitation failed');
  }
});

document.querySelector('#admin-logout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  location.replace('/');
});

init();
