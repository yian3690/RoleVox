const $ = (q) => document.querySelector(q);
let project = null;
let currentJob = null;
let activeCharacterId = null;
const imagePreviews = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
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

$('#characterForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#castBtn');
  const error = $('#characterError');
  const file = $('#characterImage').files[0];
  error.hidden = true;
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    error.textContent = '圖片必須是 PNG、JPEG 或 WebP，且不超過 5 MB。';
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
    form.append('image', file, file.name);
    project = await api(`/api/projects/${project.id}/characters`, {method: 'POST', body: form});
    const character = project.characters[project.characters.length - 1];
    imagePreviews.set(character.id, previewUrl);
    event.target.reset();
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
        await lockVoice(button.dataset.id);
      });
    });
  }
  updateReadiness();
}

function characterCard(character) {
  const cast = character.casting;
  const identity = cast.voice_identity || {};
  const preview = imagePreviews.get(character.id);
  return `<article class="character-card ${character.voice_locked ? 'locked' : ''}" data-id="${character.id}">
    <div class="character-image">
      ${preview ? `<img src="${preview}" alt="${escapeHtml(character.name)}">` : '<span>IMAGE<br>REFERENCE</span>'}
      <div class="confidence">${Number(cast.confidence || 0)}% CONFIDENCE</div>
    </div>
    <div class="character-body">
      <div class="card-title"><div><small>CHARACTER CARD</small><h3>${escapeHtml(character.name)}</h3></div>
        <span class="voice-chip">${escapeHtml(cast.voice)}</span></div>
      <div class="visual-result">
        <span>VISUAL CASTING RESULT</span>
        <dl>
          <div><dt>Archetype</dt><dd>${escapeHtml(cast.perceived_archetype)}</dd></div>
          <div><dt>Visual tone</dt><dd>${escapeHtml(cast.visual_tone)}</dd></div>
          <div><dt>Register</dt><dd>${escapeHtml(cast.suggested_register)}</dd></div>
          <div><dt>Delivery</dt><dd>${escapeHtml(cast.delivery_style)}</dd></div>
          <div><dt>Texture</dt><dd>${escapeHtml(cast.voice_texture)}</dd></div>
        </dl>
      </div>
      <div class="identity-preview"><span>VOICE IDENTITY</span><strong>${escapeHtml(identity.qualities)}</strong>
        <small>${escapeHtml(identity.pitch)} · ${escapeHtml(identity.texture)} · ${escapeHtml(identity.speaking_style)}</small></div>
      <div class="card-footer"><span>${character.dialogues.length} LINES</span>
        <button class="lock-button ${character.voice_locked ? 'is-locked' : ''}" data-id="${character.id}" ${character.voice_locked ? 'disabled' : ''}>
          ${character.voice_locked ? '🔒 VOICE LOCKED' : 'LOCK VOICE'}
        </button></div>
    </div>
  </article>`;
}

async function lockVoice(characterId) {
  try {
    project = await api(`/api/projects/${project.id}/characters/${characterId}/lock`, {method: 'POST'});
    renderProject();
    if (activeCharacterId === characterId && $('#characterDialog').open) openCharacter(characterId);
  } catch (err) {
    $('#characterError').textContent = err.message;
    $('#characterError').hidden = false;
  }
}

