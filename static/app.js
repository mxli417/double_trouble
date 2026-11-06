const navItems = document.querySelectorAll('.nav-item');

function notice(message, type = 'info', title = '') {
  if (window.showNotification) window.showNotification({ message, type, title });
}

function activateView(view) {
  navItems.forEach((item) => item.classList.toggle('active', item.dataset.view === view));
  ['match', 'rank', 'self'].forEach((name) => {
    document.querySelector(`#${name}-view`).classList.toggle('hidden', name !== view);
  });
  if (view === 'rank') loadRankings();
}

navItems.forEach((item) => item.addEventListener('click', () => activateView(item.dataset.view)));

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
    retentionConsent.disabled = !features.retention_available;
    hotOrNotConsent.disabled = !features.hot_or_not_available;
    narrationConsent.disabled = !features.narration_available;
    document.querySelector('#retention-days').textContent = features.retained_upload_days;
    const enabled = [
      features.retention_available ? 'encrypted retention and Hot or Not participation' : null,
      features.narration_available ? 'OpenAI narration' : null,
    ].filter(Boolean);
    note.textContent = enabled.length ? `Available: ${enabled.join(' and ')}.` : 'Optional retention, Hot or Not participation, and narration are not configured.';
  } catch (error) {
    note.textContent = error.message;
    notice(error.message, 'error', 'Feature check failed');
  }
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
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(formData)),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Sign in failed.');
    setSignedIn(data);
    notice('You are signed in and ready to play.', 'success', 'Welcome back');
  } catch (error) {
    authStatus.textContent = error.message;
    notice(error.message, 'error', 'Sign in failed');
  }
});

document.querySelector('#logout-button').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.reload();
});

checkSession();

const fileInput = document.querySelector('#photo');
const matchButton = document.querySelector('#match-button');
const matchStatus = document.querySelector('#match-status');
const dropZone = document.querySelector('#drop-zone');
const processingConsent = document.querySelector('#processing-consent');
const retentionConsent = document.querySelector('#retention-consent');
const hotOrNotConsent = document.querySelector('#hot-or-not-consent');
const hotOrNotName = document.querySelector('#hot-or-not-name');
const hotOrNotNameRow = document.querySelector('#hot-or-not-name-row');
const narrationConsent = document.querySelector('#narration-consent');
const luckSpiral = document.querySelector('#luck-spiral');
let activePreviewUrl = null;

function updateMatchButton() {
  const validNickname = !hotOrNotConsent.checked || hotOrNotName.value.trim().length >= 2;
  matchButton.disabled = !fileInput.files?.[0] || !processingConsent.checked || !validNickname;
}

fileInput.addEventListener('change', () => {
  const file = fileInput.files?.[0];
  updateMatchButton();
  if (file) {
    document.querySelector('#drop-zone strong').textContent = file.name;
    matchStatus.textContent = 'Your photo is ready. Choose only the optional uses you want.';
  }
});

