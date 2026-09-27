// Pointer capture keeps touch drags on the handle, never on the drawing surface.
export function makeFloating(panel, handle) {
  let position = null, drag = null;
  const clamp = () => {
    if (panel.hidden || !panel.getClientRects().length) return;
    const bounds = panel.getBoundingClientRect();
    position ||= { x: Math.max(8, innerWidth - bounds.width - 12), y: Math.max(8, innerHeight - bounds.height - 96) };
    position.x = Math.max(8, Math.min(position.x, innerWidth - bounds.width - 8));
    position.y = Math.max(8, Math.min(position.y, innerHeight - bounds.height - 8));
    panel.style.left = `${position.x}px`; panel.style.top = `${position.y}px`;
  };
  handle.onpointerdown = event => {
    if (event.button !== 0) return;
    clamp(); event.preventDefault();
    drag = { id: event.pointerId, x: event.clientX - position.x, y: event.clientY - position.y };
    handle.setPointerCapture(event.pointerId);
  };
  handle.onpointermove = event => {
    if (!drag || drag.id !== event.pointerId) return;
    event.preventDefault(); position = { x: event.clientX - drag.x, y: event.clientY - drag.y }; clamp();
  };
  const end = event => { if (drag?.id === event.pointerId) drag = null; };
  handle.onpointerup = end; handle.onpointercancel = end; handle.onlostpointercapture = end;
  handle.onkeydown = event => {
    const delta = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] }[event.key];
    if (!delta) return;
    event.preventDefault(); clamp(); position.x += delta[0]; position.y += delta[1]; clamp();
  };
  const observer = new ResizeObserver(clamp); observer.observe(panel);
  window.addEventListener('resize', clamp); window.visualViewport?.addEventListener('resize', clamp);
  return { place: clamp, dispose() { observer.disconnect(); window.removeEventListener('resize', clamp); window.visualViewport?.removeEventListener('resize', clamp); } };
}
