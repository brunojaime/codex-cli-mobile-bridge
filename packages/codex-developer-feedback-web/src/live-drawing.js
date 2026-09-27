import { captureViewport } from './capture.js';
import { paintAnnotations, canvasPoint } from './annotations.js';

// Separate live ink layer: product stays full size and voice never pauses.
export function createLiveDrawing(canvas, onChange, onReset = () => {}) {
  let strokes = [], current = null, pointer = null, tool = 'pen', snapshot = null, generation = 0;
  const paint = () => { const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height); if (snapshot) ctx.drawImage(snapshot.canvas, 0, 0); paintAnnotations(ctx, current ? [...strokes, current] : strokes); };
  const clear = () => { strokes = []; current = null; pointer = null; paint(); };
  const hide = () => { generation++; canvas.hidden = true; snapshot = null; clear(); };
  const resize = () => { if (!canvas.hidden) { hide(); onReset(); } };
  const point = e => canvasPoint(e, canvas.getBoundingClientRect(), canvas.width, canvas.height);
  canvas.onpointerdown = e => { if (pointer !== null || (e.pointerType === 'mouse' && e.button !== 0)) return; e.preventDefault(); pointer = e.pointerId; current = { tool, points: [point(e)] }; canvas.setPointerCapture(pointer); paint(); };
  canvas.onpointermove = e => { if (pointer !== e.pointerId || !current) return; e.preventDefault(); if (tool === 'pen') current.points.push(point(e)); else current.points[1] = point(e); paint(); };
  canvas.onpointerup = e => { if (pointer !== e.pointerId || !current) return; strokes.push(current); current = null; pointer = null; if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); paint(); onChange(); };
  canvas.onpointercancel = () => { current = null; pointer = null; paint(); };
  window.addEventListener('resize', resize);
  // Ink belongs to the captured frame, even if the app changes behind it.
  return {
    get active() { return !canvas.hidden; },
    set tool(value) { tool = value; },
    async show() {
      const attempt = ++generation;
      const shot = await captureViewport();
      if (generation !== attempt) return false;
      snapshot = shot; canvas.width = shot.width; canvas.height = shot.height;
      canvas.hidden = false; clear(); return true;
    },
    hide,
    undo() { strokes.pop(); paint(); onChange(); },
    clear() { clear(); onChange(); },
    async capture() {
      if (!snapshot || canvas.hidden) return captureViewport();
      const output = document.createElement('canvas'); output.width = snapshot.width; output.height = snapshot.height;
      const annotations = structuredClone(current ? [...strokes, current] : strokes);
      const ctx = output.getContext('2d'); ctx.drawImage(snapshot.canvas, 0, 0); paintAnnotations(ctx, annotations);
      return { ...snapshot, canvas: output, annotations };
    },
    dispose() { hide(); window.removeEventListener('resize', resize); }

  };
}
