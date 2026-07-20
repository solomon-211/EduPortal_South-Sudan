/* organizations.js — EduPortal South Sudan */
(function () {
  'use strict';

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  const ORG_ICON = {
    'Ministry of General Education': '🏛️',
    'State Ministry of Education':   '🏢',
    'Examination Body':              '📋',
    'University':                    '🎓',
    'College':                       '🏫',
    'School':                        '🏫',
    'NGO':                           '🤝',
    'Scholarship Provider':          '💰',
  };

  // ── Render org cards ──────────────────────────────────────────────────────

  function renderOrg(org) {
    const icon = ORG_ICON[org.org_type] || '🏢';
    const state = org.state ? `<span class="tag tag-muted">${escHtml(org.state)}</span>` : '<span class="tag tag-muted">National</span>';
    const website = org.website
      ? `<a href="${escHtml(org.website)}" target="_blank" rel="noopener" class="card-link">Visit website ↗</a>`
      : '';
    return `
      <div class="result-card">
        <div class="result-card-top">
          <span style="font-size:1.8rem;line-height:1">${icon}</span>
          ${state}
          <span class="tag" style="background:rgba(26,122,60,0.1);color:#1a7a3c">Verified</span>
        </div>
        <p class="result-card-title">${escHtml(org.name)}</p>
        <p class="result-card-meta">${escHtml(org.org_type)}</p>
        ${org.description ? `<p class="result-card-preview">${escHtml(org.description)}</p>` : ''}
        <div class="result-card-footer">
          <div style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">
            ${org.email ? `<span class="u-text-muted-xs">${escHtml(org.email)}</span>` : ''}
          </div>
          ${website}
        </div>
      </div>`;
  }

  async function loadOrgs(qs) {
    const el = document.getElementById('orgs-results');
    if (!el) return;
    el.innerHTML = '<p class="loading-text">Loading…</p>';
    try {
      const res  = await fetch(`/api/organizations?${qs || ''}`);
      const data = await res.json();
      const items = data.items || [];
      if (!items.length) { el.innerHTML = '<p class="empty-text">No organisations found.</p>'; return; }
      el.innerHTML = `<div class="results-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem">${items.map(renderOrg).join('')}</div>`;
    } catch {
      el.innerHTML = '<p class="empty-text">Failed to load organisations.</p>';
    }
  }

  // ── Join request form ─────────────────────────────────────────────────────

  async function handleJoinRequest(e) {
    e.preventDefault();
    const form = e.target;
    const btn  = form.querySelector('button[type="submit"]');
    const msg  = document.getElementById('join-request-msg');
    btn.disabled = true;
    msg.textContent = '';
    msg.className = 'status-message';

    const fd = new FormData(form);
    const payload = {
      name:        fd.get('name'),
      org_type:    fd.get('org_type'),
      state:       fd.get('state') || undefined,
      email:       fd.get('email'),
      phone:       fd.get('phone') || undefined,
      website:     fd.get('website') || undefined,
      description: fd.get('description') || undefined,
    };

    try {
      const res  = await fetch('/api/organizations/request', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      });
      const data = await res.json();
      msg.textContent = data.message || data.error;
      msg.className   = 'status-message ' + (res.ok ? 'is-success' : 'is-error');
      if (res.ok) form.reset();
    } catch {
      msg.textContent = 'Network error. Please try again.';
      msg.className   = 'status-message is-error';
    } finally {
      btn.disabled = false;
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    const filterForm = document.getElementById('orgs-filter-form');
    if (filterForm) {
      filterForm.addEventListener('submit', e => {
        e.preventDefault();
        const p = new URLSearchParams();
        for (const [k, v] of new FormData(filterForm).entries()) if (v) p.set(k, v);
        loadOrgs(p.toString());
      });
    }

    const joinForm = document.getElementById('join-request-form');
    if (joinForm) joinForm.addEventListener('submit', handleJoinRequest);

    loadOrgs('');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
