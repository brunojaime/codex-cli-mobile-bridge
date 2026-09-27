import html2canvas from 'html2canvas';

export class CaptureChangedError extends Error {
  constructor() { super('La pantalla está cambiando. Se capturará cuando termine de cargar.'); this.retryable = true; }
}
const viewport = () => ({ width: innerWidth, height: innerHeight, x: scrollX, y: scrollY, pathname: location.pathname,
  visualX: window.visualViewport?.offsetLeft || 0, visualY: window.visualViewport?.offsetTop || 0, visualScale: window.visualViewport?.scale || 1 });
const sameViewport = (a, b) => Object.keys(a).every(key => a[key] === b[key]);
const absoluteUrls = (css, base) => css.replace(/url\(\s*(['"]?)(.*?)\1\s*\)/g, (match, quote, value) => {
  try { return `url("${new URL(value, base).href.replaceAll('"', '%22')}")`; } catch { return match; }
});
function sheetText(sheet, base) {
  return [...sheet.cssRules].map(rule => {
    if (rule.type === CSSRule.IMPORT_RULE) {
      const css = sheetText(rule.styleSheet, rule.href);
      return rule.media.mediaText ? `@media ${rule.media.mediaText}{${css}}` : css;
    }
    return absoluteUrls(rule.cssText, base);
  }).join('\n');
}
function loadedStyles() {
  return [...document.querySelectorAll('link[rel~="stylesheet"]')].map(node => {
    if (!node.disabled && !node.sheet && (!node.media || matchMedia(node.media).matches)) throw new CaptureChangedError();
    try { return { href: node.href, css: sheetText(node.sheet, node.href), disabled: node.disabled || node.sheet.disabled, media: node.media, nonce: node.nonce }; }
    catch (error) { if (error?.retryable) throw error; return { href: node.href }; } // Cross-origin CSS remains subject to browser access rules.
  });
}
// Serialize DOM cloning: a manual capture must not race an interval's iframe.
let pending = Promise.resolve();
export function captureViewport() {
  const result = pending.then(captureStableViewport);
  pending = result.catch(() => {});
  return result;
}
async function captureStableViewport() {
  if (document.fonts?.status === 'loading') throw new CaptureChangedError();
  const view = viewport(), styles = loadedStyles(), capturedAt = new Date().toISOString();
  const bodyStyle = getComputedStyle(document.body);
  const expected = { color: bodyStyle.color, backgroundColor: bodyStyle.backgroundColor, fontFamily: bodyStyle.fontFamily };
  let cloneDocument;
  try {
    const canvas = await html2canvas(document.body, {
      width: view.width, height: view.height, x: view.x, y: view.y, scale: 1,
      scrollX: view.x, scrollY: view.y, windowWidth: view.width, windowHeight: view.height,
      useCORS: true, logging: false, imageTimeout: 5000,
      ignoreElements: node => node.hasAttribute('data-codex-feedback'),
      onclone: async doc => {
        cloneDocument = doc;
        // Reuse the exact CSSOM that styled the visible app. An authenticated,
        // offline or navigating clone must not depend on fetching CSS again.
        const unused = [...styles];
        for (const link of doc.querySelectorAll('link[rel~="stylesheet"]')) {
          const index = unused.findIndex(style => style.href === link.href);
          if (index < 0) continue;
          const source = unused.splice(index, 1)[0];
          if (source.css === undefined) continue;
          const style = doc.createElement('style');
          style.textContent = source.css; style.media = source.disabled ? 'not all' : source.media;
          if (source.nonce) style.nonce = source.nonce;
          link.replaceWith(style);
        }
        // Hide private content without collapsing its layout and moving marks.
        for (const node of doc.querySelectorAll('[data-feedback-private], [data-feedback-private] *')) node.style.setProperty('visibility', 'hidden', 'important');
        for (const input of doc.querySelectorAll('input[type="password"], input[autocomplete="one-time-code"]')) { input.value = ''; input.setAttribute('value', ''); }
        for (const details of doc.querySelectorAll('details:not([open])')) {
          for (const child of details.children) if (child.tagName !== 'SUMMARY') child.style.setProperty('display', 'none', 'important');
        }
        await doc.fonts?.ready;
        const actual = doc.defaultView.getComputedStyle(doc.body);
        if (Object.keys(expected).some(key => actual[key] !== expected[key])) throw new CaptureChangedError();
        doc.defaultView.scrollTo(view.x, view.y);
      },
    });
    if (!sameViewport(view, viewport())) throw new CaptureChangedError();
    return { canvas, width: view.width, height: view.height, pathname: view.pathname, viewport: view, capturedAt };
  } finally {
    // html2canvas does not destroy its iframe when onclone rejects.
    cloneDocument?.defaultView?.frameElement?.remove();
  }
}

export function traceScreenshot(canvas) {
  let scale = Math.min(1, 960 / canvas.width);
  const output = document.createElement('canvas');
  let data;
  do {
    output.width = Math.round(canvas.width * scale); output.height = Math.round(canvas.height * scale);
    output.getContext('2d').drawImage(canvas, 0, 0, output.width, output.height);
    data = output.toDataURL('image/png').split(',')[1]; scale *= .8;
  } while (data.length > 180_000 && output.width > 320);
  return { screenshotPngBase64: data, screenshotMimeType: 'image/png', width: output.width, height: output.height, pixelRatio: output.width / canvas.width };
}
