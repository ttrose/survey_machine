import { api, setKey, escape as e, notify, copy, download } from './api.js';
import { types, templates, newQuestion, surveyForm, readAnswers } from './forms.js';

const root = document.querySelector('#app');
const modal = document.querySelector('#modal');
const state = { unlocked: false, surveys: [], total: 0, filter: '', search: '', offset: 0, listVersion: 0, survey: null, dirty: false, resultsTab: 'summary', responseOffset: 0, keys: [] };
let routeVersion = 0;

const iconPaths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  template: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 3v18M9 10h11"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
  arrow: '<path d="M7 17 17 7M7 7h10v10"/>',
  chart: '<path d="M4 3v17h17M9 16v-5m5 5V7m5 9V4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  link: '<path d="m10 13 4-4M8 15l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 3 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  exit: '<path d="M10 5H4v14h6m4-14 6 7-6 7M8 12h12"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14m-8 3v7m4-7v7"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
};
function icon(name, className = '') { return `<svg class="icon ${className}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.arrow}</svg>`; }
function statusBadge(status) { return `<span class="status ${status}"><span></span>${{ draft: 'Draft', published: 'Open', closed: 'Closed' }[status]}</span>`; }
function date(value, detailed = false) { return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', ...(detailed ? { hour: 'numeric', minute: '2-digit' } : {}) }).format(new Date(value)); }
function number(value) { return new Intl.NumberFormat().format(value); }
function errorView(error) { return `<div class="empty-panel"><div class="empty-symbol">!</div><h2>We couldn’t open this page</h2><p>${e(error.message)}</p><button class="button secondary" data-action="retry">Try again</button></div>`; }
function showModal(html) { modal.innerHTML = html; if (!modal.open) modal.showModal(); }
function closeModal() { modal.close(); modal.innerHTML = ''; }
function modalHeader(title, description = '') { return `<div class="modal-heading"><div><h2 id="modal-title">${e(title)}</h2>${description ? `<p>${e(description)}</p>` : ''}</div><button class="icon-button" data-action="close-modal" aria-label="Close dialog">×</button></div>`; }
function loading() { return '<div class="loading-state"><span class="spinner"></span> Loading your workspace…</div>'; }
function safeLeave() { return !state.dirty || confirm('You have unsaved changes. Leave without saving?'); }

function shell(active = 'surveys') {
  root.innerHTML = `<div class="workspace">
    <aside class="sidebar"><a class="brand" href="#/surveys"><img src="/mark.svg" alt=""><span>Survey<br><strong>Machine</strong><span class="brand-dot">.</span></span></a>
      <div class="workspace-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">${[['surveys', 'grid', 'Surveys'], ['templates', 'template', 'Templates'], ['integrations', 'code', 'Integrations']].map(([id, glyph, label]) => `<a href="#/${id}" class="nav-item${active === id ? ' active' : ''}"${active === id ? ' aria-current="page"' : ''}>${icon(glyph)}<span>${label}</span>${active === id ? '<span class="nav-dot"></span>' : ''}</a>`).join('')}</nav>
      <div class="sidebar-note"><span class="note-spark">✳</span><h3>A little curiosity<br>goes a long way.</h3><p>Turn the right questions<br>into your next good idea.</p></div>
      <div class="sidebar-bottom"><a href="/docs" target="_blank" rel="noopener">${icon('code')} API documentation ${icon('arrow')}</a><div class="workspace-owner"><span class="avatar">SM</span><div><strong>My workspace</strong><span>Administrator</span></div><button class="icon-button" data-action="signout" aria-label="Lock workspace">${icon('exit')}</button></div></div>
    </aside>
    <div class="workspace-body"><header class="topbar"><span>Workspace <span class="crumb-divider">/</span> <strong>${active[0].toUpperCase() + active.slice(1)}</strong></span><div class="topbar-right"><span class="connection"><span></span> Workspace connected</span><span class="version-tag">v0.1</span></div></header><main id="main" class="main-content">${loading()}</main><footer class="workspace-footer"><span>Made for curious people.</span><span>Survey Machine <span class="footer-dot">·</span> Your questions, your data.</span></footer></div>
  </div>`;
}

function login() {
  root.innerHTML = `<main id="main" class="login-page"><div class="login-art"><a class="brand" href="/"><img src="/mark.svg" alt=""><span>Survey<br><strong>Machine</strong><span class="brand-dot">.</span></span></a><div><span class="eyebrow">START WITH A LITTLE CURIOSITY</span><h1>Good questions.<br><em>Useful answers.</em></h1><p>A simple home for creating surveys,<br>hearing from people, and finding what’s next.</p><div class="login-art-lines" aria-hidden="true"><div>01 <span>Ask something.</span> ↗</div><div>02 <span>Hear people out.</span> ↗</div><div>03 <span>Make your next move.</span> ↗</div></div></div><span class="login-art-footer">Your questions. Your data. Your next good idea.</span></div><div class="login-side"><form id="login-form" class="login-form"><span class="eyebrow">YOUR WORKSPACE</span><h2>Let’s get you in.</h2><p>Enter your administrator key to open your workspace.</p><label for="workspace-key">Administrator key</label><input type="password" id="workspace-key" name="key" required autocomplete="off" placeholder="Your workspace key" minlength="32"><p class="form-error" id="login-error" role="alert"></p><button class="button primary" type="submit">Open workspace ${icon('arrow')}</button><div class="login-help">${icon('lock')}<span>Your key stays in memory for this session. Refreshing the page locks the workspace.</span></div><p class="setup-help">Setting up for the first time? Your administrator key is in your local configuration or your Cloudflare secret.</p></form></div></main>`;
}

async function route() {
  const version = ++routeVersion;
  if (!state.unlocked) { login(); return; }
  const [, page = 'surveys', id] = location.hash.split('/');
  state.dirty = false;
  shell(['templates', 'integrations'].includes(page) ? page : 'surveys');
  const content = document.querySelector('#main');
  try {
    if (page === 'builder' && id) {
      const survey = await api(`/surveys/${id}`);
      if (version !== routeVersion) return;
      state.survey = survey;
      renderBuilder();
    } else if (page === 'results' && id) {
      state.responseOffset = 0;
      await loadResults(id, version);
    } else if (page === 'templates') { renderTemplates(); }
    else if (page === 'integrations') {
      const keys = await api('/api-keys');
      if (version !== routeVersion) return;
      state.keys = keys;
      renderIntegrations();
    } else {
      const [stats, surveys] = await Promise.all([api('/stats'), api('/surveys?limit=25')]);
      if (version !== routeVersion) return;
      state.stats = stats; state.surveys = surveys.items; state.total = surveys.total;
      state.filter = ''; state.search = ''; state.offset = 0;
      renderDashboard();
    }
  } catch (error) { if (version === routeVersion) content.innerHTML = errorView(error); }
}

function renderDashboard() {
  document.querySelector('#main').innerHTML = `<div class="page-heading"><div><span class="eyebrow">A HOME FOR YOUR QUESTIONS</span><h1>Your surveys<span class="heading-dot">.</span></h1><p>Create a conversation. Discover something useful.</p></div><button class="button primary" data-action="new-survey">${icon('plus')} Create survey</button></div>
    <div class="stats-grid"><div class="stat-card"><div><span>Total surveys</span>${icon('grid')}</div><strong>${number(state.stats.surveys)}</strong><p>Ideas waiting to be explored</p></div><div class="stat-card"><div><span>Responses collected</span>${icon('chart')}</div><strong>${number(state.stats.responses)}</strong><p>A little more perspective</p></div><div class="stat-card"><div><span>Open for responses</span>${icon('link')}</div><strong>${number(state.stats.published)}</strong><p>Conversations in progress</p></div></div>
    <section class="survey-section"><div class="section-toolbar"><div class="tabs" role="group" aria-label="Filter surveys">${[['', 'All surveys'], ['published', 'Open'], ['draft', 'Drafts'], ['closed', 'Closed']].map(([key, label]) => `<button data-action="filter" data-filter="${key}" class="tab${state.filter === key ? ' selected' : ''}" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><form id="search-form" class="search-box">${icon('search')}<input type="search" name="search" aria-label="Search surveys" placeholder="Search surveys…" value="${e(state.search)}"><button type="submit" class="sr-only">Search</button></form></div><div id="survey-list">${surveyList()}</div></section>
    <div class="bottom-callout"><span class="callout-icon">✳</span><div><strong>Every good answer starts with a good question.</strong><p>Find a starting point in our survey templates.</p></div><a class="text-link" href="#/templates">Explore templates ${icon('arrow')}</a></div>`;
}

function surveyList() {
  if (!state.surveys.length) return `<div class="empty-surveys"><div class="paper-illustration" aria-hidden="true"><div class="paper-top"><span></span><i>✳</i></div><div class="paper-line wide"></div><div class="paper-line"></div><div class="paper-option"><b>✓</b><span></span></div><div class="paper-option"><b></b><span></span></div><div class="paper-option"><b></b><span></span></div></div><h2>${state.search || state.filter ? 'No surveys here yet.' : 'Make room for good questions.'}</h2><p>${state.search || state.filter ? 'Try a different search or filter.' : 'Your next insight starts with a simple survey.<br>Create one from scratch, or find a template you like.'}</p><button class="button secondary" data-action="new-survey">${icon('plus')} Create your first survey</button></div>`;
  return `<div class="table-wrap"><table class="survey-table"><thead><tr><th>Survey</th><th>Status</th><th>Responses</th><th>Last updated</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${state.surveys.map((s, i) => `<tr><td><div class="survey-name"><span class="survey-glyph glyph-${i % 3}">${icon('template')}</span><div><a class="survey-title" href="#/builder/${s.id}">${e(s.title)}</a><span>${s.questions.length} question${s.questions.length !== 1 ? 's' : ''} <span class="small-dot">·</span> ${s.respondent_mode === 'anonymous' ? 'Anonymous' : 'Named responses'}</span></div></div></td><td>${statusBadge(s.status)}</td><td><a class="response-count" href="#/results/${s.id}">${number(s.response_count)} ${icon('arrow')}</a></td><td class="date-cell">${date(s.updated_at)}</td><td><details class="row-menu"><summary aria-label="Actions for ${e(s.title)}">•••</summary><div><a href="#/builder/${s.id}">Open survey</a><a href="#/results/${s.id}">View responses</a>${s.status !== 'draft' ? `<button data-action="share-row" data-id="${s.id}">Share survey</button>` : ''}<button data-action="duplicate-row" data-id="${s.id}">Duplicate</button><button class="danger-text" data-action="delete-survey" data-id="${s.id}">Delete survey</button></div></details></td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${state.offset + 1}–${state.offset + state.surveys.length} of ${number(state.total)} surveys</span><div><button class="button small secondary" data-action="survey-prev"${!state.offset ? ' disabled' : ''}>← Previous</button><button class="button small secondary" data-action="survey-next"${state.offset + state.surveys.length >= state.total ? ' disabled' : ''}>Next →</button></div></div>`;
}

async function refreshSurveys() {
  const query = new URLSearchParams({ limit: '25', offset: String(state.offset) });
  if (state.filter) query.set('status', state.filter);
  if (state.search) query.set('search', state.search);
  const requestVersion = ++state.listVersion;
  const result = await api(`/surveys?${query}`);
  if (state.listVersion !== requestVersion || !document.querySelector('#survey-list')) return;
  state.surveys = result.items; state.total = result.total;
  document.querySelector('#survey-list').innerHTML = surveyList();
  document.querySelectorAll('[data-action="filter"]').forEach(button => {
    button.classList.toggle('selected', button.dataset.filter === state.filter);
    button.setAttribute('aria-pressed', button.dataset.filter === state.filter);
  });
}

function renderTemplates() {
  document.querySelector('#main').innerHTML = `<div class="page-heading"><div><span class="eyebrow">SKIP THE BLANK PAGE</span><h1>A good place to start<span class="heading-dot">.</span></h1><p>Make one of these your own. Every question is editable before publishing.</p></div></div><div class="template-grid">${[
    ['blank', '01', 'Start from scratch', 'A clean canvas for whatever you’re curious about.', 'Your next good question'],
    ['customer', '02', 'Customer pulse', 'Understand what people love, and what needs a little work.', 'Listen. Learn. Improve.'],
    ['team', '03', 'Team check-in', 'Give your team room to share how things are going.', 'Make space for your people'],
    ['event', '04', 'Event feedback', 'Find out what landed and make the next event even better.', 'Keep the good things going'],
  ].map(([id, n, title, desc, subtitle]) => `<button class="template-card" data-action="template" data-template="${id}"><div class="template-art art-${id}"><span>${n} /</span><strong>${subtitle}</strong><div class="template-decor" aria-hidden="true">${id === 'customer' ? '◉' : id === 'team' ? '✳' : id === 'event' ? '↗' : '+'}</div></div><div class="template-content"><h2>${title} ${icon('arrow')}</h2><p>${desc}</p><span>${templates[id].questions.length || 'Your'} questions <span class="small-dot">·</span> Ready to customize</span></div></button>`).join('')}</div>`;
}

function newSurveyDialog(templateId = 'blank') {
  const template = templates[templateId];
  state.pendingTemplate = templateId;
  showModal(`${modalHeader('A new conversation', 'Give your survey a name. You can refine the questions next.')}<form id="create-survey-form"><label for="new-title">Survey title</label><input id="new-title" name="title" maxlength="200" required value="${templateId === 'blank' ? '' : e(template.title)}" placeholder="What would you like to learn?"><label for="new-mode">Respondent identity</label><select id="new-mode" name="respondent_mode"><option value="anonymous">Anonymous — don’t collect names</option><option value="named">Named — ask each respondent for a name</option></select><div class="modal-actions"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Create survey ${icon('arrow')}</button></div></form>`);
}

function renderBuilder() {
  const s = state.survey;
  const locked = s.status !== 'draft';
  document.querySelector('#main').innerHTML = `<a class="back-link" href="#/surveys">← All surveys</a><div class="builder-heading"><div><div class="heading-with-status"><h1>${locked ? e(s.title) : 'Make it your own'}<span class="heading-dot">.</span></h1>${statusBadge(s.status)}</div><p>${locked ? 'Your published questions are preserved so every response stays consistent.' : 'A little thought now makes for better answers later.'}</p></div><div class="heading-actions"><button class="button secondary" data-action="preview">${icon('eye')} Preview</button>${!locked ? '<button class="button secondary" type="submit" form="builder-form" id="save-button">Save draft</button><button class="button primary" data-action="publish">Publish & share ↗</button>' : `<a class="button secondary" href="#/results/${s.id}">${icon('chart')} Results</a><button class="button primary" data-action="share">${icon('link')} Share survey</button>`}</div></div>
    <div class="builder-layout"><form id="builder-form" class="builder-canvas"><section class="editor-intro"><span class="eyebrow">THE FIRST IMPRESSION</span><label for="survey-title">Survey title</label><input id="survey-title" data-survey-field="title" value="${e(s.title)}" maxlength="200" required${locked ? ' disabled' : ''}><label for="survey-description">Description <span class="optional">Optional</span></label><textarea id="survey-description" data-survey-field="description" rows="3" maxlength="4000" placeholder="A short introduction. Why are you asking?"${locked ? ' disabled' : ''}>${e(s.description)}</textarea></section>
      ${s.questions.map((q, i) => editorQuestion(q, i, locked)).join('')}
      ${!locked ? `<div class="add-question-panel"><span class="eyebrow">KEEP THE CONVERSATION GOING</span><h3>Add a question</h3><div class="question-type-grid">${Object.entries(types).map(([type, [label, glyph]]) => `<button type="button" data-action="add-question" data-type="${type}"${s.questions.length >= 50 ? ' disabled' : ''}><span>${glyph}</span>${label} <b>+</b></button>`).join('')}</div></div>` : ''}
    </form><aside class="builder-aside"><div class="aside-card"><h3>Survey settings</h3><label for="survey-mode">Respondent identity</label><select id="survey-mode" data-survey-field="respondent_mode"${locked ? ' disabled' : ''}><option value="anonymous"${s.respondent_mode === 'anonymous' ? ' selected' : ''}>Anonymous</option><option value="named"${s.respondent_mode === 'named' ? ' selected' : ''}>Named responses</option></select><p class="help-text">${s.respondent_mode === 'anonymous' ? 'Names and identifying metadata are not collected. Answers themselves may contain personal information.' : 'Each response includes a self-reported name. Names are not verified.'}</p><div class="aside-divider"></div><div class="aside-metric"><span>Questions</span><strong>${s.questions.length}<small> / 50</small></strong></div><div class="aside-metric"><span>Responses</span><a href="#/results/${s.id}">${number(s.response_count)} ↗</a></div><p class="saved-note" id="save-state">${state.dirty ? '● Unsaved changes' : `Saved ${date(s.updated_at)}`}</p></div>
      ${locked ? `<div class="aside-card"><h3>Manage survey</h3><p class="help-text">Duplicate this survey to edit questions for a new round of responses.</p><button class="button secondary full" data-action="duplicate">${icon('copy')} Duplicate survey</button><button class="button secondary full" data-action="${s.status === 'closed' ? 'reopen' : 'close-survey'}">${s.status === 'closed' ? 'Reopen for responses' : 'Close for responses'}</button></div>` : '<div class="writing-tip"><span>✳</span><h3>Keep it human.</h3><p>Short, clear questions are easier to answer. Ask one thing at a time.</p></div>'}
    </aside></div>`;
}

function editorQuestion(q, i, locked) {
  const disabled = locked ? ' disabled' : '';
  return `<section class="question-editor" id="editor-${q.id}"><div class="question-editor-top"><span class="question-number">QUESTION ${String(i + 1).padStart(2, '0')}</span><div>${!locked ? `<button type="button" class="icon-button" data-action="move-up" data-q="${q.id}" aria-label="Move question ${i + 1} up"${i === 0 ? ' disabled' : ''}>↑</button><button type="button" class="icon-button" data-action="move-down" data-q="${q.id}" aria-label="Move question ${i + 1} down"${i === state.survey.questions.length - 1 ? ' disabled' : ''}>↓</button><button type="button" class="icon-button" data-action="remove-question" data-q="${q.id}" aria-label="Remove question ${i + 1}">${icon('trash')}</button>` : icon('lock')}</div></div>
    <label class="sr-only" for="title-${q.id}">Question ${i + 1} title</label><input class="question-title-input" id="title-${q.id}" data-q="${q.id}" data-question-field="title" value="${e(q.title)}" required maxlength="240" placeholder="What would you like to ask?"${disabled}>
    <div class="question-controls"><label class="type-control"><span class="sr-only">Question ${i + 1} type</span><select data-q="${q.id}" data-question-field="type"${disabled}>${Object.entries(types).map(([type, [label]]) => `<option value="${type}"${q.type === type ? ' selected' : ''}>${label}</option>`).join('')}</select></label><label class="required-toggle"><input type="checkbox" data-q="${q.id}" data-question-field="required"${q.required ? ' checked' : ''}${disabled}><span>Required</span></label></div>
    <label class="sr-only" for="help-${q.id}">Question ${i + 1} help text</label><input class="help-input" id="help-${q.id}" data-q="${q.id}" data-question-field="help_text" value="${e(q.help_text)}" maxlength="1000" placeholder="Add a little guidance (optional)"${disabled}>
    ${['single_choice', 'multiple_choice'].includes(q.type) ? `<div class="options-editor">${q.options.map((option, j) => `<div class="option-editor-row"><span aria-hidden="true">${q.type === 'single_choice' ? '○' : '□'}</span><label class="sr-only" for="option-${q.id}-${j}">Question ${i + 1} option ${j + 1}</label><input id="option-${q.id}-${j}" data-q="${q.id}" data-option="${j}" value="${e(option)}" maxlength="200" required${disabled}>${!locked ? `<button type="button" class="icon-button" data-action="remove-option" data-q="${q.id}" data-option-index="${j}" aria-label="Remove option ${j + 1}"${q.options.length <= 2 ? ' disabled' : ''}>×</button>` : ''}</div>`).join('')}${!locked && q.options.length < 30 ? `<button class="text-button" type="button" data-action="add-option" data-q="${q.id}">+ Add option</button>` : ''}</div>` : q.type === 'rating' ? `<label class="range-control">Rating scale <select data-q="${q.id}" data-question-field="max_value"${disabled}>${Array.from({ length: 8 }, (_, j) => j + 3).map(n => `<option value="${n}"${q.max_value === n ? ' selected' : ''}>1 to ${n}</option>`).join('')}</select></label>` : q.type === 'number' ? `<div class="number-bounds"><label>Minimum <input type="number" step="any" data-q="${q.id}" data-question-field="min_value" value="${q.min_value ?? ''}"${disabled}></label><label>Maximum <input type="number" step="any" data-q="${q.id}" data-question-field="max_value" value="${q.max_value ?? ''}"${disabled}></label></div>` : '<div class="answer-placeholder">An answer will go here.</div>'}
  </section>`;
}

function markDirty() {
  state.dirty = true;
  const saved = document.querySelector('#save-state');
  if (saved) saved.textContent = '● Unsaved changes';
}

async function saveDraft() {
  if (!document.querySelector('#builder-form').reportValidity()) return false;
  const s = state.survey;
  state.survey = await api(`/surveys/${s.id}`, { method: 'PUT', body: { title: s.title, description: s.description, respondent_mode: s.respondent_mode, questions: s.questions, revision: s.revision } });
  state.dirty = false;
  renderBuilder();
  return true;
}

function shareDialog(survey) {
  const url = location.origin + survey.public_path;
  const embed = `<iframe src="${url}?embed=1" title="${e(survey.title)}" width="100%" height="800" frameborder="0" loading="lazy"></iframe>`;
  showModal(`${modalHeader('Let your questions travel', survey.status === 'closed' ? 'This survey is closed. Reopen it to accept responses.' : 'Anyone with this link can respond. Your results stay private.')}<label for="share-url">Survey link</label><div class="copy-input"><input id="share-url" readonly value="${e(url)}"><button class="button secondary" data-action="copy-link">${icon('copy')} Copy</button></div><label for="embed-code">Embed in your website</label><textarea id="embed-code" readonly rows="4">${e(embed)}</textarea><div class="modal-actions"><a class="button secondary" href="${e(url)}" target="_blank" rel="noopener">Open survey ↗</a><button class="button primary" data-action="copy-embed">Copy embed code</button></div>`);
}

async function loadResults(id, version = routeVersion) {
  const [survey, summary, responses] = await Promise.all([
    api(`/surveys/${id}`), api(`/surveys/${id}/summary`), api(`/surveys/${id}/responses?limit=25&offset=${state.responseOffset}`),
  ]);
  if (version !== routeVersion) return;
  state.survey = survey; state.summary = summary; state.responses = responses;
  renderResults();
}

function renderResults() {
  const s = state.survey;
  document.querySelector('#main').innerHTML = `<a class="back-link" href="#/surveys">← All surveys</a><div class="page-heading"><div><span class="eyebrow">LISTENING IS THE INTERESTING PART</span><h1>${e(s.title)}<span class="heading-dot">.</span></h1><p>${number(state.summary.total)} response${state.summary.total !== 1 ? 's' : ''} <span class="small-dot">·</span> ${s.respondent_mode === 'anonymous' ? 'Anonymous' : 'Named responses'} <span class="small-dot">·</span> ${statusBadge(s.status)}</p></div><div class="heading-actions"><button class="button secondary" data-action="refresh-results">Refresh</button><button class="button secondary" data-action="export-json">JSON ↓</button><button class="button primary" data-action="export-csv">Export CSV ↓</button></div></div>
    <div class="results-tabs tabs" role="group" aria-label="Results view"><button class="tab${state.resultsTab === 'summary' ? ' selected' : ''}" data-action="results-summary" aria-pressed="${state.resultsTab === 'summary'}">${icon('chart')} Summary</button><button class="tab${state.resultsTab === 'individual' ? ' selected' : ''}" data-action="results-individual" aria-pressed="${state.resultsTab === 'individual'}">Individual responses <span class="count-badge">${number(state.responses.total)}</span></button><a class="text-link" href="#/builder/${s.id}">View survey ↗</a></div>
    ${!state.responses.total ? `<div class="empty-panel"><div class="empty-symbol">${icon('chart')}</div><h2>Good answers are on their way.</h2><p>${s.status === 'draft' ? 'Publish your survey, then share it to start collecting responses.' : 'Share your survey link and give people room to respond.'}</p>${s.status === 'draft' ? `<a class="button secondary" href="#/builder/${s.id}">Open survey builder ↗</a>` : '<button class="button secondary" data-action="share">Share survey ↗</button>'}</div>` : state.resultsTab === 'summary' ? `<div class="summary-grid">${state.summary.questions.map((q, i) => summaryCard(q, i)).join('')}</div>` : responseTable()}`;
}

function summaryCard(q, i) {
  const choices = Object.entries(q.counts);
  const texts = state.responses.items.filter(r => q.question_id in r.answers).slice(0, 4);
  return `<section class="summary-card"><div class="summary-card-top"><span class="eyebrow">QUESTION ${String(i + 1).padStart(2, '0')}</span><span>${q.answered} answered</span></div><h2>${e(q.title)}</h2><p class="summary-type">${types[q.type][0]}</p>
    ${q.average !== null ? `<div class="average-value">${number(q.average)}${q.type === 'rating' ? `<span> / ${state.survey.questions[i].max_value}</span>` : ''}<small>Average answer</small></div>` : ''}
    ${choices.length ? `<div class="answer-bars">${choices.map(([label, count]) => `<div><div class="answer-bar-label"><span>${e(label)}</span><strong>${number(count)} <small>(${q.answered ? Math.round(count / q.answered * 100) : 0}%)</small></strong></div><progress max="${Math.max(q.answered, 1)}" value="${count}" aria-label="${e(label)}: ${count} of ${q.answered}"></progress></div>`).join('')}</div>${q.type === 'multiple_choice' ? '<p class="help-text">Respondents can choose more than one option.</p>' : ''}` : q.type !== 'number' ? `<div class="text-answers">${texts.map(r => `<p>${e(r.answers[q.question_id])}</p>`).join('') || '<p class="muted">No answers to this question yet.</p>'}</div><button class="text-button" data-action="results-individual">View individual responses ↗</button><p class="help-text">Showing up to four answers from the latest loaded responses.</p>` : ''}
  </section>`;
}

function responseTable() {
  return `<div class="table-wrap responses-table-wrap"><table class="responses-table"><thead><tr><th>Response</th><th>${state.survey.respondent_mode === 'named' ? 'Respondent' : 'Identity'}</th><th>Submitted</th><th></th></tr></thead><tbody>${state.responses.items.map((r, i) => `<tr><td><button class="text-button" data-action="response-detail" data-id="${r.id}">Response ${state.responses.total - state.responseOffset - i} ↗</button></td><td>${e(r.respondent_name || 'Anonymous')}</td><td>${date(r.submitted_at, true)}</td><td><button class="icon-button danger-text" data-action="delete-response" data-id="${r.id}" aria-label="Delete response ${state.responses.total - state.responseOffset - i}">${icon('trash')}</button></td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${state.responseOffset + 1}–${state.responseOffset + state.responses.items.length} of ${number(state.responses.total)} responses</span><div><button class="button small secondary" data-action="response-prev"${!state.responseOffset ? ' disabled' : ''}>← Previous</button><button class="button small secondary" data-action="response-next"${state.responseOffset + state.responses.items.length >= state.responses.total ? ' disabled' : ''}>Next →</button></div></div>`;
}

function responseDetail(id) {
  const r = state.responses.items.find(item => item.id === id);
  showModal(`${modalHeader(r.respondent_name || 'Anonymous response', date(r.submitted_at, true))}<div class="response-details">${state.survey.questions.map((q, i) => `<section><span class="eyebrow">QUESTION ${i + 1}</span><h3>${e(q.title)}</h3><p class="preserve-lines">${q.id in r.answers ? e(Array.isArray(r.answers[q.id]) ? r.answers[q.id].join(', ') : r.answers[q.id]) : '<span class="muted">No answer provided</span>'}</p></section>`).join('')}</div><div class="modal-actions"><button class="button secondary" data-action="close-modal">Done</button></div>`);
}

function renderIntegrations() {
  document.querySelector('#main').innerHTML = `<div class="page-heading"><div><span class="eyebrow">MAKE SURVEYS PART OF YOUR PLATFORM</span><h1>Connect your world<span class="heading-dot">.</span></h1><p>The same survey engine. Wherever your application lives.</p></div><button class="button primary" data-action="new-key">${icon('plus')} Create API key</button></div>
    <div class="integration-intro"><div><span class="eyebrow">ONE API. LOTS OF POSSIBILITIES.</span><h2>Small API.<br>Big conversations.</h2><p>Create surveys, render them in your own interface, and collect responses over standard HTTP and JSON.</p><div class="language-tags"><span>Python</span><span>Java</span><span>JavaScript</span><span>Any HTTP client</span></div><a class="text-link" href="/docs" target="_blank" rel="noopener">Explore the API documentation ↗</a></div><div class="code-card"><div><span>YOUR API ENDPOINT</span><button class="icon-button" data-action="copy-api" aria-label="Copy API base URL">${icon('copy')}</button></div><code>${e(location.origin)}/api/v1</code><pre><code>${e(`curl '${location.origin}/api/v1/surveys' \\n  -H 'X-API-Key: YOUR_API_KEY'`)}</code></pre><p>Keep administrative keys in your server. Public survey endpoints can be used in a browser without a key.</p></div></div>
    <div class="section-heading"><h2>API keys</h2><span>${state.keys.length} active</span></div>
    ${state.keys.length ? `<div class="table-wrap keys-table-wrap"><table><thead><tr><th>Name</th><th>Key prefix</th><th>Permissions</th><th>Created</th><th></th></tr></thead><tbody>${state.keys.map(k => `<tr><td><strong>${e(k.name)}</strong></td><td><code>${e(k.prefix)}…</code></td><td><div class="scope-tags">${k.scopes.map(scope => `<span>${e(scope)}</span>`).join('')}</div></td><td>${date(k.created_at)}</td><td><button class="text-button danger-text" data-action="revoke-key" data-id="${k.id}">Revoke</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty-keys"><span class="empty-symbol">⌘</span><div><h3>Give your first integration a key.</h3><p>Choose just the permissions it needs. You can revoke access any time.</p></div><button class="button secondary" data-action="new-key">Create API key ↗</button></div>'}
    <div class="integration-options"><section><h3>${icon('link')} Embed a survey</h3><p>Copy an iframe from any published survey’s Share dialog. Responses go straight to your workspace.</p></section><section><h3>${icon('code')} Build your own interface</h3><p>Read a public survey’s questions and submit answers through the public API. Review results using a scoped key on your server.</p></section></div>`;
}

function newKeyDialog() {
  showModal(`${modalHeader('A key for your integration', 'Use the smallest set of permissions your service needs.')}<form id="create-key-form"><label for="key-name">Integration name</label><input id="key-name" name="name" required maxlength="100" placeholder="e.g. Customer portal"><fieldset class="key-permissions"><legend>Permissions</legend>${[
    ['surveys:read', 'Read surveys', 'List surveys and read their definitions'],
    ['surveys:write', 'Manage surveys', 'Create, edit, duplicate, publish, and close surveys'],
    ['responses:read', 'Read responses', 'View summaries and export response data'],
    ['responses:delete', 'Delete response data', 'Delete responses; also required to delete surveys'],
  ].map(([scope, title, description], i) => `<label class="permission-choice"><input type="checkbox" name="scopes" value="${scope}"${i === 0 ? ' checked' : ''}><span><strong>${title}</strong><small>${description}</small></span></label>`).join('')}</fieldset><div class="modal-actions"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Generate key ↗</button></div></form>`);
}

async function openPublic(token) {
  root.innerHTML = '<main id="main" class="public-page"><div class="loading-state"><span class="spinner"></span> Opening your survey…</div></main>';
  try {
    const survey = await api(`/public/surveys/${token}`, { publicRequest: true });
    document.title = `${survey.title} · Survey Machine`;
    const embedded = new URLSearchParams(location.search).get('embed') === '1';
    document.querySelector('#main').innerHTML = surveyForm(survey, { embedded });
    const submissionId = crypto.randomUUID();
    document.querySelector('#response-form').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.target;
      const button = form.querySelector('button[type="submit"]');
      const errorNode = document.querySelector('#response-error');
      document.querySelectorAll('.field-error').forEach(node => { node.textContent = ''; });
      errorNode.textContent = '';
      button.disabled = true; button.textContent = 'Sending your response…';
      const body = { submission_id: submissionId, answers: readAnswers(form, survey.questions) };
      if (survey.respondent_mode === 'named') body.respondent_name = new FormData(form).get('respondent_name');
      try {
        await api(`/public/surveys/${token}/responses`, { method: 'POST', body, publicRequest: true });
        document.querySelector('#main').innerHTML = `<div class="respondent${embedded ? ' embedded' : ''}"><div class="submission-success"><div class="success-mark">${icon('check')}</div><span class="eyebrow">A LITTLE MORE PERSPECTIVE</span><h1>You’ve been heard.</h1><p>Your response to <strong>${e(survey.title)}</strong> has been recorded. Thank you for taking the time.</p><span class="success-brand"><img src="/mark.svg" alt=""> Survey Machine</span></div></div>`;
      } catch (error) {
        errorNode.textContent = error.message;
        for (const [id, message] of Object.entries(error.fields || {})) {
          const field = document.getElementById(`error-${id}`);
          if (field) field.textContent = message;
        }
        const first = Object.keys(error.fields || {}).map(id => document.getElementById(`field-${id}`)).find(Boolean);
        if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); first.querySelector('input, textarea')?.focus({ preventScroll: true }); }
        button.disabled = false; button.innerHTML = 'Submit response <span aria-hidden="true">↗</span>';
      }
    });
  } catch (error) {
    document.querySelector('#main').innerHTML = `<div class="respondent"><div class="submission-success"><div class="empty-symbol">${icon(error.status === 410 ? 'lock' : 'link')}</div><h1>${error.status === 410 ? 'This conversation has closed.' : 'This survey is unavailable.'}</h1><p>${e(error.message)}</p><span class="success-brand"><img src="/mark.svg" alt=""> Survey Machine</span></div></div>`;
  }
}

document.addEventListener('input', event => {
  const node = event.target;
  if (!state.survey || !node.dataset) return;
  if (node.dataset.surveyField) { state.survey[node.dataset.surveyField] = node.value; markDirty(); }
  if (node.dataset.q) {
    const q = state.survey.questions.find(q => q.id === node.dataset.q);
    if (!q) return;
    if (node.dataset.option !== undefined) q.options[Number(node.dataset.option)] = node.value;
    else if (node.dataset.questionField && node.dataset.questionField !== 'type') {
      const field = node.dataset.questionField;
      q[field] = field === 'required' ? node.checked : ['min_value', 'max_value'].includes(field) ? (node.value === '' ? null : Number(node.value)) : node.value;
    }
    markDirty();
  }
});

document.addEventListener('change', event => {
  const node = event.target;
  if (node.dataset.questionField === 'type') {
    const q = state.survey.questions.find(q => q.id === node.dataset.q);
    Object.assign(q, newQuestion(node.value, { id: q.id, title: q.title, help_text: q.help_text, required: q.required }));
    markDirty(); renderBuilder();
  } else if (node.dataset.surveyField === 'respondent_mode') { renderBuilder(); }
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!['login-form', 'create-survey-form', 'create-key-form', 'builder-form', 'search-form'].includes(form.id)) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]') || document.querySelector('#save-button');
  if (button?.disabled) return;
  if (button) button.disabled = true;
  try {
    if (form.id === 'login-form') {
      setKey(new FormData(form).get('key'));
      await api('/auth/check');
      state.unlocked = true;
      await route();
    } else if (form.id === 'create-survey-form') {
      const values = new FormData(form);
      const template = templates[state.pendingTemplate];
      const s = await api('/surveys', { method: 'POST', body: { title: values.get('title'), respondent_mode: values.get('respondent_mode'), description: template.description, questions: template.questions.map(q => newQuestion(q.type, q)) } });
      closeModal(); state.dirty = false; location.hash = `#/builder/${s.id}`;
    } else if (form.id === 'create-key-form') {
      const values = new FormData(form);
      if (!values.getAll('scopes').length) { notify('Choose at least one permission.', true); return; }
      const key = await api('/api-keys', { method: 'POST', body: { name: values.get('name'), scopes: values.getAll('scopes') } });
      state.keys.unshift(key); renderIntegrations();
      showModal(`${modalHeader('Your integration is ready', 'Copy this key now. You won’t be able to view it again.')}<label for="new-api-key">API key for ${e(key.name)}</label><div class="copy-input"><input id="new-api-key" readonly value="${e(key.key)}"><button class="button secondary" data-action="copy-new-key">Copy</button></div><p class="help-text">Store this key as a secret on your server. It has access to: ${e(key.scopes.join(', '))}.</p><div class="modal-actions"><button class="button primary" data-action="close-modal">I’ve saved my key</button></div>`);
      // Keep only the prefix and permissions in the rendered key list.
      delete state.keys[0].key;
    } else if (form.id === 'builder-form') {
      if (await saveDraft()) notify('Your draft is saved.');
    } else if (form.id === 'search-form') {
      state.search = String(new FormData(form).get('search')).trim(); state.offset = 0; await refreshSurveys();
    }
  } catch (error) {
    if (form.id === 'login-form') { setKey(''); document.querySelector('#login-error').textContent = error.message; }
    else notify(error.message, true);
  } finally { if (button?.isConnected) button.disabled = false; }
});

document.addEventListener('click', async event => {
  const link = event.target.closest('a[href^="#/"]');
  if (link && state.dirty) {
    if (!safeLeave()) { event.preventDefault(); return; }
    state.dirty = false;
  }
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  const qIndex = state.survey?.questions.findIndex(q => q.id === button.dataset.q);
  const q = qIndex >= 0 ? state.survey.questions[qIndex] : null;
  const asyncActions = ['publish', 'close-survey', 'reopen', 'duplicate', 'duplicate-row', 'delete-survey', 'delete-response', 'export-csv', 'export-json', 'revoke-key', 'refresh-results', 'response-next', 'response-prev', 'survey-next', 'survey-prev', 'filter'];
  if (asyncActions.includes(action)) button.disabled = true;
  try {
    switch (action) {
      case 'close-modal': closeModal(); break;
      case 'retry': await route(); break;
      case 'signout': if (safeLeave()) { setKey(''); state.unlocked = false; state.dirty = false; closeModal(); await route(); } break;
      case 'new-survey': newSurveyDialog(); break;
      case 'template': newSurveyDialog(button.dataset.template); break;
      case 'filter': state.filter = button.dataset.filter; state.offset = 0; await refreshSurveys(); break;
      case 'survey-next': state.offset += 25; await refreshSurveys(); break;
      case 'survey-prev': state.offset = Math.max(0, state.offset - 25); await refreshSurveys(); break;
      case 'add-question': state.survey.questions.push(newQuestion(button.dataset.type)); markDirty(); renderBuilder(); document.getElementById(`title-${state.survey.questions.at(-1).id}`)?.focus(); break;
      case 'remove-question': state.survey.questions.splice(qIndex, 1); markDirty(); renderBuilder(); break;
      case 'move-up': [state.survey.questions[qIndex - 1], state.survey.questions[qIndex]] = [q, state.survey.questions[qIndex - 1]]; markDirty(); renderBuilder(); break;
      case 'move-down': [state.survey.questions[qIndex + 1], state.survey.questions[qIndex]] = [q, state.survey.questions[qIndex + 1]]; markDirty(); renderBuilder(); break;
      case 'add-option': q.options.push(`Option ${q.options.length + 1}`); markDirty(); renderBuilder(); break;
      case 'remove-option': q.options.splice(Number(button.dataset.optionIndex), 1); markDirty(); renderBuilder(); break;
      case 'preview': showModal(`${modalHeader('A respondent’s view')}<div class="preview-content">${surveyForm(state.survey, { preview: true, embedded: true })}</div>`); break;
      case 'publish':
        if (!state.survey.questions.length) { notify('Add at least one question before publishing.', true); break; }
        if (!document.querySelector('#builder-form').reportValidity()) break;
        if (!confirm('Publishing locks the questions and identity settings for this survey. You can duplicate it to make changes later. Publish now?')) break;
        if (!await saveDraft()) break;
        state.survey = await api(`/surveys/${state.survey.id}/publish`, { method: 'POST' }); renderBuilder(); shareDialog(state.survey); break;
      case 'close-survey':
        if (!confirm('Close this survey? It will stop accepting responses. You can reopen it later.')) break;
        state.survey = await api(`/surveys/${state.survey.id}/close`, { method: 'POST' }); renderBuilder(); notify('Survey closed.'); break;
      case 'reopen': state.survey = await api(`/surveys/${state.survey.id}/publish`, { method: 'POST' }); renderBuilder(); notify('Your survey is open again.'); break;
      case 'share': shareDialog(state.survey); break;
      case 'share-row': shareDialog(state.surveys.find(s => s.id === button.dataset.id)); break;
      case 'duplicate':
      case 'duplicate-row': {
        if (!safeLeave()) break;
        const s = await api(`/surveys/${button.dataset.id || state.survey.id}/duplicate`, { method: 'POST' });
        state.dirty = false; location.hash = `#/builder/${s.id}`; notify('A fresh copy is ready to edit.'); break;
      }
      case 'delete-survey': {
        const s = state.surveys.find(s => s.id === button.dataset.id);
        if (!confirm(`Permanently delete “${s.title}” and all ${s.response_count} responses?`)) break;
        await api(`/surveys/${s.id}`, { method: 'DELETE' }); await route(); notify('Survey deleted.'); break;
      }
      case 'copy-link': await copy(document.querySelector('#share-url').value, document.querySelector('#share-url')); break;
      case 'copy-embed': await copy(document.querySelector('#embed-code').value, document.querySelector('#embed-code')); break;
      case 'results-summary': state.resultsTab = 'summary'; renderResults(); break;
      case 'results-individual': state.resultsTab = 'individual'; renderResults(); break;
      case 'refresh-results': await loadResults(state.survey.id); break;
      case 'response-next': state.responseOffset += 25; await loadResults(state.survey.id); break;
      case 'response-prev': state.responseOffset = Math.max(0, state.responseOffset - 25); await loadResults(state.survey.id); break;
      case 'response-detail': responseDetail(button.dataset.id); break;
      case 'delete-response':
        if (!confirm('Permanently delete this response? It will also be removed from summaries and exports.')) break;
        await api(`/surveys/${state.survey.id}/responses/${button.dataset.id}`, { method: 'DELETE' });
        if (state.responses.items.length === 1 && state.responseOffset) state.responseOffset = Math.max(0, state.responseOffset - 25);
        await loadResults(state.survey.id); notify('Response deleted.'); break;
      case 'export-csv': await download(state.survey.id, 'csv'); notify('CSV exported.'); break;
      case 'export-json': await download(state.survey.id, 'json'); notify('JSON exported.'); break;
      case 'new-key': newKeyDialog(); break;
      case 'copy-new-key': await copy(document.querySelector('#new-api-key').value, document.querySelector('#new-api-key')); break;
      case 'copy-api': await copy(`${location.origin}/api/v1`); break;
      case 'revoke-key':
        if (!confirm('Revoke this key? Its integration will immediately lose access.')) break;
        await api(`/api-keys/${button.dataset.id}`, { method: 'DELETE' });
        state.keys = state.keys.filter(k => k.id !== button.dataset.id); renderIntegrations(); notify('API key revoked.'); break;
    }
  } catch (error) { notify(error.message, true); }
  finally { if (button.isConnected && asyncActions.includes(action)) button.disabled = false; }
});

window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
let lastHash = location.hash;
window.addEventListener('hashchange', () => {
  if (state.dirty && !safeLeave()) { history.replaceState(null, '', lastHash || '/'); return; }
  lastHash = location.hash; route();
});
const publicMatch = location.pathname.match(/^\/s\/([A-Za-z0-9_-]{32})$/);
if (publicMatch) openPublic(publicMatch[1]);
else route();
