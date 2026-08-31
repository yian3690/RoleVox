const $ = (q) => document.querySelector(q);
let project = null;
let currentJob = null;
let activeCharacterId = null;
let projectLibrary = [];
let contextProjectId = null;
let projectActionMode = 'rename';
let editingDialogue = null;
let pendingDeleteCharacterId = null;
const imagePreviews = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function apiBlob(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return response.blob();
}

function escapeHtml(value) {
  const node = document.createElement('div');
  node.textContent = String(value ?? '');
  return node.innerHTML;
}

async function checkHealth() {
  try {
    const health = await api('/api/health');
    $('#statusDot').className = `dot ${health.configured ? 'ready' : 'warn'}`;
    $('#systemText').textContent = health.configured
      ? `${health.mode === 'vertex-ai' ? 'VERTEX AI' : health.mode.toUpperCase()} · ${health.location.toUpperCase()} · READY`
      : 'VERTEX AI SETUP REQUIRED';
  } catch {
    $('#statusDot').className = 'dot warn';
    $('#systemText').textContent = 'SYSTEM OFFLINE';
  }
}

async function loadProjects() {
  try {
    projectLibrary = await api('/api/projects');
    renderProjectList();
  } catch (err) {
    $('#projectList').innerHTML = `<div class="project-list-empty">${escapeHtml(err.message)}</div>`;
  }
}

function renderProjectList() {
  const list = $('#projectList');
  if (!projectLibrary.length) {
    list.innerHTML = '<div class="project-list-empty">NO PROJECTS YET</div>';
    return;
  }
  list.innerHTML = projectLibrary.map((item) => {
    const lines = item.characters.reduce((sum, character) => sum + character.dialogues.length, 0);
    return `<button type="button" class="project-list-item ${project?.id === item.id ? 'active' : ''}" data-id="${item.id}" data-short="${escapeHtml(item.title.slice(0, 1).toUpperCase())}">
      <span>${escapeHtml(item.title)}</span><small>${item.characters.length} CHARACTERS · ${lines} LINES</small>
      <em>${escapeHtml(item.scene)}</em></button>`;
  }).join('');
  list.querySelectorAll('.project-list-item').forEach((button) => {
    button.addEventListener('click', () => activateProject(button.dataset.id));
    button.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      contextProjectId = button.dataset.id;
      showProjectContextMenu(event.clientX, event.clientY);
    });
  });
}

function showProjectContextMenu(x, y) {
  const menu = $('#projectContextMenu');
  menu.hidden = false;
  const width = 190;
  menu.style.left = `${Math.min(x, window.innerWidth - width - 12)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - 100)}px`;
}

function hideProjectContextMenu() {
  $('#projectContextMenu').hidden = true;
}

function openProjectAction(mode) {
  const item = projectLibrary.find((entry) => entry.id === contextProjectId);
  if (!item) return;
  projectActionMode = mode;
  hideProjectContextMenu();
  const deleting = mode === 'delete';
  $('#projectActionKicker').textContent = deleting ? 'DELETE PROJECT' : 'PROJECT SETTINGS';
  $('#projectActionTitle').textContent = deleting ? `Delete “${item.title}”?` : 'Rename project';
  $('#projectActionCopy').textContent = deleting
    ? 'Character cards and project images will be moved to the recoverable project-trash folder. Existing voice assets will not be deleted.'
    : 'The new name will appear in both the Project Library and the project workspace.';
  $('#projectRenameLabel').hidden = deleting;
  $('#projectRenameInput').required = !deleting;
  $('#projectRenameInput').value = item.title;
  $('#confirmProjectAction').textContent = deleting ? 'DELETE PROJECT' : 'SAVE NAME';
  $('#confirmProjectAction').className = deleting ? 'danger' : '';
  $('#projectActionError').hidden = true;
  $('#projectActionDialog').showModal();
  if (!deleting) $('#projectRenameInput').select();
}