function openCharacter(characterId) {
  activeCharacterId = characterId;
  const character = project.characters.find((item) => item.id === characterId);
  if (!character) return;
  const cast = character.casting;
  const identity = cast.voice_identity || {};
  const preview = imagePreviews.get(character.id);
  $('#dialogContent').innerHTML = `
    <header class="dialog-header">
      <div class="dialog-portrait">${preview ? `<img src="${preview}" alt="">` : '<span>RV</span>'}</div>
      <div><span class="kicker">CHARACTER WORKSPACE</span><h2>${escapeHtml(character.name)}</h2><p>${escapeHtml(character.brief)}</p></div>
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
        <span class="block-label">VOICE IDENTITY</span>
        <dl class="detail-list identity">
          <div><dt>Voice</dt><dd>${escapeHtml(identity.voice || cast.voice)}</dd></div>
          <div><dt>Qualities</dt><dd>${escapeHtml(identity.qualities)}</dd></div>
          <div><dt>Pitch</dt><dd>${escapeHtml(identity.pitch)}</dd></div>
          <div><dt>Texture</dt><dd>${escapeHtml(identity.texture)}</dd></div>
          <div><dt>Speaking style</dt><dd>${escapeHtml(identity.speaking_style)}</dd></div>
          <div><dt>Accent</dt><dd>${escapeHtml(identity.accent)}</dd></div>
        </dl>
        <button id="dialogLockButton" class="lock-large ${character.voice_locked ? 'locked' : ''}" ${character.voice_locked ? 'disabled' : ''}>
          ${character.voice_locked ? '🔒 VOICE LOCKED FOR THIS PROJECT' : 'LOCK THIS VOICE IDENTITY'}
        </button>
      </section>
    </div>
    <section class="dialogue-editor">
      <div class="section-heading compact"><div><span class="kicker">DIALOGUE LIBRARY</span><h2>Add performance lines</h2></div><span>${character.dialogues.length} LINES</span></div>
      <form id="dialogueForm">
        <label>VOICE EMOTION<input id="dialogueEmotion" maxlength="80" placeholder="Fearful · restrained · urgent" required></label>
        <label>DIALOGUE TEXT<textarea id="dialogueText" maxlength="4000" placeholder="輸入角色台詞；生成時會翻譯成專案選定語言。" required></textarea></label>
        <button type="submit" class="secondary-action"><span>ADD DIALOGUE LINE</span><b>＋</b></button>
      </form>
      <p id="dialogueError" class="error" hidden></p>
      <div class="dialogue-list">
        ${character.dialogues.length ? character.dialogues.map((line, index) => `<article>
          <span>${String(index + 1).padStart(3, '0')}</span><div><strong>${escapeHtml(line.emotion)}</strong><p>${escapeHtml(line.text)}</p></div>
          <button class="delete-line" data-id="${line.id}" aria-label="Delete">×</button></article>`).join('') : '<div class="empty-dialogue">NO DIALOGUE YET</div>'}
      </div>
    </section>`;
  if (!$('#characterDialog').open) $('#characterDialog').showModal();

  $('#dialogLockButton').addEventListener('click', () => lockVoice(character.id));
  $('#dialogueForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      project = await api(`/api/projects/${project.id}/characters/${character.id}/dialogues`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({emotion: $('#dialogueEmotion').value.trim(), text: $('#dialogueText').value.trim()})
      });
      renderProject();
      openCharacter(character.id);
    } catch (err) {
      $('#dialogueError').textContent = err.message;
      $('#dialogueError').hidden = false;
      button.disabled = false;
    }
  });
  document.querySelectorAll('.delete-line').forEach((button) => {
    button.addEventListener('click', async () => {
      project = await api(`/api/projects/${project.id}/characters/${character.id}/dialogues/${button.dataset.id}`, {method: 'DELETE'});
      renderProject();
      openCharacter(character.id);
    });
  });
}

$('#closeDialog').addEventListener('click', () => $('#characterDialog').close());
$('#characterDialog').addEventListener('click', (event) => {
  if (event.target === $('#characterDialog')) $('#characterDialog').close();
});

function updateReadiness() {
  const characters = project?.characters || [];
  const unlocked = characters.filter((item) => !item.voice_locked).length;
  const lines = characters.reduce((sum, item) => sum + item.dialogues.length, 0);
  const ready = characters.length > 0 && unlocked === 0 && lines > 0;
  $('#produceBtn').disabled = !ready;
  $('#readiness').className = `readiness ${ready ? 'ready' : ''}`;
  $('#readiness').textContent = ready ? `READY · ${lines} LINES · ALL VOICES LOCKED`
    : !characters.length ? 'WAITING FOR CAST'
    : unlocked ? `LOCK ${unlocked} VOICE${unlocked > 1 ? 'S' : ''}`
    : 'ADD DIALOGUE';
}

$('#produceBtn').addEventListener('click', async () => {
  const button = $('#produceBtn');
  const error = $('#productionError');
  error.hidden = true;
  button.disabled = true;
  try {
    currentJob = await api(`/api/projects/${project.id}/produce`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        target_language: document.querySelector('input[name="targetLanguage"]:checked').value,
        production_mode: document.querySelector('input[name="productionMode"]:checked').value,
        revision_limit: Number($('#revisionLimit').value)
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

async function poll(jobId) {
  try {
    currentJob = await api(`/api/jobs/${jobId}`);
    renderJob(currentJob);
    if (currentJob.status === 'completed') {
      renderResults(currentJob.result);
      updateReadiness();
      return;
    }
    if (currentJob.status === 'failed') throw new Error(currentJob.error || 'Production failed');
    setTimeout(() => poll(jobId), 1200);
  } catch (err) {
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
    const time = new Date(event.at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
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
  const languages = {zh: '中文', ja: '日本語', en: 'English'};
  $('#summaryGrid').innerHTML = `
    <article><small>PRODUCTION TARGET</small><strong>${escapeHtml(result.production_mode).toUpperCase()}</strong></article>
    <article><small>OUTPUT LANGUAGE</small><strong>${languages[result.target_language]}</strong></article>
    <article><small>LOCKED CHARACTERS</small><strong>${result.casting.length}</strong></article>
    <article><small>APPROVED LINES</small><strong>${result.lines.filter((line) => line.approved).length}/${result.lines.length}</strong></article>
    <article><small>AUTO REVISIONS</small><strong>${revisions}</strong></article>
    <article><small>AVERAGE SCORE</small><strong>${avg}</strong></article>`;
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
