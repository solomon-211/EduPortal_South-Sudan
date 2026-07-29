/* shared-utils.js — EduPortal South Sudan
   Small helpers reused across main.js, sidebar-main.js, announcements.js,
   org-dashboard.js, and organizations.js. These are plain scripts (no
   bundler, no ES modules), so everything hangs off window.EP instead of
   using import/export. Must load before any file that calls EP.*. */
(function () {
  'use strict';

  window.EP = window.EP || {};

  // Icon key per organisation type — used by the org directory cards and
  // the announcement list/modal to show a consistent icon per source.
  EP.ORG_TYPE_ICON = {
    'Ministry of General Education': 'landmark',
    'State Ministry of Education':   'building-2',
    'Examination Body':              'clipboard-check',
    'University':                    'graduation-cap',
    'College':                       'school',
    'School':                        'school',
    'NGO':                           'handshake',
    'Scholarship Provider':          'coins',
  };

  EP.esc = function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };

  EP.token = function token() {
    return localStorage.getItem('eduportal_token') || '';
  };

  EP.authHeaders = function authHeaders() {
    return { 'Content-Type': 'application/json', Authorization: `Bearer ${EP.token()}` };
  };

  // Swaps the access token for a fresh one using the stored refresh token.
  // Shared by main.js's api() wrapper and anything that can't go through
  // that wrapper's automatic 401-retry — the notification bell's raw
  // fetch/EventSource calls and the materials video player each need their
  // own way to recover when the 2-hour access token expires mid-session,
  // or they break permanently until the page is reloaded.
  // Concurrent callers share one in-flight request so a burst of 401s
  // doesn't spend the (single-use) refresh token more than once.
  var _refreshInFlight = null;
  EP.refreshSession = function refreshSession() {
    var refreshToken = localStorage.getItem('eduportal_refresh_token');
    if (!refreshToken) return Promise.resolve(false);
    if (!_refreshInFlight) {
      _refreshInFlight = fetch('/api/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
        .then(function (res) {
          if (!res.ok) return false;
          return res.json().then(function (data) {
            localStorage.setItem('eduportal_token', data.token);
            localStorage.setItem('eduportal_refresh_token', data.refresh_token);
            return true;
          });
        })
        .catch(function () { return false; })
        .finally(function () { _refreshInFlight = null; });
    }
    return _refreshInFlight;
  };

  EP.fmtDate = function fmtDate(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  // Builds a query-string from a filter <form>, dropping empty fields so an
  // untouched filter doesn't show up as e.g. "?subject=" on the request.
  EP.filterParamsFromForm = function filterParamsFromForm(form) {
    var params = new URLSearchParams(form ? new FormData(form) : {});
    Array.from(params.entries()).forEach(function (entry) {
      if (!entry[1]) params.delete(entry[0]);
    });
    return params;
  };

  // Lazily creates (or returns the existing) overlay modal shell — a
  // `.ann-modal-overlay > .ann-modal` with a close button, click-outside,
  // and Escape-key dismissal already wired up. `opts.bodyHtml` is the
  // `.ann-modal`'s full innerHTML (title/body/footer slots are the
  // caller's concern); `opts.onClose` defaults to hiding the overlay.
  EP.createModal = function createModal(opts) {
    var existing = document.getElementById(opts.id);
    if (existing) return existing;
    var modal = document.createElement('div');
    modal.id = opts.id;
    modal.className = 'ann-modal-overlay hidden';
    modal.innerHTML = opts.bodyHtml;
    document.body.appendChild(modal);
    var close = opts.onClose || function () { modal.classList.add('hidden'); };
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    var closeBtn = modal.querySelector('.ann-modal-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    return modal;
  };

  // Copies obj[f] into form's field named f, for each f in fields — the
  // "populate the form" half of every "click Edit to load this row back
  // into the post form" handler (materials, announcements, scholarships).
  EP.populateFormFields = function populateFormFields(form, obj, fields) {
    fields.forEach(function (f) {
      var el = form.querySelector('[name="' + f + '"]');
      if (el && obj[f] != null) el.value = obj[f];
    });
  };

  // Shared tail for every "form doubles as its own edit form via
  // dataset.editingId" flow (materials, announcements, scholarships):
  // branches POST vs. PUT, follows up with any optional file uploads, and
  // resets the form / clears editingId on success. The caller still shapes
  // its own payload and supplies `request`/`setMsg`, since main.js's api()
  // (with 401-retry) and org-dashboard.js's raw fetch+authHeaders are
  // different mechanisms, and each file's message-display helper has a
  // different signature. Throws on failure — callers wrap the call in
  // their own try/catch/finally to re-enable the submit button.
  EP.submitEditablePost = async function submitEditablePost(opts) {
    var isEdit = !!opts.editingId;
    var url = isEdit ? opts.idUrl(opts.editingId) : opts.createUrl;
    opts.setMsg(isEdit ? 'Saving…' : 'Submitting…', false);
    var data = await opts.request(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(opts.payload) });
    var id = isEdit ? opts.editingId : data.id;
    var uploads = opts.fileUploads || [];
    for (var i = 0; i < uploads.length; i++) {
      var f = uploads[i];
      if (f.file && f.file.size > 0) await EP.uploadFile(f.uploadUrl(id), f.fieldName || 'file', f.file);
    }
    opts.setMsg(isEdit ? (opts.editedMsg || 'Updated — submitted for re-review.') : (opts.createdMsg || data.message || 'Submitted.'), false);
    delete opts.form.dataset.editingId;
    opts.form.reset();
    if (opts.onSuccess) opts.onSuccess();
  };

  // POST a single file to an upload endpoint (materials, announcements,
  // scholarship poster/video, logos, etc.) under `fieldName`. Resolves with
  // the parsed JSON response, or rejects with an Error carrying the server's
  // message — callers must not swallow that rejection, or a failed upload
  // silently looks like it succeeded.
  // Retries once via EP.refreshSession() on a 401 (expired access token) —
  // otherwise any upload started after the 2-hour token expiry fails with no
  // recovery, unlike main.js's api() wrapper.
  EP.uploadFile = function uploadFile(url, fieldName, file) {
    function attempt() {
      var fd = new FormData();
      fd.append(fieldName, file);
      return fetch(url, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + EP.token() },
        body: fd,
      });
    }
    return attempt().then(function (res) {
      if (res.status === 401) {
        return EP.refreshSession().then(function (ok) { return ok ? attempt() : res; });
      }
      return res;
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error(data.error || 'File upload failed');
        return data;
      });
    });
  };

  // Splits free-form text into paragraphs on blank lines (or single newlines
  // if the author didn't use any) instead of collapsing it into one run-on
  // block — used for announcement bodies, scholarship descriptions, etc.
  EP.paragraphs = function paragraphs(text) {
    var parts = (text || '').split(/\n\s*\n/).filter(function (p) { return p.trim(); });
    var paras = parts.length > 1 ? parts : (text || '').split(/\n/).filter(function (p) { return p.trim(); });
    if (!paras.length) paras = [text || ''];
    return paras.map(function (p) { return '<p>' + EP.esc(p.trim()) + '</p>'; }).join('');
  };
})();
