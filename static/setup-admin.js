const form = document.querySelector('#setup-form');
const status = document.querySelector('#setup-status');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const secret = data.get('secret');
  const password = data.get('password');
  if (password !== data.get('confirm')) { status.textContent = 'Passwords do not match.'; return; }
  status.textContent = 'Creating the first administrator…';
  try {
    const response = await fetch('/api/setup/first-admin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ secret, email: data.get('email'), password }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Setup failed.');
    status.textContent = 'Administrator created. Remove the temporary secret from Render, then continue.';
    window.showNotification?.({ message: status.textContent, type: 'success', title: 'Admin created' });
    form.reset();
    form.classList.add('hidden');
    document.querySelector('#continue-link').classList.remove('hidden');
  } catch (error) { status.textContent = error.message; window.showNotification?.({ message: error.message, type: 'error', title: 'Setup failed' }); form.elements.secret.value = ''; }
});