$('#collapseProjects').addEventListener('click', () => {
  const collapsed = $('.app-shell').classList.toggle('sidebar-collapsed');
  $('#collapseProjects').textContent = collapsed ? '›' : '‹';
  $('#collapseProjects').title = collapsed ? 'Expand project library' : 'Collapse project library';
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('#projectContextMenu')) hideProjectContextMenu();
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hideProjectContextMenu(); });
window.addEventListener('scroll', hideProjectContextMenu, true);
$('#projectContextMenu').addEventListener('click', (event) => {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (action) openProjectAction(action);
});
$('#cancelProjectAction').addEventListener('click', () => $('#projectActionDialog').close());
$('#projectActionForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const error = $('#projectActionError');
  error.hidden = true;
  const button = $('#confirmProjectAction');
  button.disabled = true;
  try {
    if (projectActionMode === 'delete') {
      await api(`/api/projects/${contextProjectId}`, {method: 'DELETE'});
      projectLibrary = projectLibrary.filter((item) => item.id !== contextProjectId);
      if (project?.id === contextProjectId) showNewProject();
      else renderProjectList();
    } else {
      const renamed = await api(`/api/projects/${contextProjectId}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: $('#projectRenameInput').value.trim()})
      });
      const index = projectLibrary.findIndex((item) => item.id === renamed.id);
      if (index >= 0) projectLibrary[index] = renamed;
      if (project?.id === renamed.id) { project = renamed; renderProject(); }
      else renderProjectList();
    }
    $('#projectActionDialog').close();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});

$('#editProjectDetails').addEventListener('click', () => {
  $('#editProjectTitle').value = project.title;
  $('#editProjectScene').value = project.scene;
  $('#editProjectBackground').value = project.background;
  $('#projectDetailsError').hidden = true;
  $('#projectDetailsDialog').showModal();
  $('#editProjectTitle').focus();
});
$('#closeProjectDetails').addEventListener('click', () => $('#projectDetailsDialog').close());
$('#projectDetailsDialog').addEventListener('click', (event) => {
  if (event.target === $('#projectDetailsDialog')) $('#projectDetailsDialog').close();
});
$('#projectDetailsForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#saveProjectDetails');
  const error = $('#projectDetailsError');
  button.disabled = true;
  error.hidden = true;
  try {
    project = await api(`/api/projects/${project.id}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: $('#editProjectTitle').value.trim(),
        scene: $('#editProjectScene').value.trim(),
        background: $('#editProjectBackground').value.trim()
      })
    });
    renderProject();
    $('#projectDetailsDialog').close();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally { button.disabled = false; }
});

function syncProjectLibrary() {
  if (!project) return;
  const index = projectLibrary.findIndex((item) => item.id === project.id);
  if (index >= 0) projectLibrary[index] = project;
  else projectLibrary.unshift(project);
  projectLibrary.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  renderProjectList();
}

async function activateProject(projectId) {
  try {
    project = await api(`/api/projects/${projectId}`);
    activeCharacterId = null;
    editingDialogue = null;
    $('#characterDialog').close();
    $('#projectCreator').hidden = true;
    $('#studio').hidden = false;
    $('#results').hidden = true;
    renderProject();
  } catch (err) {
    $('#projectList').innerHTML = `<div class="project-list-empty">${escapeHtml(err.message)}</div>`;
  }
}

function showNewProject() {
  project = null;
  activeCharacterId = null;
  editingDialogue = null;
  if ($('#characterDialog').open) $('#characterDialog').close();
  $('#studio').hidden = true;
  $('#results').hidden = true;
  $('#projectCreator').hidden = false;
  $('#projectForm').reset();
  renderProjectList();
  $('#projectTitle').focus();
}

$('#newProjectBtn').addEventListener('click', showNewProject);
$('#newProjectAction').addEventListener('click', showNewProject);

$('#projectForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  const error = $('#projectError');
  error.hidden = true;
  button.disabled = true;
  button.querySelector('span').textContent = 'CREATING PROJECT…';
  try {
    project = await api('/api/projects', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: $('#projectTitle').value.trim(),
        scene: $('#projectScene').value.trim(),
        background: $('#projectBackground').value.trim()
      })
    });
    $('#projectCreator').hidden = true;
    $('#studio').hidden = false;
    renderProject();
    $('#studio').scrollIntoView({behavior: 'smooth'});
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.querySelector('span').textContent = 'CREATE ROLEVOX PROJECT';
  }
});

$('#characterImage').addEventListener('change', (event) => {
  $('#imageFileName').textContent = event.target.files[0]?.name || 'NO FILE SELECTED';
});

$('#characterForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#castBtn');
  const error = $('#characterError');
  const file = $('#characterImage').files[0];
  error.hidden = true;
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    error.textContent = 'The image must be PNG, JPEG, or WebP and no larger than 5 MB.';
    error.hidden = false;
    return;
  }
  button.disabled = true;
  button.querySelector('span').textContent = 'VISUAL CASTING IN PROGRESS…';
  const previewUrl = URL.createObjectURL(file);
  try {
    const form = new FormData();
    form.append('name', $('#characterName').value.trim());
    form.append('brief', $('#characterBrief').value.trim());
    form.append('voice_presentation', $('#characterVoicePresentation').value);
    form.append('image', file, file.name);
    project = await api(`/api/projects/${project.id}/characters`, {method: 'POST', body: form});
    const character = project.characters[project.characters.length - 1];
    imagePreviews.set(character.id, previewUrl);
    event.target.reset();
    $('#imageFileName').textContent = 'NO FILE SELECTED';
    renderProject();
    openCharacter(character.id);
  } catch (err) {
    URL.revokeObjectURL(previewUrl);
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.querySelector('span').textContent = 'ANALYZE IMAGE & CAST VOICE';
  }
});