processingConsent.addEventListener('change', updateMatchButton);
retentionConsent.addEventListener('change', () => {
  if (!retentionConsent.checked) {
    hotOrNotConsent.checked = false;
    hotOrNotNameRow.classList.add('hidden');
  }
  updateMatchButton();
});
hotOrNotConsent.addEventListener('change', () => {
  if (hotOrNotConsent.checked) retentionConsent.checked = true;
  hotOrNotNameRow.classList.toggle('hidden', !hotOrNotConsent.checked);
  if (hotOrNotConsent.checked) hotOrNotName.focus();
  updateMatchButton();
});
hotOrNotName.addEventListener('input', updateMatchButton);

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
  if (!file) return;
  matchButton.disabled = true;
  luckSpiral.classList.remove('hidden');
  matchStatus.textContent = 'Finding your closest gallery doubles…';
  if (activePreviewUrl) URL.revokeObjectURL(activePreviewUrl);
  activePreviewUrl = URL.createObjectURL(file);
  try {
    const response = await fetch('/api/match', {
      method: 'POST',
      headers: {
        'Content-Type': file.type,
        'X-Retention-Consent': String(retentionConsent.checked),
        'X-Hot-Or-Not-Consent': String(hotOrNotConsent.checked),
        'X-Hot-Or-Not-Name': hotOrNotConsent.checked ? encodeURIComponent(hotOrNotName.value.trim()) : '',
        'X-Narration-Consent': String(narrationConsent.checked),
      },
      body: file,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Matching is unavailable.');
    const matches = data.matches;
    const yourCard = `<article class="result-card query-card"><img src="${escapeHtml(activePreviewUrl)}" alt="Your uploaded portrait"><b>You</b><small>request upload</small></article>`;
    const resultCards = matches.map((person, index) => {
      const portrait = safeImage(person.image_url, `${person.name} portrait`);
      return `<article class="result-card">${portrait}<b>#${index + 1} ${escapeHtml(person.name)}</b><small>${Math.round(person.similarity * 100)}% relative similarity</small>${wikipediaLink(person.wikipedia_url)}</article>`;
    }).join('');
    const easterEgg = matches.some(isBenAffleckMatch) ? '<p class="result-message easter-egg">All your Ben Affleck are belong to us.</p>' : '';
    const narration = data.narration ? `<p class="result-message narration">${escapeHtml(data.narration)}</p>` : '';
    document.querySelector('#match-results').innerHTML = `${yourCard}${resultCards}<p class="result-message">Same face. Different tax bracket.</p>${narration}${easterEgg}<button class="small-action hot-or-not-cta" type="button">PLAY HOT OR NOT &rarr;</button>`;
    document.querySelector('.hot-or-not-cta').addEventListener('click', () => activateView('rank'));
    matchStatus.textContent = 'The jury has spoken.';
    notice(
      hotOrNotConsent.checked ? 'Match complete. Your consented portrait joined Hot or Not.' : 'Your closest gallery doubles are ready.',
      'success',
      'Match complete',
    );
    rainConfetti();
  } catch (error) {
    matchStatus.textContent = error.message;
    notice(error.message, 'error', 'Match failed');
  } finally {
    luckSpiral.classList.add('hidden');
    fileInput.value = '';
    document.querySelector('#drop-zone strong').textContent = 'Take or choose your selfie';
    processingConsent.checked = false;
    retentionConsent.checked = false;
    hotOrNotConsent.checked = false;
    hotOrNotName.value = '';
    hotOrNotNameRow.classList.add('hidden');
    narrationConsent.checked = false;
    updateMatchButton();
  }
});

