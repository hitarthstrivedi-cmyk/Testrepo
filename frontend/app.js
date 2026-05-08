'use strict';

const CATEGORY_ICONS = {
  'AI Strategy': '🎯',
  'AI Automation (No Code)': '⚙️',
  'Agentic AI': '🤖',
  'AI Agents': '🧠',
  'Data Governance': '🛡️',
  'Data Strategy': '📊',
};

let allTrends = [];
let activeFilter = 'all';
let statusInterval = null;

// ── Bootstrap ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadTrends();
  pollStatus();
  statusInterval = setInterval(pollStatus, 15000);
});

// ── Data Loading ───────────────────────────────────────────────────────────

async function loadTrends() {
  showLoading(true);
  try {
    const res = await fetch('/api/trends');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allTrends = await res.json();
    renderTrends();
  } catch (err) {
    showError('Could not load trends', err.message);
  } finally {
    showLoading(false);
  }
}

async function pollStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const status = await res.json();
    updateStatusBadge(status);
  } catch (_) {
    setStatusBadge('error', 'Offline');
  }
}

// ── Render ─────────────────────────────────────────────────────────────────

function renderTrends() {
  const grid = document.getElementById('trendsGrid');
  const empty = document.getElementById('emptyState');
  const errorEl = document.getElementById('errorState');

  if (!allTrends || allTrends.length === 0) {
    grid.style.display = 'none';
    errorEl.style.display = 'none';
    empty.style.display = 'block';
    updateMeta(null);
    return;
  }

  const filtered = activeFilter === 'all'
    ? allTrends
    : allTrends.filter(c => c.category === activeFilter);

  if (filtered.length === 0) {
    grid.style.display = 'none';
    errorEl.style.display = 'none';
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';
  errorEl.style.display = 'none';
  grid.style.display = 'grid';

  const cards = [];
  filtered.forEach((cat, catIdx) => {
    const globalIdx = allTrends.findIndex(c => c.category === cat.category);
    cat.trending_topics.forEach((topic, topicIdx) => {
      cards.push(buildCard(cat, topic, topicIdx + 1, globalIdx));
    });
  });

  grid.innerHTML = cards.join('');
  updateMeta(allTrends);
}

function buildCard(cat, topic, rank, colorIdx) {
  const icon = CATEGORY_ICONS[cat.category] || '📌';
  const themes = (topic.key_themes || [])
    .map(t => `<span class="theme-chip">${esc(t)}</span>`)
    .join('');
  const hashtags = (topic.hashtags_analyzed || [])
    .map(h => `<span class="hashtag-chip">${esc(h)}</span>`)
    .join('');

  const quote = topic.example_post_caption
    ? `<div class="example-quote">${esc(topic.example_post_caption)}</div>`
    : '';

  return `
  <article class="trend-card cat-border-${colorIdx % 6}">
    <div class="card-header">
      <span class="category-tag cat-${colorIdx % 6}">${icon} ${esc(cat.category)}</span>
      <div class="rank-badge">${rank}</div>
    </div>
    <div class="card-body">
      <h3 class="card-title">${esc(topic.title)}</h3>
      <p class="card-summary">${esc(topic.summary)}</p>
      ${themes ? `<div class="themes-row">${themes}</div>` : ''}
      ${topic.engagement_signals ? `
      <div class="engagement-row">
        <span class="engagement-icon">📈</span>
        <span>${esc(topic.engagement_signals)}</span>
      </div>` : ''}
      ${quote}
    </div>
    ${hashtags ? `<div class="card-footer">${hashtags}</div>` : ''}
  </article>`;
}

// ── Filter ─────────────────────────────────────────────────────────────────

function filterCategory(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTrends();
}

// ── Refresh ────────────────────────────────────────────────────────────────

async function triggerRefresh() {
  const btn = document.getElementById('refreshBtn');
  const icon = document.getElementById('refreshIcon');
  btn.disabled = true;
  icon.classList.add('spinning');

  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();
    if (!res.ok && res.status !== 202) {
      showError('Refresh failed', data.detail || 'Unknown error');
      return;
    }

    setStatusBadge('loading', 'Fetching…');

    // Poll until fetch completes (max 5 min)
    let attempts = 0;
    const maxAttempts = 60;
    const pollInterval = setInterval(async () => {
      attempts++;
      const statusRes = await fetch('/api/status').catch(() => null);
      if (!statusRes) return;
      const status = await statusRes.json();
      if (!status.is_fetching || attempts >= maxAttempts) {
        clearInterval(pollInterval);
        await loadTrends();
        setStatusBadge('ok', 'Live');
      }
    }, 5000);
  } catch (err) {
    showError('Refresh failed', err.message);
  } finally {
    btn.disabled = false;
    icon.classList.remove('spinning');
  }
}

// ── Status Badge ───────────────────────────────────────────────────────────

function updateStatusBadge(status) {
  if (status.is_fetching) {
    setStatusBadge('loading', 'Fetching…');
    return;
  }
  if (!status.has_credentials) {
    setStatusBadge('error', 'No Credentials');
    return;
  }
  setStatusBadge('ok', 'Live');
}

function setStatusBadge(state, text) {
  const dot = document.getElementById('statusDot');
  const label = document.getElementById('statusText');
  dot.className = 'status-dot ' + state;
  label.textContent = text;
}

// ── Meta Bar ───────────────────────────────────────────────────────────────

function updateMeta(trends) {
  const lastUpdated = document.getElementById('lastUpdated');
  const countEl = document.getElementById('categoriesCount');

  if (!trends || trends.length === 0) {
    lastUpdated.textContent = 'No data yet';
    countEl.textContent = '0 categories';
    return;
  }

  const timestamps = trends
    .map(c => c.analysis_timestamp)
    .filter(Boolean)
    .sort();
  if (timestamps.length > 0) {
    const d = new Date(timestamps[timestamps.length - 1]);
    lastUpdated.textContent = 'Updated ' + timeAgo(d);
  }

  const total = trends.reduce((n, c) => n + c.trending_topics.length, 0);
  countEl.textContent = `${trends.length} categories · ${total} trending topics`;
}

// ── UI Helpers ─────────────────────────────────────────────────────────────

function showLoading(show) {
  document.getElementById('loadingState').style.display = show ? 'block' : 'none';
}

function showError(title, msg) {
  document.getElementById('trendsGrid').style.display = 'none';
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('errorState').style.display = 'block';
  document.getElementById('errorTitle').textContent = title;
  document.getElementById('errorMessage').textContent = msg;
}

function esc(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function timeAgo(date) {
  const diff = Math.floor((Date.now() - date) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}