function renderProject() {
  $('#studioTitle').textContent = project.title;
  $('#studioContext').textContent = `${project.scene} · ${project.background}`;
  $('#projectId').textContent = project.id;
  $('#castCount').textContent = `${project.characters.length} CHARACTER${project.characters.length === 1 ? '' : 'S'}`;
  const target = $('#productionCharacter');
  const previousTarget = target.value;
  target.innerHTML = project.characters.length ? project.characters.map((character) =>
    `<option value="${character.id}">${escapeHtml(character.name)} · ${character.voice_locked ? '🔒 locked' : 'voice unlocked'}</option>`
  ).join('') : '<option value="">ADD A CHARACTER FIRST</option>';
  if ([...target.options].some((option) => option.value === previousTarget)) target.value = previousTarget;
  const grid = $('#characterGrid');
  if (!project.characters.length) {
    grid.innerHTML = '<div class="empty-card">ADD A CHARACTER TO BEGIN VISUAL CASTING</div>';
  } else {
    grid.innerHTML = project.characters.map(characterCard).join('');
    grid.querySelectorAll('.character-card').forEach((card) => {
      card.addEventListener('click', () => openCharacter(card.dataset.id));
    });
    grid.querySelectorAll('.lock-button').forEach((button) => {
      button.addEventListener('click', async (event) => {
        event.stopPropagation();
        await toggleVoiceLock(button.dataset.id);
      });
    });
  }
  syncProjectLibrary();
  renderDialogueComposer();
  updateReadiness();
}

function orderedProjectDialogues() {
  let stable = 0;
  const rows = (project?.characters || []).flatMap((character) => character.dialogues.map((line) => ({
    ...line, characterId: character.id, characterName: character.name, stable: stable++
  })));
  return rows.sort((a, b) => {
    const ao = Number(a.order) > 0 ? Number(a.order) : 1000000 + a.stable;
    const bo = Number(b.order) > 0 ? Number(b.order) : 1000000 + b.stable;
    return ao - bo;
  });
}

function updateAddresseeOptions(selected = '') {
  const speakerId = $('#dialogueSpeaker').value;
  const options = (project?.characters || []).filter((item) => item.id !== speakerId)
    .map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('');
  $('#dialogueAddressee').innerHTML = '<option value="">AI · INFER FROM CONTEXT</option>' + options;
  if ([...$('#dialogueAddressee').options].some((option) => option.value === selected)) {
    $('#dialogueAddressee').value = selected;
  }
}

function resetDialogueEditor() {
  editingDialogue = null;
  $('#projectDialogueForm').reset();
  $('#dialogueSpeaker').disabled = false;
  $('#cancelDialogueEdit').hidden = true;
  $('#saveDialogueLine span').textContent = 'ADD NEXT LINE';
  $('#saveDialogueLine b').textContent = '＋';
  renderDialogueComposer();
}

function renderDialogueComposer() {
  const characters = project?.characters || [];
  const speaker = $('#dialogueSpeaker');
  const previousSpeaker = editingDialogue?.characterId || speaker.value;
  speaker.innerHTML = characters.length
    ? characters.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('')
    : '<option value="">ADD A CHARACTER FIRST</option>';
  if (characters.some((item) => item.id === previousSpeaker)) speaker.value = previousSpeaker;
  speaker.disabled = !characters.length || Boolean(editingDialogue);
  updateAddresseeOptions(editingDialogue?.addresseeId || '');
  $('#saveDialogueLine').disabled = !characters.length;

  const lines = orderedProjectDialogues();
  $('#projectDialogueCount').textContent = `${lines.length} LINE${lines.length === 1 ? '' : 'S'}`;
  $('#projectDialogueList').innerHTML = lines.length ? lines.map((line, index) => {
    const target = line.addressee_id
      ? characters.find((item) => item.id === line.addressee_id)?.name || 'Unknown character'
      : 'AI infers from context';
    return `<article class="project-dialogue-line">
      <span>${String(index + 1).padStart(3, '0')}</span>
      <div class="dialogue-speaker"><strong>${escapeHtml(line.characterName)}</strong><small>→ ${escapeHtml(target)}</small></div>
      <div><em>${escapeHtml(line.emotion)}</em><p>${escapeHtml(line.text)}</p></div>
      <div class="dialogue-line-actions"><button type="button" class="edit-project-dialogue" data-character="${line.characterId}" data-id="${line.id}">EDIT</button>
        <button type="button" class="delete-project-dialogue" data-character="${line.characterId}" data-id="${line.id}">×</button></div>
    </article>`;
  }).join('') : '<div class="empty-dialogue">ADD THE FIRST LINE · ROLEVOX WILL USE EACH NEXT LINE AS CONTEXT</div>';

  document.querySelectorAll('.edit-project-dialogue').forEach((button) => button.addEventListener('click', () => {
    const character = characters.find((item) => item.id === button.dataset.character);
    const line = character?.dialogues.find((item) => item.id === button.dataset.id);
    if (!line) return;
    editingDialogue = {characterId: character.id, dialogueId: line.id, addresseeId: line.addressee_id || ''};
    renderDialogueComposer();
    $('#projectDialogueEmotion').value = line.emotion;
    $('#projectDialogueText').value = line.text;
    $('#dialogueAddressee').value = line.addressee_id || '';
    $('#cancelDialogueEdit').hidden = false;
    $('#saveDialogueLine span').textContent = 'SAVE CHANGES';
    $('#saveDialogueLine b').textContent = '✓';
    $('#projectDialogueText').focus();
  }));
  document.querySelectorAll('.delete-project-dialogue').forEach((button) => button.addEventListener('click', async () => {
    try {
      project = await api(`/api/projects/${project.id}/characters/${button.dataset.character}/dialogues/${button.dataset.id}`, {method: 'DELETE'});
      if (editingDialogue?.dialogueId === button.dataset.id) editingDialogue = null;
      renderProject();
    } catch (err) {
      $('#projectDialogueError').textContent = err.message;
      $('#projectDialogueError').hidden = false;
    }
  }));
}

