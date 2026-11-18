// Run with Node >=20 after building tool/proactive_mock_preview.dart and serving
// build/proactive-mock-preview. Captures the actual Flutter frontend, not HTML replicas.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE ||
  `${require('node:os').homedir()}/.local/share/codex-browser/node_modules/playwright`);
const { mkdir, writeFile } = require('node:fs/promises');
const { resolve } = require('node:path');

(async () => {
  const output = resolve('reports/proactive-notification-mock');
  await mkdir(`${output}/screenshots`, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/opt/google/chrome/chrome',
    headless: true,
    args: ['--no-sandbox'],
  });
  const results = [];
  try {
    for (const [width, height] of [[390, 844], [430, 932], [768, 1024], [1440, 900]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const capture = async name => {
        await page.waitForTimeout(350);
        await page.screenshot({ path: `${output}/screenshots/${name}-${width}.png` });
      };
      await page.goto(process.env.PROACTIVE_PREVIEW_URL || 'http://127.0.0.1:18763');
      await page.waitForSelector('flt-semantics-placeholder', { state: 'attached' });
      await page.locator('flt-semantics-placeholder').evaluateAll(items => items.forEach(e => e.click()));
      await page.getByRole('button', { name: 'Propuestas del agente', exact: true }).waitFor();
      await capture('chat');
      await page.getByRole('button', { name: 'Propuestas del agente', exact: true }).click();
      await page.getByRole('button', { name: 'Simular notificación', exact: true }).waitFor();
      await capture('inbox-empty');
      await page.getByRole('button', { name: 'Simular notificación', exact: true }).click();
      await page.getByRole('button', { name: 'Abrir', exact: true }).waitFor();
      await capture('notification');
      await page.getByRole('button', { name: 'Abrir', exact: true }).click();
      await page.getByRole('button', { name: 'Ejecutar', exact: true }).waitFor();
      await capture('proposal');
      await page.getByRole('button', { name: 'Observaciones', exact: true }).click();
      await page.getByRole('textbox').fill('Primero una sola tanda y prioricemos el recorrido en el teléfono.');
      await capture('observations');
      await page.getByRole('button', { name: 'Guardar observaciones', exact: true }).click();
      await page.getByRole('button', { name: 'Ejecutar', exact: true }).click();
      await page.waitForTimeout(450);
      await page.mouse.move(width / 2, height / 2);
      await page.mouse.wheel(0, 900);
      await capture('executed');
      await page.getByRole('button', { name: 'Back', exact: true }).click();
      await page.getByRole('button', { name: 'Volver a simular notificación', exact: true }).click();
      await page.getByRole('button', { name: 'Abrir', exact: true }).click();
      await page.getByRole('button', { name: 'Rechazar', exact: true }).click();
      await page.waitForTimeout(350);
      await page.mouse.move(width / 2, height / 2);
      await page.mouse.wheel(0, 900);
      await capture('rejected');
      results.push({ width, height, pageErrors: errors, completed: true });
      await context.close();
    }
    await writeFile(`${output}/browser-validation.json`, JSON.stringify(results, null, 2));
    if (results.some(result => result.pageErrors.length)) throw new Error('Browser errors: inspect validation report');
    console.log(JSON.stringify(results));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
