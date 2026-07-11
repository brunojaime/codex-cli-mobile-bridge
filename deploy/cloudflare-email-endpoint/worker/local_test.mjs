import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';

const source = await readFile(new URL('./src/index.js', import.meta.url), 'utf8');
const workerModule = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const worker = workerModule.default;

const sent = [];
const cloudflareEnv = {
  EMAIL_PROVIDER: 'cloudflare_email_service',
  EMAIL_ENDPOINT_TOKEN: 'local-secret',
  EMAIL_FROM: 'preview@nienfos.com',
  ALLOWED_RECIPIENTS: 'admin@example.com',
  EMAIL: {
    async send(message) {
      sent.push(message);
      return { messageId: 'msg-local-1' };
    },
  },
};
const brevoRequests = [];
const brevoEnv = {
  EMAIL_PROVIDER: 'brevo',
  EMAIL_ENDPOINT_TOKEN: 'local-secret',
  EMAIL_FROM: 'preview@nienfos.com',
  BREVO_API_KEY: 'brevo-secret',
};

globalThis.fetch = async (url, options) => {
  brevoRequests.push({ url, options });
  return new Response(JSON.stringify({ messageId: 'brevo-msg-1' }), {
    status: 201,
    headers: { 'content-type': 'application/json' },
  });
};

async function fetchWorker(path, init = {}, env = cloudflareEnv) {
  return worker.fetch(new Request(`https://email.example.test${path}`, init), env, {});
}

let response = await fetchWorker('/health');
assert.equal(response.status, 200);
let body = await response.json();
assert.equal(body.provider, 'cloudflare_email_service');
assert.equal(body.emailBindingConfigured, true);

response = await fetchWorker('/send', { method: 'POST' });
assert.equal(response.status, 401);
assert.equal((await response.json()).error.code, 'invalid_email_endpoint_token');

response = await fetchWorker('/send', {
  method: 'POST',
  headers: {
    authorization: 'Bearer local-secret',
    'content-type': 'application/json',
  },
  body: JSON.stringify({
    from: 'ignored@nienfos.com',
    to: 'admin@example.com',
    subject: 'Preview invite',
    text: 'Open the invite link.',
    html: '<p><a href="https://preview.example.test">Activate account</a></p>',
    metadata: { preview_id: 'wp-demo', invite_id: 'wpi-demo' },
  }),
});
assert.equal(response.status, 200);
assert.equal((await response.json()).message_id, 'msg-local-1');
assert.equal(sent.length, 1);
assert.equal(sent[0].from, 'preview@nienfos.com');
assert.equal(sent[0].to, 'admin@example.com');
assert.match(sent[0].html, /Activate account/);
assert.equal(sent[0].headers['X-Codex-Preview-Id'], 'wp-demo');

response = await fetchWorker('/send', {
  method: 'POST',
  headers: {
    authorization: 'Bearer local-secret',
    'content-type': 'application/json',
  },
  body: JSON.stringify({
    to: 'other@example.com',
    subject: 'Preview invite',
    text: 'Open the invite link.',
  }),
});
assert.equal(response.status, 403);
assert.equal((await response.json()).error.code, 'recipient_not_allowed');

response = await fetchWorker('/send', {
  method: 'POST',
  headers: {
    authorization: 'Bearer local-secret',
    'content-type': 'application/json',
  },
  body: JSON.stringify({
    from: 'preview@nienfos.com',
    to: 'admin@example.com',
    subject: 'Preview invite',
    text: 'Open the invite link.',
    metadata: { preview_id: 'wp-demo', invite_id: 'wpi-demo', source_app: 'demo' },
  }),
}, brevoEnv);
body = await response.json();
assert.equal(response.status, 200);
assert.equal(body.provider, 'brevo');
assert.equal(body.message_id, 'brevo-msg-1');
assert.equal(brevoRequests.length, 1);
assert.equal(brevoRequests[0].url, 'https://api.brevo.com/v3/smtp/email');
const brevoPayload = JSON.parse(brevoRequests[0].options.body);
assert.equal(brevoPayload.sender.email, 'preview@nienfos.com');
assert.equal(brevoPayload.to[0].email, 'admin@example.com');
assert.equal(brevoPayload.headers['X-Codex-Invite-Id'], 'wpi-demo');

console.log('cloudflare email endpoint worker harness passed');