$('#dialogueSpeaker').addEventListener('change', () => updateAddresseeOptions());
$('#cancelDialogueEdit').addEventListener('click', resetDialogueEditor);
$('#projectDialogueForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const error = $('#projectDialogueError');
  error.hidden = true;
  const characterId = editingDialogue?.characterId || $('#dialogueSpeaker').value;
  const dialogueId = editingDialogue?.dialogueId;
  const url = dialogueId
    ? `/api/projects/${project.id}/characters/${characterId}/dialogues/${dialogueId}`
    : `/api/projects/${project.id}/characters/${characterId}/dialogues`;
  const button = $('#saveDialogueLine');
  button.disabled = true;
  try {
    project = await api(url, {
      method: dialogueId ? 'PATCH' : 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        emotion: $('#projectDialogueEmotion').value.trim(),
        text: $('#projectDialogueText').value.trim(),
        addressee_id: $('#dialogueAddressee').value || null
      })
    });
    editingDialogue = null;
    $('#projectDialogueForm').reset();
    $('#dialogueSpeaker').disabled = false;
    $('#cancelDialogueEdit').hidden = true;
    $('#saveDialogueLine span').textContent = 'ADD NEXT LINE';
    $('#saveDialogueLine b').textContent = '＋';
    renderProject();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally { button.disabled = false; }
});

function characterCard(character) {
  const preview = imagePreviews.get(character.id) || `/api/projects/${project.id}/characters/${character.id}/image`;
  return `<article class="character-card character-card-simple ${character.voice_locked ? 'locked' : ''}" data-id="${character.id}">
    <div class="character-image">${preview ? `<img src="${preview}" alt="${escapeHtml(character.name)}">` : '<span>IMAGE REFERENCE</span>'}</div>
    <div class="simple-character-meta"><span>CHARACTER</span><h3>${escapeHtml(character.name)}</h3>
      <strong class="simple-lock-status ${character.voice_locked ? 'locked' : ''}">${character.voice_locked ? '🔒 VOICE LOCKED' : 'VOICE UNLOCKED'}</strong></div>
  </article>`;
}

async function toggleVoiceLock(characterId) {
  try {
    const character = project.characters.find((item) => item.id === characterId);
    const action = character.voice_locked ? 'unlock' : 'lock';
    project = await api(`/api/projects/${project.id}/characters/${characterId}/${action}`, {method: 'POST'});
    renderProject();
    if (activeCharacterId === characterId && $('#characterDialog').open) openCharacter(characterId);
  } catch (err) {
    const target = $('#characterDialog').open && $('#auditionError') ? $('#auditionError') : $('#characterError');
    target.textContent = err.message;
    target.hidden = false;
  }
}