document.querySelector('#withdraw-consent').addEventListener('click', async () => {
  if (!window.confirm('Delete every retained upload and remove your portrait from Hot or Not?')) return;
  const note = document.querySelector('#feature-note');
  try {
    const response = await fetch('/api/me/consented-uploads', { method: 'DELETE' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Deletion failed.');
    note.textContent = `${data.deleted} retained upload(s) deleted.`;
    notice('Your retained uploads and Hot or Not portrait were removed.', 'success', 'Consent withdrawn');
  } catch (error) {
    note.textContent = error.message;
    notice(error.message, 'error', 'Deletion failed');
  }
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
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Hot or Not is unavailable.');
    const rows = payload.rankings;
    document.querySelector('#rankings').innerHTML = rows.map((row) => `<li class="${row.is_owner ? 'own-ranking' : ''}"><span class="rank-number">RANK #${String(row.rank).padStart(2, '0')}</span><span class="ranking-name">${escapeHtml(row.name)}${row.is_owner ? ' · YOU' : ''}</span><span class="score">${row.elo} ELO</span></li>`).join('');
    const humanPlayers = payload.human_players || [];
    document.querySelector('#human-player-count').textContent = humanPlayers.length;
    document.querySelector('#human-players').innerHTML = humanPlayers.length
      ? humanPlayers.map((player) => `<article class="human-player-card ${player.is_owner ? 'is-you' : ''}">${safeImage(player.image_url, `${player.name} portrait`)}<div><span>HUMAN PLAYER${player.is_owner ? ' · YOU' : ''}</span><b>${escapeHtml(player.name)}</b><small>RANK #${player.rank} · ${player.elo} ELO</small></div></article>`).join('')
      : '<div class="human-player-empty">No human player has joined yet.</div>';
    const myRank = document.querySelector('#my-rank');
    myRank.classList.toggle('hidden', !payload.my_candidate);
    if (payload.my_candidate) {
      myRank.innerHTML = `<span>YOUR CURRENT RANK</span><strong>#${payload.my_candidate.rank}</strong><b>${escapeHtml(payload.my_candidate.name)}</b><small>${payload.my_candidate.elo} ELO · ${payload.my_candidate.votes} votes</small>`;
    }
    nextDuel.disabled = rows.length < 2;
    status.textContent = rows.length >= 2 ? 'Community taste, rendered as math.' : 'At least two consented or cleared portraits are needed.';
    if (rows.length >= 2) await loadDuel();
  } catch (error) {
    nextDuel.disabled = true;
    status.textContent = error.message;
    notice(error.message, 'error', 'Hot or Not unavailable');
  }
}

document.querySelector('#next-duel').addEventListener('click', loadDuel);

async function loadDuel() {
  const card = document.querySelector('#duel-card');
  const status = document.querySelector('#rank-status');
  try {
    const response = await fetch('/api/duel');
    const duel = await response.json();
    if (!response.ok) throw new Error(duel.detail || 'No matchup available.');
    card.innerHTML = `${duelChoice(duel.left)}<div class="vs">VS</div>${duelChoice(duel.right)}`;
    document.querySelectorAll('.duel-choice').forEach((button) => button.addEventListener('click', () => castVote(duel.id, button.dataset.id)));
    status.textContent = 'Choose your favorite. Elo will sort itself out.';
  } catch (error) {
    status.textContent = error.message;
    notice(error.message, 'error', 'Could not load matchup');
  }
}

function duelChoice(candidate) {
  return `<button class="duel-choice" aria-label="Vote for ${escapeHtml(candidate.name)}" data-id="${escapeHtml(candidate.id)}"><div class="duel-placeholder">${safeImage(candidate.image_url, `${candidate.name} portrait`)}<b>${escapeHtml(candidate.name)}</b><small>VOTE FOR ${escapeHtml(candidate.name)}</small></div></button>`;
}

async function castVote(duelId, winnerId) {
  const status = document.querySelector('#rank-status');
  const choices = [...document.querySelectorAll('.duel-choice')];
  const winner = choices.find((choice) => choice.dataset.id === winnerId);
  const loser = choices.find((choice) => choice.dataset.id !== winnerId);
  choices.forEach((choice) => { choice.disabled = true; });
  try {
    const response = await fetch(`/api/duel/${encodeURIComponent(duelId)}/vote?winner_id=${encodeURIComponent(winnerId)}`, { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Vote failed.');
    status.textContent = `Vote locked in. Winner: ${result.winner_elo} Elo.`;
    winner?.classList.add('vote-winner');
    loser?.classList.add('vote-loser');
    notice('Your Hot or Not vote was counted.', 'success', 'Vote locked in');
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await loadRankings();
  } catch (error) {
    choices.forEach((choice) => { choice.disabled = false; });
    status.textContent = error.message;
    notice(error.message, 'error', 'Vote failed');
  }
}

const selfPhoto = document.querySelector('#self-photo');
const selfVerificationPhoto = document.querySelector('#self-verification-photo');
const selfConsent = document.querySelector('#self-processing-consent');
const selfButton = document.querySelector('#self-check-button');

function updateSelfButton() {
  selfButton.disabled = !selfPhoto.files?.[0] || !selfVerificationPhoto.files?.[0] || !selfConsent.checked;
}

selfPhoto.addEventListener('change', () => {
  document.querySelector('#self-photo-label').textContent = selfPhoto.files?.[0]?.name || 'Choose the first photo';
  updateSelfButton();
});
selfVerificationPhoto.addEventListener('change', () => {
  document.querySelector('#self-verification-label').textContent = selfVerificationPhoto.files?.[0]?.name || 'Choose the comparison photo';
  updateSelfButton();
});
selfConsent.addEventListener('change', updateSelfButton);
selfButton.addEventListener('click', async () => {
  const first = selfPhoto.files?.[0];
  const second = selfVerificationPhoto.files?.[0];
  if (!first || !second) return;
  selfButton.disabled = true;
  const status = document.querySelector('#self-status');
  const result = document.querySelector('#self-result');
  status.textContent = 'Comparing both request-only embeddings…';
  try {
    const response = await fetch('/api/self-similarity', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-First-Image-Type': first.type,
        'X-Second-Image-Type': second.type,
        'X-Second-Image-Offset': String(first.size),
      },
      body: new Blob([first, second]),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Self-similarity check is unavailable.');
    result.classList.remove('hidden');
    result.innerHTML = `<b>${data.passed ? 'PASS' : 'REVIEW'}</b><span>Similarity ${data.similarity}; configured threshold ${data.threshold}.</span>`;
    status.textContent = data.passed ? 'The model recognizes both photos as sufficiently similar.' : 'The score is below the configured threshold. Try clearer lighting or review calibration.';
    notice(status.textContent, data.passed ? 'success' : 'warning', 'Self-check complete');
  } catch (error) {
    status.textContent = error.message;
    result.classList.add('hidden');
    notice(error.message, 'error', 'Self-check failed');
  } finally {
    selfButton.disabled = false;
  }
});

function safeImage(value, alt) {
  if (typeof value !== 'string' || !value.startsWith('/api/')) {
    return '<div class="portrait-missing" aria-label="Portrait unavailable">PORTRAIT UNAVAILABLE</div>';
  }
  return `<img src="${escapeHtml(value)}" alt="${escapeHtml(alt)}">`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
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
  } catch {
    return '';
  }
}
