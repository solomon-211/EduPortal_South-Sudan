/* organizations.js — EduPortal South Sudan */
(function () {
  'use strict';

  const escHtml = EP.esc;
  const fmtDate = EP.fmtDate;

  const ORG_ICON = EP.ORG_TYPE_ICON;

  // Render org cards

  function renderOrg(org) {
    const icon = ORG_ICON[org.org_type] || 'building-2';
    const state = org.state ? `<span class="tag tag-muted">${escHtml(org.state)}</span>` : '<span class="tag tag-muted">National</span>';
    const website = org.website
      ? `<a href="${escHtml(org.website)}" target="_blank" rel="noopener" class="card-link"><i data-lucide="external-link" width="14" height="14"></i> Visit website</a>`
      : '';
    return `
      <div class="result-card" data-org-id="${org.id}">
        <div class="result-card-top">
          <i data-lucide="${icon}" width="28" height="28"></i>
          ${state}
          <span class="tag status-open">Verified</span>
        </div>
        <p class="result-card-title">${escHtml(org.name)}</p>
        <p class="result-card-meta">${escHtml(org.org_type)}</p>
        ${org.description ? `<p class="result-card-preview">${escHtml(org.description)}</p>` : ''}
        <div class="result-card-footer">
          <div class="u-flex-wrap">
            ${org.email ? `<span class="u-text-muted-xs">${escHtml(org.email)}</span>` : ''}
          </div>
          ${website}
        </div>
        <button type="button" class="card-link org-posts-toggle" data-org-id="${org.id}">
          <i data-lucide="megaphone" width="14" height="14"></i> See what they've posted
        </button>
        <div class="org-posts-panel hidden" data-org-posts="${org.id}"></div>
      </div>`;
  }

  function renderOrgPosts(items) {
    if (!items.length) return '<p class="empty-text u-text-muted-xs">No announcements posted yet.</p>';
    return items.map(a => `
      <div class="org-post-item">
        <p class="org-post-title">${escHtml(a.title)}</p>
        <p class="org-post-preview">${escHtml(a.body)}</p>
        <p class="u-text-muted-xs">${escHtml(a.audience)} &middot; ${fmtDate(a.created_at)}</p>
      </div>`).join('');
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
      el.innerHTML = `<div class="cards-grid results-grid">${items.map(renderOrg).join('')}</div>`;
      el.querySelectorAll('.org-posts-toggle').forEach(btn => {
        btn.addEventListener('click', async () => {
          const id = btn.dataset.orgId;
          const panel = el.querySelector(`[data-org-posts="${id}"]`);
          if (!panel) return;
          const isOpen = !panel.classList.contains('hidden');
          if (isOpen) { panel.classList.add('hidden'); btn.classList.remove('is-active'); return; }
          panel.classList.remove('hidden');
          btn.classList.add('is-active');
          if (panel.dataset.loaded) return;
          panel.innerHTML = '<p class="loading-text">Loading…</p>';
          try {
            const res = await fetch(`/api/organizations/${id}`);
            const data = await res.json();
            panel.innerHTML = renderOrgPosts(data.announcements || []);
            panel.dataset.loaded = '1';
          } catch {
            panel.innerHTML = '<p class="empty-text">Failed to load announcements.</p>';
          }
        });
      });
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    } catch {
      el.innerHTML = '<p class="empty-text">Failed to load organisations.</p>';
    }
  }

  // Join request form

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

  // Init

  function init() {
    const filterForm = document.getElementById('orgs-filter-form');
    if (filterForm) {
      const applyFilters = () => {
        const p = new URLSearchParams();
        for (const [k, v] of new FormData(filterForm).entries()) if (v) p.set(k, v);
        loadOrgs(p.toString());
      };
      filterForm.addEventListener('submit', e => {
        e.preventDefault();
        applyFilters();
      });
      // A dropdown that does nothing until "Search" is clicked reads as
      // broken — apply it the moment it changes.
      filterForm.querySelectorAll('select').forEach(sel => sel.addEventListener('change', applyFilters));
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
