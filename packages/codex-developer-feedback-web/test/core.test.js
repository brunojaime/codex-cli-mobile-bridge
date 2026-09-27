import { test } from 'node:test';
import assert from 'node:assert/strict';
import { enabledAt, bridgeUrl, queueKey, saveQueue, loadQueue, createItem, createBatch, submitBatch } from '../src/core.js';
const config = { sourceApp: 'rd-gestion-hse', sourceDisplayName: 'RD Gestión HSE', environment: 'dev', allowedOrigins: ['https://rd-staging.nienfos.com'], bridgeUrl: 'https://bridge.example' };
const item = () => createItem(config, { screenshot: 'data:image/png;base64,aW1hZ2U=', comment: ' Ajustar ', points: [{ x: 4, y: 9 }], width: 390, height: 844, pathname: '/clientes' });
const memory = () => { const map = new Map(); return { getItem: k => map.get(k), setItem: (k,v) => map.set(k,v) }; };
test('only the exact dev origin is enabled, never QA or production', () => {
  assert.equal(enabledAt(config, { origin: config.allowedOrigins[0] }), true);
  for (const origin of ['https://app.consultorard.com.ar', 'https://rd-staging.nienfos.com.evil.test', 'http://rd-staging.nienfos.com', 'https://chrem-staging.nienfos.com']) assert.equal(enabledAt(config, { origin }), false);
  for (const environment of ['qa','staging','preview','prod','production']) assert.equal(enabledAt({ ...config, environment }, { origin: config.allowedOrigins[0] }), false);
});
test('Bridge only accepts HTTPS without embedded credentials', () => {
  assert.equal(bridgeUrl('https://bridge.example/'), 'https://bridge.example');
  for (const url of ['http://bridge.example', 'https://user:secret@bridge.example', 'https://bridge.example?token=secret']) assert.throws(() => bridgeUrl(url));
});
test('queue persistence is local, isolated per source and environment, bounded', () => {
  const store = memory(), key = queueKey(config), entry = item();
  saveQueue(store, key, [entry]); assert.deepEqual(loadQueue(store, key), [entry]);
  assert.deepEqual(loadQueue(store, queueKey({ ...config, sourceApp: 'proyecto-inmobiliaria' })), []);
  assert.throws(() => saveQueue(store, key, Array(9).fill(entry)));
  assert.throws(() => saveQueue(store, key, [{ ...entry, screenshotPngBase64: 'a'.repeat(4_000_000) }]));
  assert.deepEqual(loadQueue(store, key), [entry]);
});
test('batch uses the existing Bridge contract and disables automatic release', () => {
  const entry = item(), payload = createBatch(config, [entry], 'default');
  assert.equal(payload.kind, 'codex.developerFeedbackBatch'); assert.equal(payload.version, 1);
  assert.equal(payload.workflowPresetId, 'default'); assert.equal(payload.releaseWhenComplete, false);
  assert.deepEqual(entry.selectionBounds, { left: 4, top: 9, width: 0, height: 0 });
  assert.equal(entry.kind, 'codex.developerFeedback'); assert.equal(entry.comment, 'Ajustar');
  assert.equal(entry.screenshotPngBase64, 'aW1hZ2U='); assert.equal(entry.queue, 'codexCli');
  assert.equal(entry.contextMetadata.environment, 'dev'); assert.equal(entry.contextMetadata.pathname, '/clientes');
  assert.throws(() => createBatch(config, [{ ...entry, sourceApp: 'other' }], 'default'));
  assert.throws(() => createBatch(config, [], 'default'));
});
test('submission does not forward product credentials and accepts Bridge receipt', async () => {
  let calls = 0;
  const result = await submitBatch(config, [item()], 'default', async (url, options) => {
    calls++; assert.equal(url, 'https://bridge.example/feedback-batches/start-session');
    assert.equal(options.credentials, 'omit'); assert.equal(options.method, 'POST');
    assert.equal(JSON.parse(options.body).items.length, 1);
    return new Response(JSON.stringify({ job_id: 'job-1' }), { status: 202 });
  });
  assert.equal(calls, 1); assert.equal(result.job_id, 'job-1');
});
test('submission rejects HTTP errors and unconfirmed responses', async () => {
  for (const response of [new Response('{}', { status: 503 }), new Response('{}', { status: 200 })]) {
    await assert.rejects(submitBatch(config, [item()], 'default', async () => response));
  }
});
test('guided trace sends all chronological frames as image attachments and audio exactly once', () => {
  const entry = { ...item(), hasAudio: true, audioBase64: 'dm9pY2U=', audioMimeType: 'audio/webm', audioDurationMs: 12000, audioByteLength: 5,
    guidedTrace: { id: 'trace-test', kind: 'codex.liveFeedback.guidedTrace', version: 1, frames: [0,5000,12000].map((atMs,i) => ({ id: `f${i}`, atMs, screenshotPngBase64: `image${i}`, screen: { route: `/step${i}` } })) } };
  const payload = createBatch(config, [entry], 'generator_only');
  assert.equal(payload.items.length, 3);
  assert.deepEqual(payload.items.map(i => i.screenshotPngBase64), ['image0','image1','image2']);
  assert.equal(payload.items.filter(i => i.hasAudio).length, 1);
  assert.equal(payload.items.filter(i => i.audioBase64).length, 1);
  assert.equal(payload.items[0].guidedTrace.frames[1].atMs, 5000);
  assert.equal(payload.items[0].guidedTrace.frames[1].screenshotPngBase64, undefined);
  assert.match(payload.items[2].comment, /Paso 3\/3, 12.0 s/);
  assert.equal(new Set(payload.items.map(i => i.id)).size, 3);
  assert.equal(entry.guidedTrace.frames[0].screenshotPngBase64, 'image0', 'local review retains every frame');
});


test('only dev enables exact configured origins, legacy queues remain isolated', () => {
  for (const environment of ['dev', 'qa']) {
    const origin = `https://rd-${environment}.nienfos.com`;
    const scoped = { ...config, environment, allowedOrigins: [origin] };
    assert.equal(enabledAt(scoped, { origin }), environment === 'dev');
    assert.equal(enabledAt(scoped, { origin: 'https://app.consultorard.com.ar' }), false);
    assert.equal(enabledAt(scoped, { origin: origin + '.evil.test' }), false);
    assert.notEqual(queueKey(scoped), queueKey({ ...scoped, environment: 'staging' }));
    assert.match(createBatch(scoped, [item()], 'default').message, new RegExp('entorno ' + environment));
  }
  for (const environment of ['prod', 'production', 'preview', 'unknown']) {
    assert.equal(enabledAt({ ...config, environment }, { origin: config.allowedOrigins[0] }), false);
  }
});
