import {createItem, queueKey, loadQueue, submitBatch, bridgeUrl} from './core.js';

// Official native adapter: hosts supply platform storage/screenshot ports only.
// No DOM, product sessions, backend credentials or local URI leave this module.
export function createNativeFeedback(config, storage, fetcher = fetch) {
  if (config.environment !== 'dev' || !config.queueScope?.trim()) throw Error('Native feedback requires dev and an explicit queueScope.');
  bridgeUrl(config.bridgeUrl);
  const key = queueKey(config);
  let tail = Promise.resolve();
  const exclusive = operation => {
    const pending = tail.then(operation); tail = pending.catch(() => {}); return pending;
  };
  const load = async () => {
    let raw = await storage.getItem(key);
    if (raw === null && config.legacyQueueKeys?.length) {
      const migrated = [];
      for (const legacyKey of config.legacyQueueKeys) {
        const value = await storage.getItem(legacyKey);
        for (const item of loadQueue({getItem: () => value}, legacyKey)) if (!migrated.some(x => x.id === item.id)) migrated.push(item);
      }
      if (migrated.some(item => item.sourceApp !== config.sourceApp)) throw Error('La cola anterior pertenece a otra app.');
      raw = JSON.stringify(migrated);
      await storage.setItem(key, raw); // Commit first. Keep the original for recovery.
    }
    const items = loadQueue({getItem: () => raw}, key);
    if (items.some(item => item.sourceApp !== config.sourceApp)) throw Error('La cola pertenece a otra app.');
    return items;
  };
  const legacyUncertain = async () => {
    for (const key of config.legacyUncertainKeys || []) if (await storage.getItem(key) === 'true') return true;
    return false;
  };
  return {
    key,
    legacyUncertain,
    async reconcileLegacy(resolution) {
      if (!['received', 'not-received'].includes(resolution)) throw Error('Revisá el envío anterior en Codex Mobile.');
      await exclusive(async () => {
        if (resolution === 'received') {
          const ids = new Set();
          for (const legacyKey of config.legacyQueueKeys || []) {
            const raw = await storage.getItem(legacyKey);
            for (const item of loadQueue({getItem: () => raw}, legacyKey)) ids.add(item.id);
          }
          await storage.setItem(key, JSON.stringify((await load()).filter(item => !ids.has(item.id))));
        }
        for (const uncertainKey of config.legacyUncertainKeys || []) await storage.setItem(uncertainKey, 'false');
      });
    },
    pending: () => exclusive(load),
    async capture({screenshot, comment = '', width, height, pathname = '/native', points = [], audio}) {
      if (!/^(data:image\/png;base64,)?[A-Za-z0-9+/]+=*$/.test(screenshot || '')) throw Error('La captura debe contener PNG en base64, no una URI local.');
      const item = createItem(config, {screenshot, comment, width, height, pathname, points});
      if (audio) Object.assign(item, {hasAudio: true, audioBase64: audio.base64, audioMimeType: audio.mimeType, audioDurationMs: audio.durationMs, audioByteLength: audio.byteLength});
      await exclusive(async () => storage.setItem(key, JSON.stringify([...await load(), item])));
      return item;
    },
    remove: id => exclusive(async () => storage.setItem(key, JSON.stringify((await load()).filter(item => item.id !== id)))),
    async presets() {
      const response = await fetcher(`${bridgeUrl(config.bridgeUrl)}/feedback-workflow-presets`, {credentials: 'omit', signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw Error('No pudimos consultar los flujos del Bridge.');
      const body = await response.json();
      return {presets: body.presets || [], defaultPresetId: body.default_preset_id || body.defaultPresetId};
    },
    async send(preset, executionMode = 'execute') {
      if (await legacyUncertain()) throw Error('Hay un envío anterior sin confirmar. Revisá su recepción en Codex Mobile antes de migrar ese lote.');
      const items = await exclusive(load);
      const result = await submitBatch(config, items, preset, fetcher, executionMode);
      const sent = new Set(items.map(item => item.id));
      await exclusive(async () => storage.setItem(key, JSON.stringify((await load()).filter(item => !sent.has(item.id)))));
      return result;
    },
  };
}
