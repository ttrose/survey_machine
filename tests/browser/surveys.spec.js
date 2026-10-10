import { test, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const key = 'test-administrator-key-for-survey-machine-12345';
const password = 'A long browser test password 123!';
const operator = { 'X-API-Key': key };

async function customer(api, name = 'Riverside Studio') {
  const email = randomUUID() + '@example.com';
  const invite = await api.post('/api/v1/operator/customers', { headers: operator, data: { name, email } });
  expect(invite.status()).toBe(201);
  const invitation = await invite.json();
  const response = await api.post('/api/v1/auth/activate', { data: { email, password, token: invitation.activation_path.split('/').at(-1) } });
  expect(response.status()).toBe(200);
  return { ...(await response.json()), email, headers: { 'X-CSRF-Token': (await response.json()).csrf_token } };
}

test('operator invitation, customer survey, anonymous response, results and export', async ({ page, browser, baseURL }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('button', { name: 'Operator sign-in' }).click();
  await page.getByLabel('Operator key', { exact: true }).fill(key);
  await page.getByRole('button', { name: 'Open operator workspace' }).click();
  await page.getByRole('link', { name: 'Customers', exact: true }).click();
  await page.getByRole('button', { name: 'Invite customer' }).first().click();
  const email = randomUUID() + '@example.com';
  await page.getByLabel('Workspace name').fill('Riverside Studio');
  await page.getByLabel('Owner email').fill(email);
  await page.getByRole('button', { name: 'Create invitation' }).click();
  const invitation = await page.getByLabel('Invitation or recovery link').inputValue();

  const ownerContext = await browser.newContext({ baseURL });
  const owner = await ownerContext.newPage();
  owner.on('pageerror', error => errors.push(error.message));
  await owner.goto(invitation);
  await owner.getByLabel('Email', { exact: true }).fill(email);
  await owner.getByLabel('Choose a password').fill(password);
  await owner.getByLabel('Confirm password').fill(password);
  await owner.getByRole('button', { name: 'Save password & sign in' }).click();
  await expect(owner.getByRole('heading', { name: 'Your surveys.' })).toBeVisible();
  await owner.reload();
  await expect(owner.getByRole('heading', { name: 'Your surveys.' })).toBeVisible();
  await expect(owner.getByRole('link', { name: 'Customers', exact: true })).toHaveCount(0);
  await owner.getByRole('link', { name: 'Templates', exact: true }).click();
  await owner.getByRole('button', { name: /Customer pulse/ }).click();
  await owner.getByLabel('Survey title', { exact: true }).fill('The autumn customer pulse');
  await owner.getByRole('button', { name: 'Create survey' }).click();
  owner.once('dialog', dialog => dialog.accept());
  await owner.getByRole('button', { name: 'Publish & share' }).click();
  const url = await owner.getByLabel('Survey link', { exact: true }).inputValue();
  const embed = await owner.getByLabel('Embed in your website').inputValue();
  expect(embed).toContain('?embed=1');

  const respondent = await browser.newContext({ baseURL });
  const form = await respondent.newPage();
  await form.goto(url);
  await expect(form.getByText('Anonymous · Your name is not collected.')).toBeVisible();
  await form.getByRole('radio', { name: '5', exact: true }).check();
  await form.getByLabel('Quality', { exact: true }).check();
  await form.getByLabel('What could we do better?').fill('Keep listening to customers.');
  await form.getByRole('button', { name: 'Submit response' }).click();
  await expect(form.getByRole('heading', { name: 'You’ve been heard.' })).toBeVisible();

  await owner.getByRole('button', { name: 'Close dialog' }).click();
  await owner.getByRole('link', { name: 'Results', exact: true }).click();
  await expect(owner.getByText('1 response', { exact: false }).first()).toBeVisible();
  await expect(owner.getByText('Keep listening to customers.')).toBeVisible();
  const downloadPromise = owner.waitForEvent('download');
  await owner.getByRole('button', { name: 'Export CSV' }).click();
  const download = await downloadPromise;
  let csv = '';
  for await (const chunk of await download.createReadStream()) csv += chunk;
  expect(csv).toContain('Keep listening to customers.');
  expect(csv).not.toContain(email);
  await owner.getByRole('link', { name: 'View survey' }).click();
  owner.once('dialog', dialog => dialog.accept());
  await owner.getByRole('button', { name: 'Close for responses' }).click();
  await form.goto(url);
  await expect(form.getByRole('heading', { name: 'This conversation has closed.' })).toBeVisible();
  await owner.getByRole('button', { name: 'Reopen for responses' }).click();
  await form.goto(url + '?embed=1');
  await expect(form.getByRole('button', { name: 'Submit response' })).toBeVisible();
  await owner.getByRole('button', { name: 'Sign out', exact: true }).click();
  await owner.reload();
  await expect(owner.getByRole('button', { name: 'Sign in', exact: false }).first()).toBeVisible();
  expect(errors).toEqual([]);
  await ownerContext.close();
  await respondent.close();
});

test('named survey supports every question type on a mobile screen', async ({ page }) => {
  const owner = await customer(page.request);
  const questions = [
    { type: 'short_text', title: 'A short answer', required: true },
    { type: 'long_text', title: 'Tell us more', required: true },
    { type: 'email', title: 'Contact email', required: true },
    { type: 'number', title: 'Number of visits', min_value: 0, max_value: 20, required: true },
    { type: 'date', title: 'Visit date', required: true },
    { type: 'single_choice', title: 'Choose one', options: ['One', 'Two'], required: true },
    { type: 'multiple_choice', title: 'Choose several', options: ['Red', 'Blue'], required: true },
    { type: 'rating', title: 'Your rating', required: true },
  ];
  const created = await page.request.post('/api/v1/surveys', { headers: owner.headers, data: { title: 'A complete visit', respondent_mode: 'named', questions } });
  expect(created.status()).toBe(201);
  const survey = await created.json();
  expect((await page.request.post('/api/v1/surveys/' + survey.id + '/publish', { headers: owner.headers })).ok()).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(survey.public_path);
  await page.getByLabel('Your name').fill('Taylor');
  await page.getByLabel('A short answer').fill('Hello');
  await page.getByLabel('Tell us more').fill('This was easy to complete.');
  await page.getByLabel('Contact email').fill('taylor@example.com');
  await page.getByLabel('Number of visits').fill('3');
  await page.getByLabel('Visit date').fill('2026-10-09');
  await page.getByLabel('One', { exact: true }).check();
  await page.getByLabel('Red', { exact: true }).check();
  await page.getByLabel('Blue', { exact: true }).check();
  await page.getByRole('radio', { name: '4', exact: true }).check();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'Submit response' }).click();
  await expect(page.getByRole('heading', { name: 'You’ve been heard.' })).toBeVisible();
  const responses = await page.request.get('/api/v1/surveys/' + survey.id + '/responses');
  expect(responses.ok()).toBeTruthy();
  const result = (await responses.json()).items[0];
  expect(result.respondent_name).toBe('Taylor');
  expect(Object.keys(result.answers)).toHaveLength(8);
});

