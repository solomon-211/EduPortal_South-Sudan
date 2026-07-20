/* org-dashboard.js — EduPortal South Sudan */
(function () {
  'use strict';

  function token() { return localStorage.getItem('token') || ''; }
  function authHeaders() {
    return { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` };
  }
  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function fmtDate(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }
  function setMsg(id, text, ok) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'status-message ' + (ok ? 'is-success' : 'is-error');
  }

  // ── Load org profile & announcements ──────────────────────────────────────

  async function loadDashboard() {
    try {
      const res  = await fetch('/api/my-org', { headers: authHeaders() });
      const data = await res.json();

      if (!res.ok) {
        const notice = document.getElementById('org-dash-notice');
        if (notice) { notice.textContent = data.error || 'Access denied.'; notice.classList.remove('hidden'); }
        return;
      }

      const org  = data.org;
      const anns = data.announcements || [];

      // Title
      const title = document.getElementById('org-dash-title');
      if (title && org) title.textContent = org.name || 'Your Organisation';

      // Stats
      const total   = anns.length;
      const pending = anns.filter(a => !a.approved).length;
      setText('od-ann-count',     total);
      setText('od-pending-count', pending);
      setText('od-org-type',      org ? (org.org_type || '—') : '—');

      // Pre-fill profile form
      if (org) prefillOrgForm(org);

      // Render announcements list
      renderAnnList(anns);

    } catch (e) {
      console.error('org-dashboard load error', e);
    }
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function prefillOrgForm(org) {
    const form = document.getElementById('od-org-form');
    if (!form) return;
    ['name', 'org_type', 'state', 'website', 'email', 'phone', 'description'].forEach(f => {
      const el = form.elements[f];
      if (el && org[f] != null) el.value = org[f];
    });
  }

  function renderAnnList(anns) {
    const el = document.getElementById('od-ann-list');
    if (!el) return;
    if (!anns.length) { el.innerHTML = '<p class="empty-text">No announcements yet.</p>'; return; }

    const PRIORITY_COLOR = { urgent: '#c0392b', high: '#b86000', normal: '' };

    el.innerHTML = anns.map(a => {
      const color  = PRIORITY_COLOR[a.priority] || '';
      const badge  = a.approved
        ? '<span class="status-badge status-open">Live</span>'
        : '<span class="status-badge status-limited">Pending</span>';
      const priTag = a.priority !== 'normal'
        ? `<span class="tag" style="background:rgba(0,0,0,0.06);color:${color}">${escHtml(a.priority)}</span>`
        : '';
      return `
        <div class="admin-approve-card" style="margin-bottom:.75rem">
          <div style="flex:1;min-width:0">
            <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.3rem">
              ${badge} ${priTag}
              <span class="u-text-muted-xs">${fmtDate(a.created_at)}</span>
            </div>
            <h3 style="margin:0 0 .25rem;font-size:.98rem">${escHtml(a.title)}</h3>
            <p style="margin:0;font-size:.84rem;color:#888">${escHtml(a.body).slice(0, 160)}${a.body.length > 160 ? '…' : ''}</p>
            <div style="margin-top:.4rem;display:flex;gap:.5rem;flex-wrap:wrap">
              <span class="tag tag-muted">${escHtml(a.audience || 'all')}</span>
              ${a.state ? `<span class="tag tag-muted">${escHtml(a.state)}</span>` : '<span class="tag tag-muted">National</span>'}
              ${a.expires_at ? `<span class="deadline-badge">Expires ${fmtDate(a.expires_at)}</span>` : ''}
              ${a.attachment_path ? `<a href="${escHtml(a.attachment_path)}" target="_blank" rel="noopener" class="card-link" style="font-size:.8rem">📎 Attachment</a>` : ''}
            </div>
          </div>
          <div class="admin-approve-actions">
            <button class="card-button btn-reject u-inline-btn-sm" data-id="${a.id}" onclick="window._odDelete(${a.id})">Delete</button>
          </div>
        </div>`;
    }).join('');
  }

  // ── Delete announcement ───────────────────────────────────────────────────

  window._odDelete = async function (id) {
    if (!confirm('Delete this announcement?')) return;
    const res = await fetch(`/api/announcements/${id}`, {
      method: 'DELETE', headers: authHeaders(),
    });
    if (res.ok) loadDashboard();
    else {
      const d = await res.json();
      alert(d.error || 'Delete failed.');
    }
  };

  // ── Save org profile ──────────────────────────────────────────────────────

  async function handleOrgSave(e) {
    e.preventDefault();
    const form = e.target;
    const btn  = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    const fd = new FormData(form);
    const payload = {};
    for (const [k, v] of fd.entries()) if (v) payload[k] = v;

    // org_publisher can only update their own org via admin endpoint if admin,
    // otherwise we use a dedicated self-service endpoint
    const res  = await fetch('/api/my-org/profile', {
      method:  'PUT',
      headers: authHeaders(),
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    setMsg('od-org-msg', data.message || data.error, res.ok);
    btn.disabled = false;
  }

  // ── Post announcement ─────────────────────────────────────────────────────

  async function handleAnnPost(e) {
    e.preventDefault();
    const form = e.target;
    const btn  = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    const fd = new FormData(form);
    const payload = {
      title:          fd.get('title'),
      body:           fd.get('body'),
      audience:       fd.get('audience'),
      priority:       fd.get('priority'),
      state:          fd.get('state') || undefined,
      expires_at:     fd.get('expires_at') || undefined,
      attachment_url: fd.get('attachment_url') || undefined,
    };
    const attachFile = fd.get('attachment_file');
    const res  = await fetch('/api/announcements', {
      method:  'POST',
      headers: authHeaders(),
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok && attachFile && attachFile.size > 0) {
      const fileFd = new FormData();
      fileFd.append('file', attachFile);
      await fetch(`/api/announcements/${data.id}/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
        body: fileFd,
      }).catch(() => {});
    }
    setMsg('od-ann-msg', data.message || data.error, res.ok);
    if (res.ok) { form.reset(); loadDashboard(); }
    btn.disabled = false;
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    const stored = localStorage.getItem('user');
    if (!stored) {
      window.location.href = '/login';
      return;
    }
    try {
      const user = JSON.parse(stored);
      if (!['org_publisher', 'admin'].includes(user.role)) {
        const notice = document.getElementById('org-dash-notice');
        if (notice) { notice.textContent = 'Organisation publisher access required.'; notice.classList.remove('hidden'); }
        return;
      }
    } catch { /* ignore */ }

    loadDashboard();

    const orgForm = document.getElementById('od-org-form');
    if (orgForm) orgForm.addEventListener('submit', handleOrgSave);

    const annForm = document.getElementById('od-ann-form');
    if (annForm) annForm.addEventListener('submit', handleAnnPost);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