function openCharacter(characterId) {
  activeCharacterId = characterId;
  const character = project.characters.find((item) => item.id === characterId);
  if (!character) return;
  const cast = character.casting;
  const identity = cast.voice_identity || {};
  const candidates = Array.isArray(cast.voice_candidates) ? cast.voice_candidates : [];
  const selectedVoice = cast.selected_voice;
  const preview = imagePreviews.get(character.id) || `/api/projects/${project.id}/characters/${character.id}/image`;
  $('#dialogContent').innerHTML = `
    <header class="dialog-header">
      <div class="dialog-portrait" role="button" tabindex="0" title="View full character image">${preview ? `<img src="${preview}" alt="${escapeHtml(character.name)} full reference">` : '<span>RV</span>'}<i>VIEW FULL IMAGE</i></div>
      <div class="character-heading">
        <div id="characterHeadingDisplay"><span class="kicker">CHARACTER WORKSPACE</span><h2>${escapeHtml(character.name)}</h2><p>${escapeHtml(character.brief)}</p>
          <div class="character-heading-actions"><button id="editCharacterButton" type="button">EDIT NAME &amp; BRIEF</button>
            <button id="deleteCharacterButton" type="button">DELETE CHARACTER</button></div></div>
        <form id="characterHeadingForm" hidden><span class="kicker">EDIT CHARACTER</span>
          <label>CHARACTER NAME<input id="editCharacterName" maxlength="80" value="${escapeHtml(character.name)}" required></label>
          <label>CHARACTER BRIEF<textarea id="editCharacterBrief" maxlength="1000" required>${escapeHtml(character.brief)}</textarea></label>
          <div><button id="cancelCharacterEdit" type="button">CANCEL</button><button type="submit">SAVE CHARACTER</button></div>
          <p id="characterEditError" class="error" hidden></p>
        </form>
      </div>
      <span class="dialog-lock ${character.voice_locked ? 'locked' : ''}">${character.voice_locked ? '🔒 VOICE LOCKED' : 'VOICE UNLOCKED'}</span>
    </header>
    <div class="dialog-columns">
      <section>
        <span class="block-label">VISUAL CASTING RESULT</span>
        <div class="reasoning-callout"><strong>${escapeHtml(cast.perceived_archetype)}</strong>
          <p>${escapeHtml(cast.visual_analysis)}</p><small>IMAGE + BRIEF + SCENE → CHARACTER VOICE PROFILE</small></div>
        <dl class="detail-list">
          <div><dt>Visual tone</dt><dd>${escapeHtml(cast.visual_tone)}</dd></div>
          <div><dt>Suggested voice</dt><dd>${escapeHtml(cast.suggested_register)}</dd></div>
          <div><dt>Delivery style</dt><dd>${escapeHtml(cast.delivery_style)}</dd></div>
          <div><dt>Voice texture</dt><dd>${escapeHtml(cast.voice_texture)}</dd></div>
          <div><dt>Confidence</dt><dd>${Number(cast.confidence || 0)}%</dd></div>
        </dl>
      </section>
      <section class="voice-identity">
        <div class="recast-control"><label><span>VOICE PRESENTATION</span><select id="workspaceVoicePresentation" ${character.voice_locked ? 'disabled' : ''}>
          <option value="auto" ${character.voice_presentation === 'auto' ? 'selected' : ''}>AI DECIDES</option>
          <option value="feminine" ${character.voice_presentation === 'feminine' ? 'selected' : ''}>FEMININE VOICE</option>
          <option value="masculine" ${character.voice_presentation === 'masculine' ? 'selected' : ''}>MASCULINE VOICE</option>
          <option value="neutral" ${character.voice_presentation === 'neutral' ? 'selected' : ''}>NEUTRAL VOICE</option></select></label>
          <button id="recastVoiceButton" type="button" ${character.voice_locked ? 'disabled' : ''}>${character.voice_locked ? 'UNLOCK TO RECAST' : 'RECAST 3 VOICES'}</button></div>
        <div class="audition-heading"><span class="block-label">VOICE CASTING · CHOOSE 1 OF 3</span>
          <label><span>PREVIEW LANGUAGE</span><select id="previewLanguage"><option value="zh">Chinese</option><option value="ja">Japanese</option><option value="en">English</option></select></label></div>
        <div class="voice-candidates">${candidates.map((candidate, index) => `<article class="voice-candidate ${selectedVoice === candidate.voice ? 'selected' : ''}">
          <header><span>OPTION ${String(index + 1).padStart(2, '0')}</span><strong>${escapeHtml(candidate.voice)}</strong></header>
          <p>${escapeHtml(candidate.qualities)} · ${escapeHtml(candidate.pitch)} · ${escapeHtml(candidate.texture)}</p>
          <small>${escapeHtml(candidate.speaking_style)} · ${escapeHtml(candidate.rationale)}</small>
          <div class="candidate-actions"><button type="button" class="audition-button" data-voice="${escapeHtml(candidate.voice)}">▶ GENERATE PREVIEW</button>
          <button type="button" class="select-voice" data-voice="${escapeHtml(candidate.voice)}" ${character.voice_locked ? 'disabled' : ''}>${selectedVoice === candidate.voice ? '✓ SELECTED' : 'SELECT VOICE'}</button></div>
          <audio class="audition-audio" data-voice="${escapeHtml(candidate.voice)}" controls hidden></audio>
        </article>`).join('')}</div>
        <span class="block-label selected-identity-label">${selectedVoice ? 'SELECTED VOICE IDENTITY' : 'SELECT A VOICE TO CREATE THE IDENTITY'}</span>
        <dl class="detail-list identity">
          <div><dt>Voice</dt><dd>${selectedVoice ? escapeHtml(identity.voice || cast.voice) : 'Not selected'}</dd></div>
          <div><dt>Qualities</dt><dd>${escapeHtml(identity.qualities)}</dd></div>
          <div><dt>Pitch</dt><dd>${escapeHtml(identity.pitch)}</dd></div>
          <div><dt>Texture</dt><dd>${escapeHtml(identity.texture)}</dd></div>
          <div><dt>Speaking style</dt><dd>${escapeHtml(identity.speaking_style)}</dd></div>
          <div><dt>Accent</dt><dd>${escapeHtml(identity.accent)}</dd></div>
        </dl>
        <button id="dialogLockButton" class="lock-large ${character.voice_locked ? 'locked' : ''}" ${!selectedVoice ? 'disabled' : ''}>
          ${character.voice_locked ? '🔓 UNLOCK THIS VOICE IDENTITY' : selectedVoice ? '🔒 LOCK THIS VOICE IDENTITY' : 'SELECT AN AUDITION VOICE FIRST'}
        </button>
        <p id="auditionError" class="error" hidden></p>
      </section>
    </div>`;
  if (!$('#characterDialog').open) $('#characterDialog').showModal();

  const openFullImage = () => {
    $('#lightboxCharacterImage').src = preview;
    $('#lightboxCharacterImage').alt = `${character.name} full character reference`;
    $('#lightboxCharacterName').textContent = character.name;
    $('#characterImageLightbox').showModal();
  };
  $('.dialog-portrait').addEventListener('click', openFullImage);
  $('.dialog-portrait').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openFullImage(); }
  });
  $('#editCharacterButton').addEventListener('click', () => {
    $('#characterHeadingDisplay').hidden = true;
    $('#characterHeadingForm').hidden = false;
    $('#editCharacterName').focus();
  });
  $('#deleteCharacterButton').addEventListener('click', () => {
    pendingDeleteCharacterId = character.id;
    $('#deleteCharacterTitle').textContent = `Delete “${character.name}”?`;
    $('#deleteCharacterError').hidden = true;
    $('#deleteCharacterDialog').showModal();
  });
  $('#cancelCharacterEdit').addEventListener('click', () => {
    $('#characterHeadingForm').hidden = true;
    $('#characterHeadingDisplay').hidden = false;
  });
  $('#characterHeadingForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const error = $('#characterEditError');
    const button = event.submitter;
    error.hidden = true;
    button.disabled = true;
    try {
      project = await api(`/api/projects/${project.id}/characters/${character.id}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: $('#editCharacterName').value.trim(), brief: $('#editCharacterBrief').value.trim()})
      });
      renderProject();
      openCharacter(character.id);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
  $('#dialogLockButton').addEventListener('click', () => toggleVoiceLock(character.id));
  $('#recastVoiceButton').addEventListener('click', async () => {
    const button = $('#recastVoiceButton');
    const error = $('#auditionError');
    error.hidden = true;
    button.disabled = true;
    button.textContent = 'VISUAL RECASTING…';
    try {
      project = await api(`/api/projects/${project.id}/characters/${character.id}/recast`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({voice_presentation: $('#workspaceVoicePresentation').value})
      });
      renderProject();
      openCharacter(character.id);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      button.disabled = false;
      button.textContent = 'RECAST 3 VOICES';
    }
  });
  document.querySelectorAll('.select-voice').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        project = await api(`/api/projects/${project.id}/characters/${character.id}/select-voice`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({voice: button.dataset.voice})
        });
        renderProject();
        openCharacter(character.id);
      } catch (err) {
        $('#auditionError').textContent = err.message;
        $('#auditionError').hidden = false;
      }
    });
  });
  document.querySelectorAll('.audition-button').forEach((button) => {
    button.addEventListener('click', async () => {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = 'GENERATING…';
      try {
        const blob = await apiBlob(`/api/projects/${project.id}/characters/${character.id}/voice-preview`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({voice: button.dataset.voice, language: $('#previewLanguage').value})
        });
        const audio = document.querySelector(`.audition-audio[data-voice="${CSS.escape(button.dataset.voice)}"]`);
        if (audio.dataset.objectUrl) URL.revokeObjectURL(audio.dataset.objectUrl);
        audio.dataset.objectUrl = URL.createObjectURL(blob);
        audio.src = audio.dataset.objectUrl;
        audio.hidden = false;
        await audio.play().catch(() => {});
        button.textContent = '↻ REGENERATE';
      } catch (err) {
        button.textContent = original;
        $('#auditionError').textContent = err.message;
        $('#auditionError').hidden = false;
      } finally {
        button.disabled = false;
      }
    });
  });
}

$('#closeDialog').addEventListener('click', () => $('#characterDialog').close());
$('#characterDialog').addEventListener('click', (event) => {
  if (event.target === $('#characterDialog')) $('#characterDialog').close();
});
$('#closeImageLightbox').addEventListener('click', () => $('#characterImageLightbox').close());
$('#characterImageLightbox').addEventListener('click', (event) => {
  if (event.target === $('#characterImageLightbox')) $('#characterImageLightbox').close();
});
$('#cancelDeleteCharacter').addEventListener('click', () => $('#deleteCharacterDialog').close());
$('#deleteCharacterForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#confirmDeleteCharacter');
  const error = $('#deleteCharacterError');
  button.disabled = true;
  error.hidden = true;
  try {
    project = await api(`/api/projects/${project.id}/characters/${pendingDeleteCharacterId}`, {method: 'DELETE'});
    const previewUrl = imagePreviews.get(pendingDeleteCharacterId);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    imagePreviews.delete(pendingDeleteCharacterId);
    pendingDeleteCharacterId = null;
    activeCharacterId = null;
    $('#deleteCharacterDialog').close();
    $('#characterDialog').close();
    renderProject();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally { button.disabled = false; }
});

function updateReadiness() {
  const allCharacters = project?.characters || [];
  const mode = document.querySelector('input[name="generationMode"]:checked').value;
  let ready = false;
  let message = 'WAITING FOR CAST';
  if (mode === 'single') {
    const character = allCharacters.find((item) => item.id === $('#productionCharacter').value);
    const hasDirection = $('#singleVoiceEmotion').value.trim() && $('#singleDialogueText').value.trim();
    ready = Boolean(character?.voice_locked && hasDirection);
    message = !character ? 'SELECT CHARACTER'
      : !character.voice_locked ? `LOCK ${character.name.toUpperCase()} VOICE`
      : !hasDirection ? 'ENTER EMOTION + DIALOGUE' : 'READY · SINGLE CHARACTER · VOICE LOCKED';
  } else {
    const speakers = allCharacters.filter((item) => item.dialogues.length > 0);
    const unlocked = speakers.filter((item) => !item.voice_locked).length;
    const lines = speakers.reduce((sum, item) => sum + item.dialogues.length, 0);
    ready = speakers.length > 0 && unlocked === 0;
    message = !speakers.length ? 'ADD PROJECT DIALOGUE'
      : unlocked ? `LOCK ${unlocked} SPEAKER VOICE${unlocked > 1 ? 'S' : ''}`
      : `READY · DIALOGUE · ${lines} LINES`;
  }
  $('#produceBtn').disabled = !ready;
  $('#readiness').className = `readiness ${ready ? 'ready' : ''}`;
  $('#readiness').textContent = message;
}

$('#productionCharacter').addEventListener('change', updateReadiness);
['singleVoiceEmotion', 'singleDialogueText'].forEach((id) => $(`#${id}`).addEventListener('input', updateReadiness));
document.querySelectorAll('input[name="generationMode"]').forEach((input) => input.addEventListener('change', () => {
  const single = input.value === 'single' && input.checked;
  if (!input.checked) return;
  $('#singleGenerationPanel').hidden = !single;
  $('#dialogueGenerationPanel').hidden = single;
  $('#productionError').hidden = true;
  updateReadiness();
}));

$('#produceBtn').addEventListener('click', async () => {
  const button = $('#produceBtn');
  const error = $('#productionError');
  error.hidden = true;
  button.disabled = true;
  try {
    const workflowMode = document.querySelector('input[name="generationMode"]:checked').value;
    currentJob = await api(`/api/projects/${project.id}/produce`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        target_language: document.querySelector('input[name="targetLanguage"]:checked').value,
        production_mode: document.querySelector('input[name="productionMode"]:checked').value,
        workflow_mode: workflowMode,
        revision_limit: Number($('#revisionLimit').value),
        single_character_id: workflowMode === 'single' ? $('#productionCharacter').value : null,
        single_emotion: workflowMode === 'single' ? $('#singleVoiceEmotion').value.trim() : null,
        single_text: workflowMode === 'single' ? $('#singleDialogueText').value.trim() : null
      })
    });
    $('#runPanel').hidden = false;
    $('#results').hidden = true;
    renderJob(currentJob);
    $('#runPanel').scrollIntoView({behavior: 'smooth', block: 'center'});
    poll(currentJob.id);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    updateReadiness();
  }
});

