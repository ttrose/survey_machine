import { escape as e } from './api.js';

export const types = {
  short_text: ['Short answer', 'Aa'], long_text: ['Long answer', '¶'],
  single_choice: ['Single choice', '◉'], multiple_choice: ['Multiple choice', '☑'],
  rating: ['Rating', '☆'], email: ['Email address', '@'], number: ['Number', '#'], date: ['Date', '▦'],
};

export const templates = {
  blank: { title: 'Untitled survey', description: '', questions: [] },
  customer: { title: 'Customer pulse', description: 'A few quick questions to help us make your experience better.', questions: [
    { type: 'rating', title: 'How was your overall experience?', required: true },
    { type: 'single_choice', title: 'What matters most to you?', options: ['Ease of use', 'Quality', 'Value', 'Support'], required: true },
    { type: 'long_text', title: 'What could we do better?' },
  ] },
  team: { title: 'Team check-in', description: 'Help us understand how things are going. This survey is anonymous.', questions: [
    { type: 'rating', title: 'How are you feeling about work this week?', required: true },
    { type: 'multiple_choice', title: 'Where would more support help?', options: ['Workload', 'Communication', 'Tools', 'Learning opportunities'] },
    { type: 'long_text', title: 'Is there anything else you would like to share?' },
  ] },
  event: { title: 'Event feedback', description: 'Thanks for joining us! Tell us what worked and what we can improve.', questions: [
    { type: 'rating', title: 'How would you rate the event?', required: true },
    { type: 'single_choice', title: 'Would you attend again?', options: ['Yes', 'Maybe', 'No'], required: true },
    { type: 'long_text', title: 'What should we do differently next time?' },
  ] },
};

export function newQuestion(type = 'short_text', data = {}) {
  return { id: crypto.randomUUID(), type, title: '', help_text: '', required: false,
    options: ['single_choice', 'multiple_choice'].includes(type) ? ['Option 1', 'Option 2'] : [],
    min_value: type === 'rating' ? 1 : null, max_value: type === 'rating' ? 5 : null, ...data };
}

export function questionInput(q, { disabled = false, prefix = 'q', value } = {}) {
  const id = `${prefix}-${q.id}`;
  const dis = disabled ? ' disabled' : '';
  const req = q.required ? ' required' : '';
  const help = q.help_text ? ` aria-describedby="help-${id}"` : '';
  const common = `id="${id}" name="${e(q.id)}" aria-label="${e(q.title)}"${dis}${req}${help}`;
  const val = `value="${e(value ?? '')}"`;
  switch (q.type) {
    case 'long_text': return `<textarea ${common} maxlength="8000" rows="4" placeholder="Write your answer here…">${e(value ?? '')}</textarea>`;
    case 'single_choice':
    case 'multiple_choice': {
      const checkbox = q.type === 'multiple_choice';
      return `<div class="choice-list">${q.options.map((option, i) => `<label class="choice"><input type="${checkbox ? 'checkbox' : 'radio'}" name="${e(q.id)}" id="${id}-${i}" value="${e(option)}"${dis}${!checkbox ? req : ''}${help}${(checkbox ? (value || []).includes(option) : value === option) ? ' checked' : ''}><span>${e(option)}</span></label>`).join('')}</div>`;
    }
    case 'rating': return `<div class="rating-input">${Array.from({ length: q.max_value || 5 }, (_, i) => `<label><input type="radio" name="${e(q.id)}" value="${i + 1}"${dis}${req}${value === i + 1 ? ' checked' : ''}><span>${i + 1}</span></label>`).join('')}</div><div class="rating-labels"><span>Lowest</span><span>Highest</span></div>`;
    default: return `<input ${common} type="${q.type === 'short_text' ? 'text' : q.type}" ${val}${q.type === 'number' ? ` step="any"${q.min_value !== null ? ` min="${q.min_value}"` : ''}${q.max_value !== null ? ` max="${q.max_value}"` : ''}` : q.type === 'email' ? ' maxlength="254"' : q.type === 'short_text' ? ' maxlength="1000"' : ''} placeholder="${q.type === 'email' ? 'you@example.com' : q.type === 'number' ? 'Enter a number' : 'Your answer…'}">`;
  }
}

export function surveyForm(survey, { preview = false, embedded = false } = {}) {
  return `<div class="respondent${embedded ? ' embedded' : ''}">
    ${!embedded ? '<a class="respondent-brand" href="/" target="_blank" rel="noopener"><img src="/mark.svg" alt=""> Survey Machine</a>' : ''}
    <div class="form-card">
      <div class="form-accent"></div><div class="form-intro"><span class="eyebrow">${preview ? 'SURVEY PREVIEW' : 'YOUR PERSPECTIVE MATTERS'}</span><h1>${e(survey.title)}</h1>${survey.description ? `<p class="preserve-lines">${e(survey.description)}</p>` : ''}<div class="privacy-note">${survey.respondent_mode === 'anonymous' ? 'Anonymous · Your name is not collected.' : 'Named responses · Your name will be shared with the survey owner.'}</div></div>
      <form id="response-form">
        ${survey.respondent_mode === 'named' ? '<div class="public-question"><label class="question-label" for="respondent-name">Your name <span class="required-star">*</span></label><input id="respondent-name" name="respondent_name" maxlength="200" autocomplete="name" required placeholder="First and last name"></div>' : ''}
        ${survey.questions.map((q, i) => `<fieldset class="public-question" id="field-${q.id}"><legend class="question-label"><span class="question-index">${i + 1}.</span> ${e(q.title)}${q.required ? ' <span class="required-star">*</span>' : '<span class="optional">Optional</span>'}</legend>${q.help_text ? `<p class="help-text" id="help-q-${q.id}">${e(q.help_text)}</p>` : ''}${questionInput(q)}<p class="field-error" id="error-${q.id}"></p></fieldset>`).join('')}
        <div class="form-footer"><p class="form-error" id="response-error" role="alert"></p><button class="button primary" type="submit"${preview ? ' disabled' : ''}>${preview ? 'Preview only' : 'Submit response'} <span aria-hidden="true">↗</span></button><p>${preview ? 'No responses are collected in preview.' : 'Your answers are shared with the survey owner.'}</p></div>
      </form>
    </div>${!embedded ? '<p class="respondent-credit">Good questions. Useful answers.</p>' : ''}
  </div>`;
}

export function readAnswers(form, questions) {
  const values = new FormData(form);
  const answers = {};
  for (const q of questions) {
    if (q.type === 'multiple_choice') {
      const selected = values.getAll(q.id);
      if (selected.length) answers[q.id] = selected;
    } else {
      const value = values.get(q.id);
      if (value !== null && value !== '') answers[q.id] = ['rating', 'number'].includes(q.type) ? Number(value) : value;
    }
  }
  return answers;
}
