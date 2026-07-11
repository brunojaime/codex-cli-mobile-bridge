const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
};

const SENSITIVE_KEYS = new Set([
  'authorization',
  'api-key',
  'apikey',
  'password',
  'secret',
  'token',
  'x-sib-api-key',
]);

function json(payload, init = {}) {
  return new Response(JSON.stringify(payload), {
    ...init,
    headers: {
      ...JSON_HEADERS,
      ...(init.headers || {}),
    },
  });
}

function bearerToken(request) {
  const value = request.headers.get('authorization') || '';
  const [scheme, token] = value.split(/\s+/, 2);
  return scheme && scheme.toLowerCase() === 'bearer' ? token || '' : '';
}

function requireToken(request, env) {
  const expected = String(env.EMAIL_ENDPOINT_TOKEN || '').trim();
  if (!expected) {
    return {
      ok: false,
      response: json(
        { error: { code: 'email_endpoint_token_missing', message: 'EMAIL_ENDPOINT_TOKEN is not configured.' } },
        { status: 503 },
      ),
    };
  }
  if (bearerToken(request) !== expected) {
    return {
      ok: false,
      response: json(
        { error: { code: 'invalid_email_endpoint_token', message: 'Invalid email endpoint token.' } },
        { status: 401 },
      ),
    };
  }
  return { ok: true };
}

function isEmail(value) {
  const text = String(value || '').trim();
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text);
}

function allowedRecipients(env) {
  return String(env.ALLOWED_RECIPIENTS || '')
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function emailProvider(env) {
  return String(env.EMAIL_PROVIDER || (env.BREVO_API_KEY ? 'brevo' : 'cloudflare_email_service')).trim();
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (_error) {
    return null;
  }
}

function sanitize(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitize(item));
  }
  if (!value || typeof value !== 'object') {
    return value;
  }
  const clean = {};
  for (const [key, item] of Object.entries(value)) {
    clean[key] = SENSITIVE_KEYS.has(key.toLowerCase()) ? '[redacted]' : sanitize(item);
  }
  return clean;
}

function redactSecrets(message, env) {
  let redacted = String(message || '');
  for (const value of [env.EMAIL_ENDPOINT_TOKEN, env.BREVO_API_KEY]) {
    if (value) {
      redacted = redacted.split(String(value)).join('[redacted]');
    }
  }
  return redacted;
}

function metadataHeaders(metadata) {
  return {
    'X-Codex-Preview-Id': String(metadata?.preview_id || ''),
    'X-Codex-Invite-Id': String(metadata?.invite_id || ''),
    'X-Codex-Source-App': String(metadata?.source_app || ''),
  };
}

async function sendWithBrevo(message, env) {
  if (!env.BREVO_API_KEY) {
    return json(
      { error: { code: 'brevo_api_key_missing', message: 'BREVO_API_KEY is not configured.' } },
      { status: 503 },
    );
  }
  const response = await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: {
      accept: 'application/json',
      'api-key': env.BREVO_API_KEY,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      sender: { email: message.from },
      to: [{ email: message.to }],
      subject: message.subject,
      textContent: message.text,
      htmlContent: message.html || undefined,
      headers: metadataHeaders(message.metadata),
    }),
  });
  const raw = await response.text();
  let body = {};
  try {
    body = raw ? JSON.parse(raw) : {};
  } catch (_error) {
    body = { raw: raw.slice(0, 500) };
  }
  if (!response.ok) {
    return json(
      {
        error: {
          code: 'brevo_send_failed',
          message: redactSecrets(`Brevo ${response.status}: ${JSON.stringify(sanitize(body))}`, env),
        },
      },
      { status: 502 },
    );
  }
  const messageId = body.messageId || body.id || crypto.randomUUID();
  return json({ id: messageId, message_id: messageId, provider: 'brevo' });
}

async function sendWithCloudflareEmailService(message, env) {
  if (!env.EMAIL || typeof env.EMAIL.send !== 'function') {
    return json(
      { error: { code: 'email_binding_missing', message: 'EMAIL send_email binding is not configured.' } },
      { status: 503 },
    );
  }
  try {
    const result = await env.EMAIL.send({
      from: message.from,
      to: message.to,
      subject: message.subject,
      text: message.text,
      html: message.html || undefined,
      headers: metadataHeaders(message.metadata),
    });
    const messageId = result?.messageId || result?.id || crypto.randomUUID();
    return json({ id: messageId, message_id: messageId, provider: 'cloudflare_email_service' });
  } catch (error) {
    return json(
      {
        error: {
          code: error?.code || 'email_send_failed',
          message: redactSecrets(error?.message || 'Cloudflare Email Service send failed.', env),
        },
      },
      { status: 502 },
    );
  }
}

async function handleSend(request, env) {
  const token = requireToken(request, env);
  if (!token.ok) return token.response;
  const payload = await readJson(request);
  if (!payload || typeof payload !== 'object') {
    return json({ error: { code: 'invalid_json', message: 'Expected JSON payload.' } }, { status: 400 });
  }
  const from = String(env.EMAIL_FROM || payload.from || '').trim();
  const to = String(payload.to || '').trim();
  const subject = String(payload.subject || '').trim();
  const text = String(payload.text || '').trim();
  const html = String(payload.html || '').trim();
  if (!isEmail(from) || !isEmail(to) || !subject || !text) {
    return json(
      { error: { code: 'invalid_email_payload', message: 'from, to, subject, and text are required.' } },
      { status: 400 },
    );
  }
  const allowlist = allowedRecipients(env);
  if (allowlist.length > 0 && !allowlist.includes(to.toLowerCase())) {
    return json(
      { error: { code: 'recipient_not_allowed', message: 'Recipient is not in ALLOWED_RECIPIENTS.' } },
      { status: 403 },
    );
  }
  const message = { from, to, subject, text, html, metadata: payload.metadata || {} };
  const provider = emailProvider(env);
  if (provider === 'brevo') {
    return sendWithBrevo(message, env);
  }
  if (provider === 'cloudflare_email_service') {
    return sendWithCloudflareEmailService(message, env);
  }
  return json(
    { error: { code: 'unsupported_email_provider', message: `Unsupported EMAIL_PROVIDER: ${provider}` } },
    { status: 503 },
  );
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '/health')) {
      return json({
        ok: true,
        provider: emailProvider(env),
        brevoConfigured: Boolean(env.BREVO_API_KEY),
        emailBindingConfigured: Boolean(env.EMAIL && typeof env.EMAIL.send === 'function'),
      });
    }
    if (request.method === 'POST' && (url.pathname === '/' || url.pathname === '/send')) {
      return handleSend(request, env, ctx);
    }
    return json({ error: { code: 'not_found', message: 'Route not found.' } }, { status: 404 });
  },
};
