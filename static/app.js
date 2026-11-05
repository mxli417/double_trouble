const tabs = document.querySelectorAll('.tab');
function activateView(view) {
  tabs.forEach((item) => item.classList.toggle('active', item.dataset.view === view));
  document.querySelector('#match-view').classList.toggle('hidden', view !== 'match');
  document.querySelector('#rank-view').classList.toggle('hidden', view !== 'rank');
  if (view === 'rank') loadRankings();
}

tabs.forEach((tab) => tab.addEventListener('click', () => activateView(tab.dataset.view)));

const authScreen = document.querySelector('#auth-screen');
const appContent = document.querySelector('#app-content');
const authStatus = document.querySelector('#auth-status');
const loginForm = document.querySelector('#login-form');

function setSignedIn(user) {
  authScreen.classList.add('hidden');
  appContent.classList.remove('hidden');
  document.querySelector('#science-pill').classList.add('hidden');
  document.querySelector('#account-label').textContent = user.email;
  document.querySelector('#account-label').classList.remove('hidden');
  document.querySelector('#logout-button').classList.remove('hidden');
  document.querySelector('#admin-link').classList.toggle('hidden', user.role !== 'admin');
  loadFeatures();
}

async function loadFeatures() {
  const note = document.querySelector('#feature-note');
  try {
    const response = await fetch('/api/features');
    const features = await response.json();
    if (!response.ok) throw new Error(features.detail || 'Optional services unavailable.');
    document.querySelector('#retention-consent').disabled = !features.retention_available;
    document.querySelector('#narration-consent').disabled = !features.narration_available;
    document.querySelector('#retention-days').textContent = features.retained_upload_days;
    const enabled = [features.retention_available ? 'encrypted retention' : null, features.narration_available ? 'OpenAI narration' : null].filter(Boolean);
    note.textContent = enabled.length ? `Available: ${enabled.join(' and ')}.` : 'Optional retention and narration are not configured on this deployment.';
  } catch (error) { note.textContent = error.message; }
}

async function checkSession() {
  const response = await fetch('/api/auth/me');
  if (response.ok) setSignedIn(await response.json());
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  authStatus.textContent = 'Signing in…';
  const formData = new FormData(loginForm);
  try {
    const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(formData)) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Sign in failed.');
    setSignedIn(data);
  } catch (error) { authStatus.textContent = error.message; }
});

document.querySelector('#logout-button').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.reload();
});

checkSession();

const fileInput = document.querySelector('#photo');
const verificationInput = document.querySelector('#verification-photo');
const matchButton = document.querySelector('#match-button');
const matchStatus = document.querySelector('#match-status');
const dropZone = document.querySelector('#drop-zone');
const verificationZone = document.querySelector('#verification-zone');
const processingConsent = document.querySelector('#processing-consent');
const retentionConsent = document.querySelector('#retention-consent');
const narrationConsent = document.querySelector('#narration-consent');
const luckSpiral = document.querySelector('#luck-spiral');

function updateMatchButton() {
  matchButton.disabled = !fileInput.files?.[0] || !verificationInput.files?.[0] || !processingConsent.checked;
}

