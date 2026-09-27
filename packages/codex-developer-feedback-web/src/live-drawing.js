import { captureViewport } from './capture.js';
import { paintAnnotations, canvasPoint } from './annotations.js';

// Separate live ink layer: product stays full size and voice never pauses.
export function createLiveDrawing(canvas, onChange) {
  let strokes = [], current = null, pointer = null, tool = 'pen';
  const paint = () => { const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height); paintAnnotations(ctx, current ? [...strokes, current] : strokes); };
  const clear = () => { strokes = []; current = null; pointer = null; paint(); };
  const resize = () => { if (canvas.hidden) return; canvas.width = innerWidth; canvas.height = innerHeight; clear(); };
  const point = e => canvasPoint(e, canvas.getBoundingClientRect(), canvas.width, canvas.height);
  canvas.onpointerdown = e => { if (pointer !== null || (e.pointerType === 'mouse' && e.button !== 0)) return; e.preventDefault(); pointer = e.pointerId; current = { tool, points: [point(e)] }; canvas.setPointerCapture(pointer); paint(); };
  canvas.onpointermove = e => { if (pointer !== e.pointerId || !current) return; e.preventDefault(); if (tool === 'pen') current.points.push(point(e)); else current.points[1] = point(e); paint(); };
  canvas.onpointerup = e => { if (pointer !== e.pointerId || !current) return; strokes.push(current); current = null; pointer = null; if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); paint(); onChange(); };
  canvas.onpointercancel = () => { current = null; pointer = null; paint(); };
  window.addEventListener('resize', resize);
  // Never leave viewport coordinates pinned to unrelated content after scrolling.
  window.addEventListener('scroll', clear, true);
  return {
    get active() { return !canvas.hidden; },
    set tool(value) { tool = value; },
    show() { canvas.hidden = false; resize(); },
    hide() { canvas.hidden = true; clear(); },
    undo() { strokes.pop(); paint(); onChange(); },
    clear() { clear(); onChange(); },
    async capture() {
      const ink = document.createElement('canvas'); ink.width = canvas.width; ink.height = canvas.height;
      const annotations = canvas.hidden ? [] : structuredClone(strokes);
      if (!canvas.hidden) ink.getContext('2d').drawImage(canvas, 0, 0);
      const shot = await captureViewport();
      if (ink.width && ink.height) shot.canvas.getContext('2d').drawImage(ink, 0, 0);
      return { ...shot, annotations };
    },
    dispose() { window.removeEventListener('resize', resize); window.removeEventListener('scroll', clear, true); }
  };
}
