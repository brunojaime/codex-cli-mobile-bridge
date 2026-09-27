import { createQueueStore } from './queue-store.js';
import { createLiveDrawing } from './live-drawing.js';
import { captureViewport } from './capture.js';
import { makeFloating } from './floating.js';
import { createTraceRecorder, traceTime } from './trace.js';
import { enabledAt, bridgeUrl, queueKey, createItem, submitBatch } from './core.js';
import { canvasPoint, paintAnnotations } from './annotations.js';

const paths = {
  grip: '<path d="M8 5h1m6 0h1M8 12h1m6 0h1M8 19h1m6 0h1"/>',
  mic: '<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  fold: '<path d="m6 14 6-6 6 6"/>',
  bug: '<path d="m8 3 2 3m6-3-2 3M7 9h10v7a5 5 0 0 1-10 0V9Zm1 0a4 4 0 0 1 8 0M12 10v10M3 8l4 3m-4 3h4m-3 6 3-3m14-9-4 3m4 3h-4m3 6-3-3"/>',
  pen: '<path d="m16 3 5 5L8 21H3v-5L16 3Zm-3 3 5 5"/>',
  rectangle: '<rect x="4" y="5" width="16" height="14" rx="1"/>',
  arrow: '<path d="M4 20 20 4M9 4h11v11"/>',
  undo: '<path d="M3 10h11a6 6 0 0 1 0 12M3 10l5-5m-5 5 5 5"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  inbox: '<path d="M4 4h16l2 12v4H2v-4L4 4Zm-2 12h6l2 3h4l2-3h6"/>',
};
const icon = name => `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
const css = `
:host { all: initial; font-family: system-ui, sans-serif; color: #172b44; font-size: 14px; line-height: 1.45; }
* { box-sizing: border-box; } button, textarea, select { font: inherit; } svg { width: 22px; height: 22px; flex-shrink: 0; }
button { cursor: pointer; border: 1px solid #ccd5e0; background: white; color: #172b44; border-radius: 10px; padding: 10px 14px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
button:focus-visible,textarea:focus-visible,select:focus-visible,canvas:focus-visible { outline: 3px solid #37a7d7; outline-offset: 2px; }
button:disabled { opacity: .55; cursor: default; } .primary { background: #163c61; color: white; border-color: #163c61; } .icon-button { width: 44px; padding: 8px; }
.launcher { position: fixed; right: 16px; bottom: calc(86px + env(safe-area-inset-bottom, 0px)); width: 56px; height: 56px; border-radius: 50%; padding: 12px; box-shadow: 0 4px 20px #17334d40; z-index: 2147483600; }
.launcher svg { width: 28px; height: 28px; } .badge { position: absolute; top: -4px; right: -3px; border-radius: 12px; background: #dc2626; color: white; padding: 1px 6px; font-size: 12px; border: 2px solid white; }
.dock { position: fixed; right: 16px; bottom: calc(154px + env(safe-area-inset-bottom, 0px)); width: min(290px, calc(100vw - 32px)); padding: 14px; border: 1px solid #d4dce6; border-radius: 14px; background: #fff; box-shadow: 0 8px 36px #17334d30; z-index: 2147483600; }
.dock strong { display: block; margin-bottom: 10px; } .dock button { width: 100%; margin-top: 6px; justify-content: flex-start; } .dock p { margin-bottom: 0; }
dialog { border: 1px solid #d4dce6; border-radius: 16px; padding: 0; width: min(520px, calc(100vw - 24px)); max-height: calc(100dvh - 24px); color: #172b44; background: #fff; box-shadow: 0 24px 80px #0004; }
dialog::backdrop { background: #10243a66; } .body { padding: 20px; } header { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; font-size: 21px; } p { margin: 8px 0 14px; } .muted { color: #536577; font-size: 13px; } label { display: block; margin: 14px 0 6px; font-weight: 600; }
textarea, select { width: 100%; border: 1px solid #abb9c8; border-radius: 10px; padding: 10px; background: white; color: #172b44; } textarea { resize: vertical; min-height: 90px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; } #canvas { display: block; max-width: 100%; max-height: 26dvh; width: auto; margin: auto; border: 1px solid #d1dbe5; border-radius: 8px; }
.preview { margin-top: 14px; background: #eef2f7; border-radius: 8px; } .item { display: flex; align-items: center; gap: 10px; border-top: 1px solid #e2e8f0; padding: 10px 0; } .item img { width: 48px; height: 56px; object-fit: contain; background: #eef2f7; } .item span { flex: 1; overflow-wrap: anywhere; } .status { color: #165f4b; white-space: pre-line; } .error { color: #9c2c24; } [hidden] { display: none !important; }
#editor { position: fixed; inset: 0; margin: 0; width: 100%; height: 100dvh; max-width: none; max-height: none; border: 0; border-radius: 0; background: white; overflow: hidden; }
.workarea { position: absolute; inset: 0; overflow: auto; }
#drawing-canvas { display: block; touch-action: none; user-select: none; cursor: crosshair; background: white; max-width: none; }
.floating { position: fixed; width: max-content; max-width: calc(100vw - 16px); z-index: 2147483601; background: #fff; color: #172b44; border: 1px solid #c9d4df; border-radius: 14px; padding: 6px; box-shadow: 0 4px 20px #10243a35; }
.float-row { display: flex; align-items: center; gap: 4px; } .float-row button { padding: 8px; min-width: 44px; } .float-row .primary { padding: 8px 12px; }
.drag { touch-action: none; cursor: grab; border: 0; color: #52667a; } .drag:active { cursor: grabbing; }
.tools { display: flex; gap: 4px; margin-top: 6px; padding-top: 6px; border-top: 1px solid #e5ebf2; }
.tools button { padding: 8px; width: 44px; } .tools button[aria-pressed="true"] { color: #fff; background: #163c61; border-color: #163c61; }
#drawing-hint { margin: 0; padding: 4px 6px 0; font-size: 11px; color: #52667a; }
#recording-bar { width: 286px; } #live-drawing { position: fixed; inset: 0; z-index: 2147483600; touch-action: none; } .recording-info { flex: 1; min-width: 0; } .recording-info strong { display: block; font-variant-numeric: tabular-nums; } .recording-info small { color: #52667a; } .record-dot { display: inline-block; width: 8px; height: 8px; background: #b42335; border-radius: 50%; margin-right: 6px; }
#recording-note { margin: 0; font-size: 12px; } #trace-review img { display: block; width: auto; max-width: 100%; height: 30dvh; object-fit: contain; margin: auto; background: #eef2f7; }
#trace-review audio { width: 100%; margin-top: 12px; } #trace-review input[type=range] { width: 100%; min-height: 44px; } .trace-caption { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.item-actions { display: flex; flex-direction: column; gap: 4px; } .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }

`;

export function mountFeedback(config) {
  if (typeof document === 'undefined' || !enabledAt(config, window.location)) return () => {};
  bridgeUrl(config.bridgeUrl);
  if (document.querySelector('[data-codex-feedback]')) return () => {};
  const host = document.createElement('div');
  host.dataset.codexFeedback = '0.5.0';
  host.setAttribute('data-html2canvas-ignore', 'true');
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>${css}</style>
    <button class="launcher primary" aria-label="Abrir feedback" aria-expanded="false" aria-controls="dock" title="Feedback · staging" type="button">${icon('bug')}<span class="badge" hidden></span></button>
    <section class="dock" id="dock" aria-label="Herramientas de feedback" hidden>
      <strong>Feedback · staging</strong>
      <button id="start-drawing" class="primary" type="button">${icon('pen')}Dibujar en pantalla</button>
      <button id="start-trace" type="button">${icon('mic')}Grabar recorrido con voz</button>
      <p class="muted">Hasta 2 minutos. Capturas automáticas mientras usás la app.</p>
      <button id="pending" type="button">${icon('inbox')}<span>Ver pendientes</span></button>
      <p id="dock-status" class="muted" role="status"></p>
    </section>
    <dialog id="editor" aria-label="Dibujar sobre la pantalla">
      <div class="workarea"><canvas id="drawing-canvas" aria-label="Dibujar sobre la captura con el dedo o el mouse"></canvas></div>
      <section id="drawing-tools" class="floating" aria-label="Herramientas flotantes">
        <div class="float-row">
          <button id="drawing-drag" class="drag" aria-label="Mover herramientas" title="Arrastrar o mover con las flechas del teclado" type="button">${icon('grip')}</button>
          <button id="fold-tools" aria-label="Plegar herramientas" aria-expanded="true" type="button">${icon('fold')}</button>
          <button id="continue" class="primary" type="button">Comentar</button>
          <button id="exit-editor" aria-label="Volver del dibujo" type="button">${icon('close')}</button>
        </div>
        <div class="tools" id="drawing-buttons" role="toolbar" aria-label="Herramientas de dibujo">
          <button data-tool="pen" aria-label="Lápiz" title="Lápiz" aria-pressed="true" type="button">${icon('pen')}</button>
          <button data-tool="rectangle" aria-label="Rectángulo" title="Rectángulo" aria-pressed="false" type="button">${icon('rectangle')}</button>
          <button data-tool="arrow" aria-label="Flecha" title="Flecha" aria-pressed="false" type="button">${icon('arrow')}</button>
          <button id="undo" aria-label="Deshacer trazo" title="Deshacer" type="button">${icon('undo')}</button>
          <button id="clear" aria-label="Borrar dibujos" title="Borrar dibujos" type="button">${icon('trash')}</button>
        </div>
        <p id="drawing-hint" role="status">Dibujá con el dedo o el mouse.</p>
      </section>
    </dialog>
    <canvas id="live-drawing" aria-label="Marcar durante la grabación" hidden></canvas>
    <section id="recording-bar" class="floating" aria-label="Grabación del recorrido" hidden>
      <div class="float-row">
        <button id="recording-drag" class="drag" aria-label="Mover grabación" title="Arrastrar o mover con las flechas del teclado" type="button">${icon('grip')}</button>
        <div class="recording-info"><strong><span class="record-dot"></span><span id="recording-clock">0:00</span></strong><small id="recording-frames">Esperando micrófono…</small></div>
        <button id="stop-trace" class="primary" aria-label="Detener recorrido" type="button">${icon('stop')}</button>
        <button id="cancel-trace" aria-label="Descartar recorrido en curso" type="button">${icon('close')}</button>
      </div>
      <div class="float-row"><button id="capture-step" type="button">Capturar paso</button><button id="mark-trace" type="button" aria-pressed="false">Dibujar</button></div>
      <div id="live-tools" class="tools" role="toolbar" aria-label="Marcas del recorrido" hidden>
      <button id="live-pen" aria-label="Lápiz del recorrido" aria-pressed="true">${icon('pen')}</button><button id="live-rectangle" aria-label="Rectángulo del recorrido" aria-pressed="false">${icon('rectangle')}</button><button id="live-arrow" aria-label="Flecha del recorrido" aria-pressed="false">${icon('arrow')}</button><button id="live-undo" aria-label="Deshacer marca">${icon('undo')}</button><button id="live-clear" aria-label="Borrar marcas">${icon('trash')}</button></div><p id="recording-note" role="status"></p>
    </section>
    <dialog id="trace-review" aria-labelledby="trace-title"><div class="body">
      <header><h2 id="trace-title">Revisar recorrido</h2><button id="close-trace-review" class="icon-button" aria-label="Cerrar recorrido" type="button">${icon('close')}</button></header>
      <p class="muted" id="trace-summary"></p>
      <img id="trace-image" alt="Captura del recorrido">
      <label for="trace-position" class="sr-only">Paso del recorrido</label><input id="trace-position" type="range" min="0" value="0" step="1">
      <div class="trace-caption"><span id="trace-step"></span><span id="trace-time"></span></div>
      <audio id="trace-audio" controls preload="metadata"></audio>
      <p id="trace-note" class="muted" role="status"></p>
      <label for="trace-comment">¿Qué debería pasar?</label><textarea id="trace-comment" maxlength="10000" placeholder="Podés completar lo que contaste…"></textarea>
      <div class="actions"><button id="save-trace" class="primary" type="button">Guardar recorrido</button><button id="discard-trace" type="button">Descartar recorrido</button></div>
    </div></dialog>
    <dialog id="feedback-dialog" aria-labelledby="title"><div class="body">
      <header><div><h2 id="title">Feedback de desarrollo</h2><p class="muted" id="app"></p></div><button id="close" class="icon-button" aria-label="Cerrar feedback" type="button">${icon('close')}</button></header>
      <div class="actions"><button id="capture" type="button">${icon('pen')}Nueva captura</button><button id="new-trace" type="button">${icon('mic')}Nuevo recorrido</button></div>
      <section id="draft" hidden>
        <div class="preview"><canvas id="canvas" aria-label="Vista previa de la captura dibujada"></canvas></div>
        <button id="edit" type="button">${icon('pen')}Editar dibujo</button>
        <label for="comment">¿Qué querés cambiar?</label><textarea id="comment" maxlength="10000" placeholder="Describí el cambio o problema…"></textarea>
        <div class="actions"><button id="save" class="primary" type="button">Guardar en la cola</button><button id="discard" type="button">Descartar captura</button></div>
      </section>
      <label id="queue-label">Capturas y recorridos pendientes</label><div id="queue" aria-labelledby="queue-label"></div>
      <label for="preset">Flujo de trabajo</label><select id="preset"><option value="generator_only">Generador</option><option value="generator_reviewer">Generador + revisor</option></select>
      <p class="muted">Conectá Tailscale para enviar. Sólo se envía al tocar «Enviar a Codex».</p>
      <div class="actions"><button id="send" class="primary" type="button">Enviar a Codex</button></div>
      <p id="status" class="status" role="status" aria-live="polite"></p>
    </div></dialog>`;
  document.body.append(host);
  const el = id => root.getElementById(id);
  const dialog = el('feedback-dialog'), editor = el('editor'), launch = root.querySelector('.launcher');
  el('app').textContent = config.sourceDisplayName;
  const key = queueKey(config);
  const queueStore = createQueueStore(key);
  let items = [], snapshot = null, strokes = [], active = null, pointerId = null, tool = 'pen';
  let busy = false, disposed = false, frame = 0, presetLoaded = false;
  let traceDraft = null, reviewItem = null, audioUrl = null;
  let pathname = '', width = 0, height = 0, queueError = false;
  const status = (message, error = false) => {
    el('status').textContent = message; el('status').className = `status${error ? ' error' : ''}`;
  };
  const dock = open => { el('dock').hidden = !open; launch.setAttribute('aria-expanded', String(open)); };
  const renderQueue = () => {
    el('queue').replaceChildren();
    if (!items.length) el('queue').textContent = 'Todavía no guardaste capturas ni recorridos.';
    for (const item of items) {
      const row = document.createElement('div'); row.className = 'item';
      const img = document.createElement('img'); img.src = `data:image/png;base64,${item.screenshotPngBase64}`; img.alt = 'Captura guardada';
      const label = document.createElement('span'); label.textContent = item.guidedTrace ? `Recorrido · ${traceTime(item.audioDurationMs || 0)} · ${item.guidedTrace.frames.length} capturas${item.comment ? ` · ${item.comment}` : ''}` : item.comment || 'Captura sin comentario';
      const remove = document.createElement('button'); remove.textContent = 'Eliminar'; remove.disabled = busy; remove.type = 'button';
      remove.onclick = async () => {
        if (busy) return; setBusy(true);
        try { const next = items.filter(i => i.id !== item.id); await queueStore.save(next); items = next; renderQueue(); }
        catch { status('No se pudo actualizar la cola del navegador.', true); }
        finally { setBusy(false); }
      };
      const actions = document.createElement('div'); actions.className = 'item-actions';
      if (item.guidedTrace) { const review = document.createElement('button'); review.type = 'button'; review.textContent = 'Revisar'; review.onclick = () => openTraceReview(item, true); actions.append(review); }
      actions.append(remove); row.append(img, label, actions); el('queue').append(row);
    }
    el('send').disabled = busy || !items.length || queueError;
    const badge = launch.querySelector('.badge'); badge.hidden = !items.length; badge.textContent = String(items.length);
    launch.setAttribute('aria-label', items.length ? `Abrir feedback, ${items.length} pendientes` : 'Abrir feedback');
    el('pending').querySelector('span').textContent = `Ver pendientes${items.length ? ` (${items.length})` : ''}`;
  };
  launch.disabled = true;
  void queueStore.load().then(saved => { if (!disposed) { items = saved; renderQueue(); } }).catch(() => {
    queueError = true; status('No se pudo abrir la cola local. Permití el almacenamiento del sitio y recargá.', true);
  }).finally(() => { if (!disposed) { launch.disabled = false; renderQueue(); } });
  renderQueue();
  const setBusy = value => {
    busy = value;
    for (const id of ['capture', 'new-trace', 'start-drawing', 'start-trace', 'save', 'discard', 'edit', 'comment', 'preset', 'save-trace', 'discard-trace']) el(id).disabled = value;
    renderQueue();
  };
  const paint = (canvas, includeActive = false) => {
    if (!snapshot) return;
    if (canvas.width !== snapshot.width || canvas.height !== snapshot.height) { canvas.width = snapshot.width; canvas.height = snapshot.height; }
    const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(snapshot, 0, 0);
    paintAnnotations(ctx, includeActive && active ? [...strokes, active] : strokes);
  };
  const controls = () => {
    el('undo').disabled = !strokes.length || pointerId !== null;
    el('clear').disabled = !strokes.length || pointerId !== null;
    el('drawing-hint').textContent = strokes.length ? `${strokes.length} ${strokes.length === 1 ? 'trazo' : 'trazos'} · Podés seguir dibujando.` : 'Usá el dedo o el mouse para dibujar.';
  };
  const draw = () => { frame = 0; paint(el('drawing-canvas'), true); controls(); };
  const scheduleDraw = () => { if (!frame) frame = requestAnimationFrame(draw); };
  const fit = () => {
    if (!snapshot || !editor.open) return;
    // One screenshot pixel per CSS pixel: toolbars never reduce the work surface.
    el('drawing-canvas').style.width = `${snapshot.width}px`;
    el('drawing-canvas').style.height = `${snapshot.height}px`;
    draw();
  };
  const resize = new ResizeObserver(fit); resize.observe(root.querySelector('.workarea'));
  const drawingFloat = makeFloating(el('drawing-tools'), el('drawing-drag'));
  const recordingFloat = makeFloating(el('recording-bar'), el('recording-drag'));
  el('fold-tools').onclick = () => { const hidden = !el('drawing-buttons').hidden; el('drawing-buttons').hidden = hidden; el('drawing-hint').hidden = hidden; el('fold-tools').setAttribute('aria-expanded', String(!hidden)); el('fold-tools').setAttribute('aria-label', hidden ? 'Mostrar herramientas' : 'Plegar herramientas'); drawingFloat.place(); };
  const point = event => canvasPoint(event, el('drawing-canvas').getBoundingClientRect(), snapshot.width, snapshot.height);
  el('drawing-canvas').onpointerdown = event => {
    if (!snapshot || pointerId !== null || event.button !== 0 || strokes.length >= 100) return;
    event.preventDefault(); pointerId = event.pointerId;
    active = { tool, points: [point(event)] };
    el('drawing-canvas').setPointerCapture(pointerId); scheduleDraw();
  };
  el('drawing-canvas').onpointermove = event => {
    if (pointerId !== event.pointerId || !active) return;
    event.preventDefault();
    const next = point(event);
    if (active.tool === 'pen') { if (active.points.length < 1500) active.points.push(next); }
    else active.points = [active.points[0], next];
    scheduleDraw();
  };
  const finish = event => {
    if (pointerId !== event.pointerId) return;
    if (event.type === 'pointerup' && active) strokes.push(active);
    active = null; pointerId = null;
    if (el('drawing-canvas').hasPointerCapture(event.pointerId)) el('drawing-canvas').releasePointerCapture(event.pointerId);
    scheduleDraw();
  };
  el('drawing-canvas').onpointerup = finish;
  el('drawing-canvas').onpointercancel = finish;
  el('drawing-canvas').onlostpointercapture = finish;
  root.querySelectorAll('[data-tool]').forEach(button => {
    button.onclick = () => {
      tool = button.dataset.tool;
      root.querySelectorAll('[data-tool]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    };
  });
  el('undo').onclick = () => { strokes.pop(); draw(); };
  el('clear').onclick = () => { strokes = []; draw(); };
  const openEditor = () => { dock(false); if (dialog.open) dialog.close(); editor.showModal(); fit(); drawingFloat.place(); };
  const showComment = () => {
    active = null; pointerId = null; if (editor.open) editor.close();
    paint(el('canvas')); el('draft').hidden = !snapshot;
    if (!dialog.open) dialog.showModal();
  };
  el('continue').onclick = showComment;
  el('exit-editor').onclick = showComment;
  editor.addEventListener('cancel', event => { event.preventDefault(); showComment(); });
  el('edit').onclick = openEditor;
  el('discard').onclick = () => { snapshot = null; strokes = []; active = null; el('comment').value = ''; el('draft').hidden = true; };
  el('close').onclick = () => dialog.close();
  dialog.addEventListener('close', () => { if (!editor.open) launch.focus(); });
  const loadPresets = async () => {
    if (presetLoaded) return;
    try {
      const response = await fetch(`${bridgeUrl(config.bridgeUrl)}/feedback-workflow-presets`, { credentials: 'omit', signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (disposed || !data.presets?.length) return;
      el('preset').replaceChildren(...data.presets.map(p => new Option(p.name, p.id)));
      el('preset').value = data.default_preset_id || data.defaultPresetId || data.presets[0].id; presetLoaded = true;
    } catch { if (!disposed && !queueError) status('Podés guardar sin conexión. Para enviar, conectá Tailscale y verificá el Bridge.', true); }
  };
  launch.onclick = () => { dock(el('dock').hidden); void loadPresets(); };
  el('pending').onclick = () => { dock(false); showComment(); void loadPresets(); };
  const capture = async () => {
    if (snapshot) { openEditor(); return; }
    setBusy(true); el('dock-status').textContent = 'Preparando pantalla…';
    if (dialog.open) dialog.close(); host.style.visibility = 'hidden';
    try {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const shot = await captureViewport();
      snapshot = shot.canvas; width = shot.width; height = shot.height; pathname = shot.pathname;
      if (disposed) return;
      strokes = []; active = null; host.style.visibility = ''; openEditor(); status('Revisá la captura y agregá tu comentario.'); el('dock-status').textContent = '';
    } catch { if (!disposed) { el('dock-status').textContent = 'No se pudo capturar. Intentá nuevamente.'; dock(true); } }
    finally { if (!disposed) { host.style.visibility = ''; setBusy(false); } }
  };
  el('capture').onclick = capture; el('start-drawing').onclick = capture;
  el('save').onclick = async () => {
    if (!snapshot || queueError || busy) return;
    setBusy(true);
    try {
      paint(el('canvas'));
      const item = createItem(config, { screenshot: el('canvas').toDataURL('image/png'), comment: el('comment').value, points: strokes.flatMap(s => s.points), strokes, width, height, pathname });
      const next = [...items, item]; await queueStore.save(next); items = next;
      snapshot = null; strokes = []; active = null; el('comment').value = ''; el('draft').hidden = true; renderQueue(); status('Guardado en este navegador. Todavía no se envió a Codex.');
    } catch (error) { status(error.message || 'No hay espacio disponible en el navegador.', true); }
    finally { setBusy(false); }
  };
  el('send').onclick = async () => {
    if (busy || !items.length) return;
    if (snapshot || traceDraft) { status('Guardá o descartá la captura o recorrido actual antes de enviar.', true); return; }
    setBusy(true); status('Enviando a Codex…');
    try {
      const result = await submitBatch(config, items, el('preset').value);
      items = [];
      try { await queueStore.save([]); } catch { queueError = true; }
      if (!disposed) status(`Enviado a Codex. Seguí el trabajo en Codex Mobile.\nReferencia: ${result.batchId || result.feedback_batch_id || result.job_id || result.jobId}${queueError ? '\nNo se pudo limpiar el almacenamiento: no reenvíes estas capturas al recargar.' : ''}`);
    } catch (error) {
      if (!disposed) status(error.name === 'TimeoutError' || error instanceof TypeError
        ? 'No se pudo confirmar el envío. La cola sigue guardada. Revisá en Codex Mobile si llegó antes de reintentar; verificá Tailscale y el Bridge.' : error.message, true);
    } finally { if (!disposed) setBusy(false); }
  };
  const releaseAudio = () => { el('trace-audio').pause(); el('trace-audio').removeAttribute('src'); el('trace-audio').load(); if (audioUrl) URL.revokeObjectURL(audioUrl); audioUrl = null; };
  const showTraceFrame = index => {
    if (!reviewItem) return;
    const frames = reviewItem.guidedTrace.frames, frame = frames[index]; if (!frame) return;
    el('trace-position').value = String(index); el('trace-image').src = `data:image/png;base64,${frame.screenshotPngBase64}`;
    el('trace-step').textContent = `Paso ${index + 1} de ${frames.length}`; el('trace-time').textContent = traceTime(frame.atMs);
  };
  const openTraceReview = (item, queued = false, note = '') => {
    if (dialog.open) dialog.close(); dock(false); reviewItem = item; releaseAudio();
    el('trace-summary').textContent = `${traceTime(item.audioDurationMs)} · ${item.guidedTrace.frames.length} capturas · ${item.hasAudio ? 'Con voz' : 'Sin audio'}`;
    el('trace-position').max = String(item.guidedTrace.frames.length - 1); el('trace-note').textContent = note;
    el('trace-comment').value = item.comment; el('trace-comment').readOnly = queued;
    el('save-trace').hidden = queued; el('discard-trace').hidden = queued;
    el('trace-audio').hidden = !item.hasAudio;
    if (item.hasAudio) { const bytes = Uint8Array.from(atob(item.audioBase64), c => c.charCodeAt(0)); audioUrl = URL.createObjectURL(new Blob([bytes], { type: item.audioMimeType })); el('trace-audio').src = audioUrl; }
    showTraceFrame(0); if (!el('trace-review').open) el('trace-review').showModal();
  };
  el('trace-position').oninput = () => { const index = Number(el('trace-position').value); showTraceFrame(index); if (reviewItem?.hasAudio) el('trace-audio').currentTime = reviewItem.guidedTrace.frames[index].atMs / 1000; };
  el('trace-audio').ontimeupdate = () => { if (!reviewItem) return; const ms = el('trace-audio').currentTime * 1000; let index = 0; reviewItem.guidedTrace.frames.forEach((f, i) => { if (f.atMs <= ms) index = i; }); showTraceFrame(index); };
  el('trace-review').addEventListener('close', () => { if (traceDraft && reviewItem === traceDraft) traceDraft.comment = el('trace-comment').value; releaseAudio(); launch.focus(); });
  el('close-trace-review').onclick = () => el('trace-review').close();
  el('save-trace').onclick = async () => {
    if (!traceDraft || queueError || busy) return;
    setBusy(true);
    try { traceDraft.comment = el('trace-comment').value.trim(); const next = [...items, traceDraft]; await queueStore.save(next); items = next; traceDraft = null; el('trace-review').close(); renderQueue(); showComment(); status('Recorrido guardado en la cola. Tocá Nuevo recorrido para seguir agregando.'); }
    catch (error) { el('trace-note').textContent = error.message; }
    finally { setBusy(false); }
  };
  el('discard-trace').onclick = () => { traceDraft = null; el('trace-review').close(); };
  const liveDrawing = createLiveDrawing(el('live-drawing'), () => void recorder.capture('annotation'));
  const resetLiveDrawing = () => { liveDrawing.hide(); el('live-tools').hidden = true; el('mark-trace').textContent = 'Dibujar'; el('mark-trace').setAttribute('aria-pressed', 'false'); };
  const recordingEnded = () => { resetLiveDrawing(); el('recording-bar').hidden = true; launch.hidden = false; el('start-trace').disabled = false; };
  const recorder = createTraceRecorder(config, {
    captureScreen: () => liveDrawing.capture(),
    onUpdate: value => {
      el('recording-clock').textContent = traceTime(value.durationMs); el('recording-frames').textContent = value.stopping ? 'Preparando recorrido…' : `${value.frames} capturas · Voz`;
      el('mark-trace').disabled = value.stopping; el('stop-trace').disabled = value.stopping; el('capture-step').disabled = value.stopping;
    },
    onReady: (item, note) => { if (disposed) return; recordingEnded(); if (item) { traceDraft = item; openTraceReview(item, false, note); } },
    onError: message => { if (!disposed) { el('recording-note').textContent = message; el('dock-status').textContent = message; } },
  });
  const startTrace = async () => {
    if (busy || queueError) return;
    if (traceDraft) { openTraceReview(traceDraft); return; }
    if (snapshot) { showComment(); status('Guardá o descartá la captura antes de grabar el recorrido.', true); return; }
    if (dialog.open) dialog.close();
    dock(false); launch.hidden = true; el('recording-bar').hidden = false; el('recording-clock').textContent = '0:00'; el('recording-frames').textContent = 'Esperando micrófono…'; el('recording-note').textContent = ''; el('stop-trace').disabled = true; el('capture-step').disabled = true; recordingFloat.place();
    try { await recorder.start(); } catch (error) { if (!disposed) { recordingEnded(); dock(true); el('dock-status').textContent = error.message; } }
  };
  el('start-trace').onclick = startTrace; el('new-trace').onclick = startTrace;
  el('mark-trace').onclick = async () => {
    if (liveDrawing.active) { el('mark-trace').disabled = true; await recorder.capture('annotations_complete'); resetLiveDrawing(); el('mark-trace').disabled = false; }
    else { liveDrawing.show(); el('live-tools').hidden = false; el('mark-trace').textContent = 'Navegar'; el('mark-trace').setAttribute('aria-pressed', 'true'); el('recording-note').textContent = 'La voz sigue grabando. Tocá Navegar para continuar el flujo.'; }
    recordingFloat.place();
  };
  for (const name of ['pen', 'rectangle', 'arrow']) el(`live-${name}`).onclick = () => { liveDrawing.tool = name; for (const other of ['pen', 'rectangle', 'arrow']) el(`live-${other}`).setAttribute('aria-pressed', String(name === other)); };
  el('live-undo').onclick = () => liveDrawing.undo(); el('live-clear').onclick = () => liveDrawing.clear();
  el('stop-trace').onclick = () => void recorder.stop(); el('capture-step').onclick = () => void recorder.capture();
  el('cancel-trace').onclick = () => { recorder.cancel(); recordingEnded(); };
  return () => { disposed = true; void queueStore.close(); liveDrawing.dispose(); recorder.cancel(); releaseAudio(); drawingFloat.dispose(); recordingFloat.dispose(); resize.disconnect(); if (frame) cancelAnimationFrame(frame); host.remove(); };
}
