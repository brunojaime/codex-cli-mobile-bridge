import html2canvas from 'html2canvas';

export async function captureViewport() {
  const width = innerWidth, height = innerHeight, pathname = location.pathname;
  const canvas = await html2canvas(document.body, {
    width, height, x: scrollX, y: scrollY, scale: 1,
    windowWidth: width, windowHeight: height, useCORS: true, logging: false, imageTimeout: 5000,
    ignoreElements: node => node.hasAttribute('data-codex-feedback') || node.hasAttribute('data-feedback-private'),
    onclone: doc => {
      for (const input of doc.querySelectorAll('input[type="password"], input[autocomplete="one-time-code"]')) { input.value = ''; input.setAttribute('value', ''); }
      // html2canvas does not understand the browser's closed-details content visibility.
      for (const details of doc.querySelectorAll('details:not([open])')) {
        for (const child of details.children) if (child.tagName !== 'SUMMARY') child.style.setProperty('display', 'none', 'important');
      }
    },
  });
  return { canvas, width, height, pathname };
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
