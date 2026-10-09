let workspaceKey = '';

export function setKey(key) { workspaceKey = key; }

export class ApiError extends Error {
  constructor(status, detail) {
    let message = 'The request could not be completed.';
    if (typeof detail === 'string') message = detail;
    else if (Array.isArray(detail)) message = detail.map(e => `${e.loc?.slice(1).join(' → ') || 'Input'}: ${e.msg}`).join('\n');
    else if (detail?.message) message = detail.message;
    super(message);
    this.status = status;
    this.fields = detail?.fields || {};
  }
}

export async function api(path, { method = 'GET', body, publicRequest = false } = {}) {
  const headers = {};
  if (!publicRequest && workspaceKey) headers['X-API-Key'] = workspaceKey;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, 'Could not reach Survey Machine. Check your connection and try again.');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(response.status, error.detail);
  }
  return response.status === 204 ? null : response.json();
}

export async function download(surveyId, format) {
  const response = await fetch(`/api/v1/surveys/${surveyId}/export?format=${format}`, { headers: { 'X-API-Key': workspaceKey } });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(response.status, error.detail);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `survey-${surveyId}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function escape(value = '') {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

export function notify(message, error = false) {
  const node = document.createElement('div');
  node.className = `toast${error ? ' toast-error' : ''}`;
  node.textContent = message;
  document.querySelector('#notifications').append(node);
  setTimeout(() => node.remove(), error ? 8500 : 4500);
}

export async function copy(text, input) {
  try { await navigator.clipboard.writeText(text); notify('Copied to clipboard.'); }
  catch { if (input) { input.focus(); input.select(); } notify('Select the text and copy it with your keyboard.'); }
}
