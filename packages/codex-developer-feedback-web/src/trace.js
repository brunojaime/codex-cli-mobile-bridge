import { captureViewport, traceScreenshot } from './capture.js';
import { createItem } from './core.js';
export const TRACE_LIMITS = { durationMs: 120_000, intervalMs: 2000, maxFrames: 48, maxEvents: 160, frameChars: 1_800_000, audioBytes: 900_000 };
const base64 = blob => new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(blob); });
export const traceTime = ms => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;

export function createTraceRecorder(config, { onUpdate, onReady, onError, captureScreen = captureViewport }) {
  let state = null, starting = false, generation = 0;
  const notify = () => { if (state) onUpdate({ durationMs: performance.now() - state.start, frames: state.frames.length, stopping: state.stopping }); };
  const event = (type, data = {}) => {
    if (!state) return;
    if (state.timeline.length >= TRACE_LIMITS.maxEvents) { state.droppedEventCount++; return; }
    state.timeline.push({ id: `${state.id}-event-${state.timeline.length + 1}`, type, atMs: Math.round(performance.now() - state.start), ...data });
  };
  const capture = async (reason = 'manual', final = false) => {
    const s = state;
    if (!s || (s.stopping && !final)) return;
    if (s.capturePromise) { if (!final && ['interval', 'interaction'].includes(reason)) return; await s.capturePromise; if (state !== s || (s.stopping && !final)) return; }
    s.capturePromise = (async () => {
      try {
        const atMs = Math.round(performance.now() - s.start);
        const shot = await captureScreen();
        if (state !== s) return;
        const image = traceScreenshot(shot.canvas);
        if (!final && ['interval', 'interaction'].includes(reason) && s.frames.at(-1)?.screenshotPngBase64 === image.screenshotPngBase64) return;
        if (s.frames.length >= TRACE_LIMITS.maxFrames || s.frameChars + image.screenshotPngBase64.length > TRACE_LIMITS.frameChars) {
          if (!final) { void stop('Se alcanzó el límite de capturas.'); return; }
          // Reserve the final screen by replacing only the last frame at the limit.
          const previous = s.frames.pop(); if (previous) s.frameChars -= previous.screenshotPngBase64.length;
        }
        const id = `${s.id}-frame-${s.nextFrame++}`;
        s.frames.push({ id, attachmentId: id, atMs, ...image, screen: { route: shot.pathname }, annotations: shot.annotations || [] });
        s.frameChars += image.screenshotPngBase64.length;
        event('frame_captured', { frameId: id, reason, route: shot.pathname }); notify();
      } catch { s.captureErrors++; if (!s.stopping) onError('No se pudo capturar este paso. Podés volver a tocar Capturar paso.'); }
    })();
    try { await s.capturePromise; } finally { s.capturePromise = null; }
  };
  const interaction = e => {
    if (!state || e.composedPath().some(node => node instanceof Element && node.hasAttribute('data-codex-feedback'))) return;
    const target = e.target instanceof Element ? e.target : null;
    if (target?.closest('[data-feedback-private],input[type="password"],input[autocomplete="one-time-code"]')) return;
    event('pointer', { x: Math.round(e.clientX), y: Math.round(e.clientY), route: location.pathname });
    clearTimeout(state.interactionTimer);
    state.interactionTimer = setTimeout(() => { if (state && performance.now() - state.lastInteractionCapture > 2000) { state.lastInteractionCapture = performance.now(); void capture('interaction'); } }, 650);
  };
  const beforeUnload = e => { if (state) { e.preventDefault(); e.returnValue = ''; } };
  const visibility = () => { if (document.hidden && state) void stop('Se detuvo al salir de la app.'); };
  const detach = s => {
    clearInterval(s.timer); clearInterval(s.uiTimer); clearTimeout(s.limitTimer); clearTimeout(s.interactionTimer);
    document.removeEventListener('pointerup', interaction, true); document.removeEventListener('visibilitychange', visibility);
    window.removeEventListener('beforeunload', beforeUnload);
  };
  const cancel = () => {
    generation++; starting = false;
    const s = state; state = null;
    if (!s) return;
    detach(s); if (s.recorder.state !== 'inactive') s.recorder.stop(); s.stream.getTracks().forEach(t => t.stop());
  };
  const stop = async (reason = '') => {
    const s = state; if (!s || s.stopping) return;
    s.stopping = true; detach(s); notify();
    event('recording_stopped', { reason });
    const durationMs = Math.round(performance.now() - s.start);
    // Stop microphone immediately; final screen capture can take longer.
    if (s.recorder.state !== 'inactive') s.recorder.stop();
    s.stream.getTracks().forEach(t => t.stop());
    await capture('stopped', true);
    await s.audioDone;
    if (state !== s) return;
    if (!s.frames.length) { state = null; onError('No se guardaron capturas. Volvé a grabar el recorrido.'); onReady(null); return; }
    const blob = new Blob(s.chunks, { type: s.recorder.mimeType || s.chunks[0]?.type || 'audio/webm' });
    const audioBase64 = blob.size ? await base64(blob) : '';
    if (state !== s) return;
    const last = s.frames.at(-1);
    const item = createItem(config, { screenshot: last.screenshotPngBase64, comment: '', points: [], width: last.width, height: last.height, pathname: last.screen.route });
    Object.assign(item, { feedbackKind: 'codex.liveFeedback.guidedTrace', hasAudio: !!audioBase64, audioBase64, audioMimeType: blob.type, audioDurationMs: durationMs, audioByteLength: blob.size,
      guidedTrace: { kind: 'codex.liveFeedback.guidedTrace', version: 1, id: s.id, startedAt: s.startedAt, endedAt: new Date().toISOString(),
        recording: { mode: 'screen_trace_with_audio', durationMs, frameStrategy: 'route_change_interaction_and_interval', maxFrames: TRACE_LIMITS.maxFrames, maxEvents: TRACE_LIMITS.maxEvents, truncated: !!reason || s.droppedEventCount > 0, droppedEventCount: s.droppedEventCount, audio: { attachmentId: `${s.id}-audio`, mimeType: blob.type, durationMs, transcriptAvailable: false } },
        timeline: s.timeline, frames: s.frames },
    });
    state = null;
    onReady(item, reason || (s.captureErrors ? 'Algunos pasos no se pudieron capturar. Revisá la secuencia.' : audioBase64 ? '' : 'No se obtuvo audio. Podés revisar las capturas o volver a grabar.'));
  };
  const start = async () => {
    if (starting || state) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Este navegador no permite grabar voz. Abrí dev en Chrome o Safari con HTTPS.');
    starting = true; const attempt = ++generation; let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      if (attempt !== generation) { stream.getTracks().forEach(t => t.stop()); return; }
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 32000 });
      const s = state = { id: `trace-${crypto.randomUUID()}`, start: performance.now(), startedAt: new Date().toISOString(), stream, recorder, frames: [], timeline: [], chunks: [], frameChars: 0, audioBytes: 0, nextFrame: 1, captureErrors: 0, droppedEventCount: 0, lastRoute: location.pathname, lastInteractionCapture: 0, stopping: false };
      s.audioDone = new Promise(resolve => { recorder.onstop = resolve; });
      recorder.ondataavailable = e => { if (e.data.size) { s.chunks.push(e.data); s.audioBytes += e.data.size; if (s.audioBytes > TRACE_LIMITS.audioBytes && !s.stopping) void stop('Se alcanzó el límite de audio.'); } };
      recorder.onerror = () => { void stop('El micrófono se interrumpió. Revisá el audio.'); };
      for (const track of stream.getTracks()) track.onended = () => { if (state === s && !s.stopping) void stop('El micrófono se desconectó.'); };
      recorder.start(1000); event('recording_started');
      document.addEventListener('pointerup', interaction, true); document.addEventListener('visibilitychange', visibility);
      window.addEventListener('beforeunload', beforeUnload);
      s.timer = setInterval(() => void capture('interval'), TRACE_LIMITS.intervalMs);
      s.uiTimer = setInterval(() => { if (state !== s) return; if (s.lastRoute !== location.pathname) { s.lastRoute = location.pathname; event('route_change', { route: s.lastRoute }); void capture('route_change'); } notify(); }, 500);
      s.limitTimer = setTimeout(() => void stop('Se alcanzaron los 2 minutos.'), TRACE_LIMITS.durationMs);
      notify(); void capture('started');
    } catch (error) {
      stream?.getTracks().forEach(t => t.stop());
      if (attempt !== generation) return;
      cancel();
      throw new Error(error.name === 'NotAllowedError' ? 'Permití el micrófono en el navegador para grabar el recorrido con voz.' : 'No se pudo iniciar el micrófono. Revisá el permiso y volvé a intentar.');
    } finally { if (attempt === generation) starting = false; }
  };
  return { start, stop, cancel, capture, get active() { return !!state || starting; } };
}