test('integration keys stay scoped and can be revoked', async ({ page, request }) => {
  const owner = await customer(page.request);
  await page.goto('/#/integrations');
  await page.getByRole('button', { name: 'Create API key' }).first().click();
  await page.getByLabel('Integration name').fill('CRM read access');
  await page.getByRole('button', { name: 'Generate key' }).click();
  const integrationKey = await page.getByLabel('API key for CRM read access').inputValue();
  const headers = { 'X-API-Key': integrationKey };
  expect((await request.get('/api/v1/surveys', { headers })).status()).toBe(200);
  expect((await request.post('/api/v1/surveys', { headers, data: { title: 'Denied' } })).status()).toBe(403);
  expect((await request.get('/api/v1/operator/customers', { headers })).status()).toBe(403);
  await page.getByRole('button', { name: 'I’ve saved my key' }).click();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Revoke', exact: true }).click();
  await expect(page.getByText('Give your first integration a key.')).toBeVisible();
  expect((await request.get('/api/v1/surveys', { headers })).status()).toBe(401);
});

test('customer isolation also holds on the deployed runtime contract', async ({ page, request }) => {
  const a = await customer(page.request, 'Account A');
  const b = await customer(request, 'Account B');
  const create = await page.request.post('/api/v1/surveys', { headers: a.headers, data: { title: 'Private to A' } });
  const survey = await create.json();
  expect((await request.get('/api/v1/surveys')).ok()).toBeTruthy();
  expect((await (await request.get('/api/v1/surveys')).json()).total).toBe(0);
  for (const suffix of ['', '/responses', '/summary', '/export?format=csv']) {
    expect((await request.get('/api/v1/surveys/' + survey.id + suffix)).status()).toBe(404);
  }
  expect((await request.delete('/api/v1/surveys/' + survey.id, { headers: b.headers })).status()).toBe(404);
  expect((await page.request.get('/api/v1/surveys/' + survey.id)).status()).toBe(200);
});

test('mobile workspace navigation and blank form editing remain usable', async ({ page }) => {
  await customer(page.request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Create survey', exact: true }).click();
  await page.getByLabel('Survey title', { exact: true }).fill('A mobile survey');
  await page.locator('#create-survey-form').getByRole('button', { name: 'Create survey' }).click();
  await page.getByRole('button', { name: /Short answer/ }).click();
  await page.getByLabel('Question 1 title').fill('How are you?');
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page.getByText('Your draft is saved.')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.reload();
  await expect(page.getByLabel('Question 1 title')).toHaveValue('How are you?');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: false }).first()).toBeVisible();
});

test('edits made during a slow save are preserved', async ({ page }) => {
  const owner = await customer(page.request);
  const response = await page.request.post('/api/v1/surveys', {
    headers: owner.headers, data: { title: 'Before saving' },
  });
  const survey = await response.json();
  await page.goto('/#/builder/' + survey.id);
  await page.getByLabel('Survey title', { exact: true }).fill('First edit');
  let release, received;
  const waiting = new Promise(resolve => { received = resolve; });
  const proceed = new Promise(resolve => { release = resolve; });
  await page.route('**/api/v1/surveys/' + survey.id, async route => {
    if (route.request().method() !== 'PUT') return route.continue();
    const response = await route.fetch();
    received();
    await proceed;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Save draft' }).click();
  await waiting;
  await page.getByLabel('Survey title', { exact: true }).fill('Keep this latest edit');
  release();
  await expect(page.getByText('Earlier changes saved. Save again to include your latest edits.')).toBeVisible();
  await expect(page.getByLabel('Survey title', { exact: true })).toHaveValue('Keep this latest edit');
  await page.unrouteAll({ behavior: 'wait' });
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page.getByText('Your draft is saved.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Survey title', { exact: true })).toHaveValue('Keep this latest edit');
});
