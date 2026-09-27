import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const out = resolve('../../reports/staging-feedback-drawing-20260926');
const browser = await chromium.launch({ headless: true });
const results = [];
try {
 for (const app of [
  { name: 'rd', origin: 'https://rd-dev.nienfos.com', prod: 'https://app.consultorard.com.ar', port: 5188 },
  { name: 'chrem', origin: 'https://chrem-dev.nienfos.com', prod: 'https://chrempropiedades.com.ar', port: 5189 },
 ]) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await context.route('**/*', async route => {
   const url = new URL(route.request().url());
   if (url.hostname.endsWith('.ts.net')) return route.fulfill({ json: { default_preset_id: 'default', presets: [{ id: 'default', name: 'Generador' }] } });
   if (![new URL(app.origin).hostname, new URL(app.prod).hostname].includes(url.hostname)) return route.abort();
   if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 401, json: { error: 'unauthorized' } });
   const response = await route.fetch({ url: `http://127.0.0.1:${app.port}${url.pathname}${url.search}` });
   return route.fulfill({ response });
  });
  await page.goto(app.origin);
  await page.getByRole('button', { name: 'Abrir feedback', exact: true }).click({ timeout: 60000 });
  await page.getByRole('button', { name: 'Dibujar en pantalla', exact: true }).click();
  await page.locator('#drawing-canvas').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Comentar', exact: true }).click();
  await page.locator('#draft').waitFor({ state: 'visible', timeout: 30000 });
  await page.getByLabel('¿Qué querés cambiar?').fill('Prueba local de integración. No enviada.');
  await page.screenshot({ path: resolve(out, `${app.name}-app-integration-390.png`), fullPage: false });
  await page.getByRole('button', { name: 'Guardar en la cola', exact: true }).click();
    await page.locator('#status').filter({hasText:'Guardado en este navegador'}).waitFor();
  await page.reload();
  await page.getByRole('button', { name: 'Abrir feedback, 1 pendientes', exact: true }).waitFor();
  await page.goto(app.prod);
  await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('[data-codex-feedback]').count(), 0);
  results.push({ app: app.name, source: 'real local app, simulated dev origin; API unauthenticated', capture: 'passed', persistence: 'passed', productionHidden: true });
  await context.close();
 }
 await writeFile(resolve(out, 'app-integration-tests.json'), JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));
} finally { await browser.close(); }
