import re

path = r'C:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\eduportal\frontend\static\app.js'

with open(path, encoding='utf-8') as f:
    content = f.read()

# Find the function boundaries
start = content.find('  function _renderSchoolEditPanel(shell, school, reqItems, id) {')
if start == -1:
    print('ERROR: function not found'); exit(1)

# Find the closing brace — count braces from the opening {
depth = 0
end = start
for i, ch in enumerate(content[start:], start):
    if ch == '{':
        depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break

print(f'Function found: chars {start}–{end}')

NEW_FUNC = r"""  function _renderSchoolEditPanel(shell, school, reqItems, id) {
    const panel = document.createElement('section');
    panel.className = 'card content-panel school-edit-panel';
    panel.innerHTML = `
      <p class="section-label">MANAGE SCHOOL PROFILE</p>
      <p class="school-edit-note">You are the assigned admin for this school. Changes are saved immediately.</p>

      <form id="edit-school-form">
        <div class="school-edit-grid">
          <label class="field-label">School Name
            <input class="field-input" name="name" value="${esc(school.name)}">
          </label>
          <label class="field-label">State
            <input class="field-input" name="state" value="${esc(school.state)}">
          </label>
          <label class="field-label">County
            <input class="field-input" name="county" value="${esc(school.county)}">
          </label>
          <label class="field-label">Level
            <select class="field-input" name="level">
              <option value="primary" ${school.level==='primary'?'selected':''}>Primary</option>
              <option value="secondary" ${school.level==='secondary'?'selected':''}>Secondary</option>
            </select>
          </label>
          <label class="field-label">Type
            <select class="field-input" name="type">
              <option value="mixed" ${school.type==='mixed'?'selected':''}>Mixed</option>
              <option value="boys" ${school.type==='boys'?'selected':''}>Boys</option>
              <option value="girls" ${school.type==='girls'?'selected':''}>Girls</option>
            </select>
          </label>
          <label class="field-label">Boarding
            <select class="field-input" name="boarding">
              <option value="Day" ${school.boarding==='Day'?'selected':''}>Day</option>
              <option value="Boarding" ${school.boarding==='Boarding'?'selected':''}>Boarding</option>
            </select>
          </label>
          <label class="field-label">Status
            <select class="field-input" name="status">
              <option value="open" ${school.status==='open'?'selected':''}>Open</option>
              <option value="limited" ${school.status==='limited'?'selected':''}>Limited</option>
              <option value="closed" ${school.status==='closed'?'selected':''}>Closed</option>
            </select>
          </label>
          <label class="field-label">Capacity
            <input class="field-input" name="capacity" type="number" value="${esc(school.capacity)}">
          </label>
          <label class="field-label">Enrollment
            <input class="field-input" name="enrollment" type="number" value="${esc(school.enrollment)}">
          </label>
          <label class="field-label">Contact Name
            <input class="field-input" name="contact_name" value="${esc(school.contact_name)}">
          </label>
          <label class="field-label">Phone
            <input class="field-input" name="phone" value="${esc(school.phone)}">
          </label>
          <label class="field-label">Email
            <input class="field-input" name="email" type="email" value="${esc(school.email||'')}">
          </label>
          <label class="field-label">Hours
            <input class="field-input" name="hours" value="${esc(school.hours||'')}">
          </label>
          <label class="field-label">Curriculum
            <input class="field-input" name="curriculum" value="${esc(school.curriculum||'')}">
          </label>
          <label class="field-label">Language
            <input class="field-input" name="language" value="${esc(school.language||'')}">
          </label>
        </div>
        <label class="field-label" style="display:block;margin-bottom:1rem">Description
          <textarea class="field-input" name="description" rows="3">${esc(school.description||'')}</textarea>
        </label>
        <div class="school-edit-actions">
          <button class="card-button" type="submit" style="width:auto;padding:0.65rem 1.4rem;margin-top:0">Save School Info</button>
          <span id="edit-school-msg" class="school-edit-msg"></span>
        </div>
      </form>

      <hr class="school-edit-divider">

      <p class="section-label" style="margin-bottom:0.75rem">ADMISSION REQUIREMENTS</p>
      <div id="req-editor"></div>
      <div class="school-edit-actions" style="margin-top:0.75rem">
        <button id="add-req-btn" class="card-button req-add-btn" style="width:auto;padding:0.55rem 1rem;margin-top:0">+ Add requirement</button>
        <button id="save-reqs-btn" class="card-button" style="width:auto;padding:0.65rem 1.4rem;margin-top:0">Save Requirements</button>
        <span id="edit-reqs-msg" class="school-edit-msg"></span>
      </div>`;

    shell.appendChild(panel);

    // School info form
    const editForm = panel.querySelector('#edit-school-form');
    const editMsg  = panel.querySelector('#edit-school-msg');
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = editForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(editMsg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(editForm));
      ['capacity','enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
      try {
        await api(`/api/schools/${id}`, { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(editMsg, 'Saved \u2713');
      } catch (err) {
        setMsg(editMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    // Requirements editor
    const reqEditor = panel.querySelector('#req-editor');
    const reqsMsg   = panel.querySelector('#edit-reqs-msg');
    let reqs = reqItems.map(r => ({ item_label: r.item_label, is_required: r.is_required, notes: r.notes || '' }));

    function renderReqEditor() {
      reqEditor.innerHTML = reqs.map((r, i) => `
        <div class="req-row" data-idx="${i}">
          <input class="field-input req-label" placeholder="Requirement label" value="${esc(r.item_label)}">
          <input class="field-input req-notes" placeholder="Notes (optional)" value="${esc(r.notes)}">
          <label class="req-required-label">
            <input type="checkbox" class="req-required" ${r.is_required ? 'checked' : ''}> Required
          </label>
          <button class="req-remove-btn req-remove" data-idx="${i}" type="button">&times;</button>
        </div>`).join('');
      reqEditor.querySelectorAll('.req-remove').forEach(btn => {
        btn.addEventListener('click', () => { reqs.splice(Number(btn.dataset.idx), 1); renderReqEditor(); });
      });
    }
    renderReqEditor();

    panel.querySelector('#add-req-btn').addEventListener('click', () => {
      reqs.push({ item_label: '', is_required: true, notes: '' });
      renderReqEditor();
    });

    panel.querySelector('#save-reqs-btn').addEventListener('click', async () => {
      const btn = panel.querySelector('#save-reqs-btn');
      btn.disabled = true;
      setMsg(reqsMsg, 'Saving\u2026');
      const rows = reqEditor.querySelectorAll('.req-row');
      const items = [...rows].map(row => ({
        item_label: row.querySelector('.req-label').value.trim(),
        is_required: row.querySelector('.req-required').checked,
        notes: row.querySelector('.req-notes').value.trim(),
      })).filter(r => r.item_label);
      try {
        await api(`/api/schools/${id}/requirements`, { method: 'PUT', body: JSON.stringify({ items }) });
        setMsg(reqsMsg, 'Saved \u2713');
        reqs = items;
      } catch (err) {
        setMsg(reqsMsg, err.message, true);
      } finally { btn.disabled = false; }
    });
  }"""

new_content = content[:start] + NEW_FUNC + content[end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done. File written successfully.')
