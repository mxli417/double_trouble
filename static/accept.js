const inviteToken = new URLSearchParams(window.location.hash.slice(1)).get('token');
window.history.replaceState({}, '', '/accept');
const form = document.querySelector('#accept-form');
const status = document.querySelector('#accept-status');
if (!inviteToken) { form.classList.add('hidden'); status.textContent = 'This invitation link is invalid or expired.'; }
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  if (data.get('password') !== data.get('confirm')) { status.textContent = 'Passwords do not match.'; return; }
  status.textContent = 'Activating account…';
  try {
    const response = await fetch('/api/auth/accept-invite', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: inviteToken, password: data.get('password') }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not accept invitation.');
    status.textContent = 'Account active. Taking you to the game…';
    window.location.replace('/');
  } catch (error) { status.textContent = error.message; }
});
