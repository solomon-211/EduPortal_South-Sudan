/* org-dashboard.js — EduPortal South Sudan */
(function () {
  'use strict';

  const authHeaders = EP.authHeaders;
  const escHtml = EP.esc;
  const fmtDate = EP.fmtDate;
  function setMsg(id, text, ok) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'status-message ' + (ok ? 'is-success' : 'is-error');
  }

  // This file uses a plain authenticated fetch rather than main.js's api()
  // wrapper (a different file/closure, no 401-retry) — thrown Error carries
  // the server's message, matching what EP.submitEditablePost expects.
  async function request(url, opts) {
    const res  = await fetch(url, { method: opts.method, headers: authHeaders(), body: opts.body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }

  // Load org profile & announcements

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
      const notice = document.getElementById('org-dash-notice');
      if (notice) { notice.textContent = 'Could not load your organisation dashboard. Check your connection and reload.'; notice.classList.remove('hidden'); }
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

  let currentAnns = [];

  function renderAnnList(anns) {
    currentAnns = anns;
    const el = document.getElementById('od-ann-list');
    if (!el) return;
    if (!anns.length) { el.innerHTML = '<p class="empty-text">No announcements yet.</p>'; return; }

    const PRIORITY_CLASS = { urgent: 'tag--priority-urgent', high: 'tag--priority-high', normal: '' };

    el.innerHTML = anns.map(a => {
      const badge  = a.approved
        ? '<span class="status-badge status-open">Live</span>'
        : '<span class="status-badge status-limited">Pending</span>';
      const priTag = a.priority !== 'normal'
        ? `<span class="tag ${PRIORITY_CLASS[a.priority] || ''}">${escHtml(a.priority)}</span>`
        : '';
      const rejectNote = (!a.approved && a.rejection_reason)
        ? `<p class="u-text-danger u-list-copy-xs">Feedback: ${escHtml(a.rejection_reason)}</p>` : '';
      return `
        <div class="admin-approve-card">
          <div class="u-card-flex-main">
            <div class="od-ann-item__badges">
              ${badge} ${priTag}
              <span class="u-text-muted-xs">${fmtDate(a.created_at)}</span>
            </div>
            <h3>${escHtml(a.title)}</h3>
            <p>${escHtml(a.body).slice(0, 160)}${a.body.length > 160 ? '…' : ''}</p>
            <div class="od-ann-item__tags">
              <span class="tag tag-muted">${escHtml(a.audience || 'all')}</span>
              ${a.state ? `<span class="tag tag-muted">${escHtml(a.state)}</span>` : '<span class="tag tag-muted">National</span>'}
              ${a.expires_at ? `<span class="deadline-badge">Expires ${fmtDate(a.expires_at)}</span>` : ''}
              ${a.attachment_path ? `<a href="${escHtml(a.attachment_path)}" target="_blank" rel="noopener" class="card-link od-ann-item__attach"><i data-lucide="paperclip" width="13" height="13"></i> Attachment</a>` : ''}
            </div>
            ${rejectNote}
          </div>
          <div class="admin-approve-actions">
            <button class="card-button u-inline-btn-sm" data-id="${a.id}" onclick="window._odEdit(${a.id})">Edit</button>
            <button class="card-button btn-reject u-inline-btn-sm" data-id="${a.id}" onclick="window._odDelete(${a.id})">Delete</button>
          </div>
        </div>`;
    }).join('');
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
  }

  // Edit announcement — populates the post form and switches it into "save
  // edits" mode, same pattern as the school/NGO dashboards.

  window._odEdit = function (id) {
    const a = currentAnns.find(x => x.id === id);
    const form = document.getElementById('od-ann-form');
    if (!a || !form) return;
    EP.populateFormFields(form, a, ['title', 'body', 'audience', 'priority', 'state', 'expires_at', 'attachment_url']);
    form.dataset.editingId = a.id;
    setMsg('od-ann-msg', `Editing "${a.title}" — resubmit to save changes.`, true);
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // Delete announcement

  window._odDelete = async function (id) {
    if (!confirm('Delete this announcement?')) return;
    try {
      await request(`/api/announcements/${id}`, { method: 'DELETE' });
      loadDashboard();
    } catch (err) {
      setMsg('od-ann-msg', err.message || 'Delete failed.', false);
    }
  };

  // Save org profile

  async function handleOrgSave(e) {
    e.preventDefault();
    const form = e.target;
    const btn  = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    const fd = new FormData(form);
    const payload = {};
    for (const [k, v] of fd.entries()) if (v) payload[k] = v;

    try {
      // org_publisher can only update their own org via admin endpoint if admin,
      // otherwise we use a dedicated self-service endpoint
      const data = await request('/api/my-org/profile', { method: 'PUT', body: JSON.stringify(payload) });
      setMsg('od-org-msg', data.message || 'Saved.', true);
      loadDashboard();
    } catch (err) {
      setMsg('od-org-msg', err.message || 'Save failed. Check your connection and try again.', false);
    } finally {
      btn.disabled = false;
    }
  }

  // Post announcement

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
    try {
      await EP.submitEditablePost({
        form,
        editingId: form.dataset.editingId,
        payload,
        createUrl: '/api/announcements',
        idUrl: (id) => `/api/announcements/${id}`,
        fileUploads: [{ file: attachFile, uploadUrl: (id) => `/api/announcements/${id}/upload` }],
        request,
        setMsg: (text, isError) => setMsg('od-ann-msg', text, !isError),
      });
      loadDashboard();
    } catch (err) {
      setMsg('od-ann-msg', err.message || 'Submission failed.', false);
    } finally {
      btn.disabled = false;
    }
  }

  // Init

  function init() {
    const stored = localStorage.getItem('eduportal_user');
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