fileInput.addEventListener('change', () => {
  const file = fileInput.files?.[0];
  verificationZone.classList.toggle('hidden', !file);
  updateMatchButton();
  if (file) {
    document.querySelector('#drop-zone strong').textContent = file.name;
    matchStatus.textContent = 'Now add a second photo of the same person in different lighting.';
  }
});
verificationInput.addEventListener('change', () => {
  const file = verificationInput.files?.[0];
  updateMatchButton();
  if (file) document.querySelector('#verification-zone strong').textContent = file.name;
});
processingConsent.addEventListener('change', updateMatchButton);
dropZone.addEventListener('dragover', (event) => {
  event.preventDefault();
  dropZone.classList.add('dragging');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragging'));
dropZone.addEventListener('drop', (event) => {
  event.preventDefault();
  dropZone.classList.remove('dragging');
  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    fileInput.dispatchEvent(new Event('change'));
  }
});
matchButton.addEventListener('click', async () => {
  const file = fileInput.files?.[0];
  const verificationFile = verificationInput.files?.[0];
  if (!file || !verificationFile) return;
  matchButton.disabled = true;
  luckSpiral.classList.remove('hidden');
  matchStatus.textContent = 'Checking whether the two photos agree…';
  try {
    const checkResponse = await fetch('/api/self-similarity', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-First-Image-Type': file.type,
        'X-Second-Image-Type': verificationFile.type,
        'X-Second-Image-Offset': String(file.size),
      },
      body: new Blob([file, verificationFile]),
    });
    const check = await checkResponse.json();
    if (!checkResponse.ok) throw new Error(check.detail || 'Consistency check is unavailable.');
    if (!check.passed) {
      matchStatus.textContent = `Consistency ${check.similarity} is below ${check.threshold}. Try clearer photos or recalibrate the configured provider.`;
      return;
    }
    matchStatus.textContent = `Consistency ${check.similarity} passed. Finding your double…`;
    const response = await fetch('/api/match', {
      method: 'POST',
      headers: {
        'Content-Type': file.type,
        'X-Retention-Consent': String(retentionConsent.checked),
        'X-Narration-Consent': String(narrationConsent.checked),
      },
      body: file,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Matching is unavailable.');
    const matches = data.matches;
    const resultCards = matches.map((person, i) => `<article class="result-card"><b>#${i + 1} ${escapeHtml(person.name)}</b><small>relative lookalike ranking</small>${wikipediaLink(person.wikipedia_url)}</article>`).join('');
    const easterEgg = matches.some(isBenAffleckMatch) ? '<p class="result-message easter-egg">All your Ben Affleck are belong to us.</p>' : '';
    const narration = data.narration ? `<p class="result-message narration">${escapeHtml(data.narration)}</p>` : '';
    document.querySelector('#match-results').innerHTML = `${resultCards}<p class="result-message">Same face. Different tax bracket.</p>${narration}${easterEgg}<button class="small-action faceoff-cta" type="button">PLAY FACE OFF &rarr;</button>`;
    document.querySelector('.faceoff-cta').addEventListener('click', () => activateView('rank'));
    matchStatus.textContent = 'The jury has spoken.';
    rainConfetti();
  } catch (error) {
    matchStatus.textContent = error.message;
  } finally {
    luckSpiral.classList.add('hidden');
    fileInput.value = '';
    verificationInput.value = '';
    verificationZone.classList.add('hidden');
    document.querySelector('#drop-zone strong').textContent = 'Take or choose your first selfie';
    document.querySelector('#verification-zone strong').textContent = 'Take or choose a second selfie';
    processingConsent.checked = false;
    retentionConsent.checked = false;
    narrationConsent.checked = false;
    updateMatchButton();
  }
});

document.querySelector('#withdraw-consent').addEventListener('click', async () => {
  const note = document.querySelector('#feature-note');
  try {
    const response = await fetch('/api/me/consented-uploads', { method: 'DELETE' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Deletion failed.');
    note.textContent = `${data.deleted} retained upload(s) deleted.`;
  } catch (error) { note.textContent = error.message; }
});

function rainConfetti() {
  const layer = document.querySelector('#confetti-layer');
  const colors = ['#d9ef72', '#ff8f80', '#1c2523', '#708b3c', '#f3c969'];
  for (let index = 0; index < 70; index += 1) {
    const piece = document.createElement('i');
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.background = colors[index % colors.length];
    piece.style.animationDelay = `${Math.random() * 0.7}s`;
    piece.style.animationDuration = `${1.8 + Math.random() * 1.6}s`;
    piece.style.transform = `rotate(${Math.random() * 360}deg)`;
    layer.appendChild(piece);
    setTimeout(() => piece.remove(), 3800);
  }
}

async function loadRankings() {
  const status = document.querySelector('#rank-status');
  const nextDuel = document.querySelector('#next-duel');
  try {
    const response = await fetch('/api/rankings?limit=20');
    if (!response.ok) throw new Error('The licensed gallery is not loaded yet.');
    const rows = await response.json();
    document.querySelector('#rankings').innerHTML = rows.map((row, i) => `<li><span>${String(i + 1).padStart(2, '0')} &nbsp; ${escapeHtml(row.name)}</span><span class="score">${row.elo} ELO</span></li>`).join('');
    nextDuel.disabled = rows.length < 2;
    status.textContent = rows.length >= 2 ? 'Community taste, rendered as math.' : 'The reference gallery needs at least two people before Face Off can begin.';
    if (rows.length >= 2) await loadDuel();
  } catch (error) {
    nextDuel.disabled = true;
    status.textContent = error.message;
  }
}

document.querySelector('#next-duel').addEventListener('click', loadDuel);
async function loadDuel() {
  const card = document.querySelector('#duel-card');
  const status = document.querySelector('#rank-status');
  try {
    const response = await fetch('/api/duel');
    const duel = await response.json();
    if (!response.ok) throw new Error(duel.detail || 'No duel available.');
    card.innerHTML = `<button class="duel-choice" aria-label="Vote for ${escapeHtml(duel.left.name)}" data-id="${escapeHtml(duel.left.id)}"><div class="duel-placeholder"><span>✦</span><b>${escapeHtml(duel.left.name)}</b><small>VOTE FOR ${escapeHtml(duel.left.name)}</small></div></button><div class="vs">VS</div><button class="duel-choice" aria-label="Vote for ${escapeHtml(duel.right.name)}" data-id="${escapeHtml(duel.right.id)}"><div class="duel-placeholder"><span>✦</span><b>${escapeHtml(duel.right.name)}</b><small>VOTE FOR ${escapeHtml(duel.right.name)}</small></div></button>`;
    document.querySelectorAll('.duel-choice').forEach((button) => button.addEventListener('click', () => castVote(duel.id, button.dataset.id)));
    status.textContent = 'Choose the hotter one. Elo will sort itself out.';
  } catch (error) { status.textContent = error.message; }
}

async function castVote(duelId, winnerId) {
  const status = document.querySelector('#rank-status');
  try {
    const response = await fetch(`/api/duel/${encodeURIComponent(duelId)}/vote?winner_id=${encodeURIComponent(winnerId)}`, { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Vote failed.');
    status.textContent = `Vote locked in. Winner: ${result.winner_elo} Elo.`;
    await loadRankings();
  } catch (error) { status.textContent = error.message; }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

function normalizedIdentity(value) {
  return String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function isBenAffleckMatch(person) {
  return normalizedIdentity(person?.name) === 'ben affleck' || normalizedIdentity(person?.id) === 'ben affleck';
}

function wikipediaLink(value) {
  if (!value) return '';
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== 'https:' || !(host === 'wikipedia.org' || host.endsWith('.wikipedia.org'))) return '';
    return `<a class="wiki-link" href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">Open Wikipedia profile ↗</a>`;
  } catch { return ''; }
}