async function poll(jobId, retryCount = 0) {
  try {
    currentJob = await api(`/api/jobs/${jobId}`);
    $('#productionError').hidden = true;
    renderJob(currentJob);
    if (currentJob.status === 'completed') {
      renderResults(currentJob.result);
      updateReadiness();
      return;
    }
    if (currentJob.status === 'failed') throw new Error(currentJob.error || 'Production failed');
    setTimeout(() => poll(jobId, 0), 1200);
  } catch (err) {
    if ([429, 503].includes(err.status)) {
      const delay = Math.min(8000, 1500 * (2 ** Math.min(retryCount, 3)));
      $('#productionError').textContent = `Production worker is busy. Retrying automatically in ${Math.ceil(delay / 1000)} seconds…`;
      $('#productionError').hidden = false;
      setTimeout(() => poll(jobId, retryCount + 1), delay);
      return;
    }
    $('#productionError').textContent = err.message;
    $('#productionError').hidden = false;
    updateReadiness();
  }
}

function renderJob(job) {
  $('#runStage').textContent = job.stage;
  $('#runPercent').textContent = `${job.progress}%`;
  $('#progressBar').style.width = `${job.progress}%`;
  const stages = ['Direction', 'Translation', 'Casting', 'Dialogue planning', 'Voice generation', 'Voice critique', 'Automatic retry', 'Ready'];
  document.querySelectorAll('#pipeline li').forEach((item) => {
    item.className = '';
    const own = stages.indexOf(item.dataset.stage);
    const active = stages.indexOf(job.stage);
    if (own < active || job.status === 'completed') item.classList.add('done');
    if (own === active && job.status !== 'completed') item.classList.add('active');
  });
  $('#eventLog').innerHTML = job.events.slice().reverse().map((event) => {
    const time = new Date(event.at).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false});
    return `<div class="event ${event.status}"><span>${time}</span><strong>${escapeHtml(event.agent)}</strong><p><b>${event.status.toUpperCase()}</b> · ${escapeHtml(event.message)}</p></div>`;
  }).join('');
}

