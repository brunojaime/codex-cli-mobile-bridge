export function enabledAt(config, location) {
  return config.environment === 'dev' && config.allowedOrigins.includes(location.origin);
}

export function bridgeUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
    throw new Error('El Bridge debe usar una dirección HTTPS sin credenciales.');
  }
  return url.href.replace(/\/$/, '');
}

export function queueKey(config) {
  return `codex-feedback:v1:${config.sourceApp}:${config.environment}`;
}

export function saveQueue(storage, key, items) {
  if (items.length > 8) throw new Error('Podés guardar hasta 8 capturas por envío.');
  const data = JSON.stringify(items);
  if (data.length > 4_000_000) throw new Error('Las capturas ocupan demasiado espacio. Enviá o eliminá algunas.');
  storage.setItem(key, data);
}

export function loadQueue(storage, key) {
  const data = storage.getItem(key);
  if (!data) return [];
  const items = JSON.parse(data);
  if (!Array.isArray(items) || items.some(item => !item.id || !item.screenshotPngBase64)) {
    throw new Error('No se pudo leer la cola guardada en este navegador.');
  }
  return items;
}

export function createItem(config, { screenshot, comment, points, strokes = [], width, height, pathname }) {
  const bounds = points.reduce((b, p) => ({ left: Math.min(b.left, p.x), top: Math.min(b.top, p.y), right: Math.max(b.right, p.x), bottom: Math.max(b.bottom, p.y) }), { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity });
  return {
    kind: 'codex.developerFeedback', version: 1,
    id: `feedback-${crypto.randomUUID()}`,
    sourceApp: config.sourceApp, sourceDisplayName: config.sourceDisplayName,
    queue: 'codexCli', status: 'pending', createdAt: new Date().toISOString(),
    comment: comment.trim(), screenshotMimeType: 'image/png',
    screenshotPngBase64: screenshot.replace(/^data:image\/png;base64,/, ''),
    selectionPoints: points,
    selectionBounds: points.length ? {
      left: bounds.left, top: bounds.top,
      width: bounds.right - bounds.left,
      height: bounds.bottom - bounds.top,
    } : {},
    hasAudio: false,
    contextMetadata: { environment: config.environment, pathname, viewport: { width, height }, annotations: { version: 1, strokes } },
  };
}

export function createBatch(config, items, preset) {
  if (!items.length) throw new Error('Agregá al menos una captura.');
  if (items.some(item => item.sourceApp !== config.sourceApp)) throw new Error('La cola pertenece a otra app.');
  return {
    kind: 'codex.developerFeedbackBatch', version: 1,
    sourceApp: config.sourceApp, sourceDisplayName: config.sourceDisplayName,
    workflowPresetId: preset, releaseWhenComplete: false, items: items.flatMap(expandTrace),
    message: `Feedback del entorno ${config.environment}. Implementar y validar los cambios en el proyecto indicado. No desplegar producción. La publicación requiere autorización específica.`,
  };
}

// Every frame must become an image attachment: the Bridge omits binary data
// from guidedTrace JSON when constructing the model prompt.
export function expandTrace(item) {
  const frames = item.guidedTrace?.frames;
  if (!frames?.length) return [item];
  const trace = { ...item.guidedTrace, frames: frames.map(({ screenshotPngBase64, ...frame }) => frame) };
  return frames.map((frame, index) => {
    const { audioBase64, audioMimeType, audioDurationMs, audioByteLength, guidedTrace, ...base } = item;
    const step = `Recorrido ${trace.id}. Paso ${index + 1}/${frames.length}, ${(frame.atMs / 1000).toFixed(1)} s, ${frame.screen?.route || '/'}.`;
    return { ...base, id: index ? `${item.id}-frame-${index + 1}` : item.id,
      screenshotPngBase64: frame.screenshotPngBase64,
      comment: index ? step : `${item.comment}\n${step}\nLa voz corresponde al recorrido completo. Revisar todas las imágenes adjuntas en orden.`,
      hasAudio: index === 0 && item.hasAudio,
      ...(index === 0 ? { guidedTrace: trace, audioBase64, audioMimeType, audioDurationMs, audioByteLength } : {}),
      contextMetadata: { ...item.contextMetadata, traceId: trace.id, frameIndex: index, atMs: frame.atMs },
    };
  });
}

export async function submitBatch(config, items, preset, fetcher = fetch) {
  const response = await fetcher(`${bridgeUrl(config.bridgeUrl)}/feedback-batches/start-session`, {
    method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(createBatch(config, items, preset)),
    signal: AbortSignal.timeout(60000),
  });
  if (!response.ok) throw new Error(`El Bridge no aceptó el envío (${response.status}). La cola sigue guardada.`);
  const result = await response.json();
  if (!result.job_id && !result.jobId && !result.batchId && !result.feedback_batch_id) {
    throw new Error('El Bridge no confirmó el envío. Revisá Codex Mobile antes de volver a enviarlo.');
  }
  return result;
}
