// Coordinates are stored in screenshot pixels, independent of editor size.
export function canvasPoint(event, rect, width, height) {
  return {
    x: Math.max(0, Math.min(width, (event.clientX - rect.left) * width / rect.width)),
    y: Math.max(0, Math.min(height, (event.clientY - rect.top) * height / rect.height)),
  };
}

export function paintAnnotations(ctx, strokes) {
  for (const { tool, points } of strokes) {
    if (!points.length) continue;
    const first = points[0], last = points.at(-1);
    const path = () => {
      ctx.beginPath();
      if (tool === 'rectangle') ctx.rect(first.x, first.y, last.x - first.x, last.y - first.y);
      else {
        ctx.moveTo(first.x, first.y);
        if (tool === 'arrow') {
          ctx.lineTo(last.x, last.y);
          const angle = Math.atan2(last.y - first.y, last.x - first.x);
          const size = Math.min(20, Math.hypot(last.x - first.x, last.y - first.y) / 3);
          for (const delta of [-Math.PI / 6, Math.PI / 6]) {
            ctx.moveTo(last.x, last.y);
            ctx.lineTo(last.x - size * Math.cos(angle + delta), last.y - size * Math.sin(angle + delta));
          }
        } else if (points.length === 1) ctx.lineTo(first.x + 0.1, first.y + 0.1);
        else for (const p of points.slice(1)) ctx.lineTo(p.x, p.y);
      }
    };
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    path(); ctx.lineWidth = 7; ctx.strokeStyle = '#ffffff'; ctx.stroke();
    path(); ctx.lineWidth = 4; ctx.strokeStyle = '#dc2626'; ctx.stroke();
    ctx.restore();
  }
}