function metric(label, value) {
  return `<div><span>${label}</span><strong>${Number(value || 0)}</strong></div>`;
}

function revisionView(revision) {
  if (!revision) return '';
  const emotion = revision.emotion || {};
  const rate = revision.speaking_rate || {};
  return `<div class="auto-revision">
    <div class="revision-title"><span>AUTO REVISION</span><strong>Directing another take…</strong></div>
    <div class="revision-grid">
      <div><span>Emotion</span><b>${emotion.from ?? '—'} → ${emotion.to ?? '—'}</b></div>
      <div><span>Speaking rate</span><b>${rate.from ?? '—'} → ${rate.to ?? '—'}</b></div>
      <div><span>Breathiness</span><b>+${revision.breathiness_delta ?? 0}%</b></div>
      <div><span>Pause</span><b>+${revision.pause_delta_seconds ?? 0} sec</b></div>
    </div>
  </div>`;
}

function renderResults(result) {
  const avg = Math.round(result.lines.reduce((sum, line) => sum + Number(line.qa.score || 0), 0) / result.lines.length);
  const revisions = result.lines.reduce((sum, line) => sum + Math.max(0, line.takes.length - 1), 0);
  const languages = {zh: 'Chinese', ja: 'Japanese', en: 'English'};
  $('#summaryGrid').innerHTML = `
    <article><small>GENERATION TYPE</small><strong>${result.workflow_mode === 'single' ? 'SINGLE' : 'DIALOGUE'}</strong></article>
    <article><small>PRODUCTION TARGET</small><strong>${escapeHtml(result.production_mode).toUpperCase()}</strong></article>
    <article><small>OUTPUT LANGUAGE</small><strong>${languages[result.target_language]}</strong></article>
    <article><small>LOCKED CHARACTERS</small><strong>${result.casting.length}</strong></article>
    <article><small>APPROVED LINES</small><strong>${result.lines.filter((line) => line.approved).length}/${result.lines.length}</strong></article>
    <article><small>AUTO REVISIONS</small><strong>${revisions}</strong></article>
    <article><small>AVERAGE SCORE</small><strong>${avg}</strong></article>`;
  const receipt = result.run_receipt || {};
  $('#runReceipt').innerHTML = receipt.run_id ? `
    <div><span>AUTONOMOUS RUN RECEIPT</span><strong>${escapeHtml(receipt.run_id)}</strong></div>
    <dl>
      <div><dt>ORIGIN</dt><dd>${escapeHtml(receipt.origin || 'studio')}</dd></div>
      <div><dt>ORCHESTRATOR</dt><dd>${escapeHtml(receipt.orchestrator || 'native')}</dd></div>
      <div><dt>DURABLE WORKER</dt><dd>${escapeHtml(receipt.durable_worker || 'local')}</dd></div>
      <div><dt>VOICE POLICY</dt><dd>SYNTHETIC ONLY · NO CLONING</dd></div>
    </dl>
    <p>Receipt, agent trace, critic decisions, selected takes, and SHA-256 hashes are included in the game package.</p>` : '';
  $('#downloadBtn').href = result.package_url;
  $('#assetList').innerHTML = result.lines.map((line) => {
    const takes = line.takes.map((take, index) => `<div class="take-sequence">
      <article class="take ${take.approved ? 'approved' : 'retry'}">
        <header><div><span>TAKE ${String(take.take).padStart(2, '0')}</span><strong>${take.approved ? '✓ APPROVED' : 'CRITIC REVIEW'}</strong></div>
          <b class="overall">${take.qa.score}</b></header>
        <div class="metric-grid">
          ${metric('Emotion match', take.qa.emotion_match)}
          ${metric('Character consistency', take.qa.character_consistency)}
          ${metric('Pronunciation', take.qa.pronunciation)}
          ${metric('Scene fit', take.qa.scene_fit)}
        </div>
        <blockquote>${escapeHtml(take.qa.feedback)}</blockquote>
        <audio controls preload="none" src="${take.url}"></audio>
      </article>
      ${!take.approved && index < line.takes.length - 1 ? revisionView(take.revision) : ''}
    </div>`).join('');
    return `<section class="line-result">
      <header class="line-heading"><div><span>LINE ${String(line.id).padStart(3, '0')} · ${escapeHtml(line.character)}</span>
        <h3>${escapeHtml(line.text)}</h3>
        ${line.source_text !== line.text ? `<p>Source: ${escapeHtml(line.source_text)}</p>` : ''}
        <small>${escapeHtml(line.emotion)} · ${escapeHtml(line.pace)} · VOICE ${escapeHtml(line.voice)} 🔒</small></div>
        <div><span>SELECTED TAKE</span><strong>${String(line.selected_take).padStart(2, '0')}</strong></div></header>
      <div class="takes">${takes}</div>
    </section>`;
  }).join('');
  $('#results').hidden = false;
  $('#results').scrollIntoView({behavior: 'smooth'});
}

checkHealth();
loadProjects();
