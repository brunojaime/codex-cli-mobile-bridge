import { chromium } from 'playwright';
import { build } from 'esbuild';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const output = resolve(process.env.FEEDBACK_REPORT_DIR || '../../reports/staging-feedback-flow-20260926');
await mkdir(output, { recursive: true });
const bundle = await build({ entryPoints: ['src/index.js'], bundle: true, format: 'esm', write: false });
const script = bundle.outputFiles[0].text;
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const app of [
    { sourceApp: 'rd-gestion-hse', name: 'RD Gestión HSE', origin: 'https://rd-dev.nienfos.com', production: 'https://app.consultorard.com.ar' },
    { sourceApp: 'proyecto-inmobiliaria', name: 'Chrem Inmobiliaria', origin: 'https://chrem-dev.nienfos.com', production: 'https://chrempropiedades.com.ar' },
  ]) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
    const page = await context.newPage();
    let posts = [], fail = false;
    const config = { sourceApp: app.sourceApp, sourceDisplayName: app.name, environment: 'dev', allowedOrigins: [app.origin], bridgeUrl: 'https://bridge.test' };
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'bridge.test') {
        if (url.pathname === '/feedback-workflow-presets') return route.fulfill({ json: { default_preset_id: 'default', presets: [{ id: 'default', name: 'Generador' }] } });
        assert.equal(url.pathname, '/feedback-batches/start-session');
        posts.push(route.request().postDataJSON());
        return route.fulfill({ status: fail ? 503 : 202, json: fail ? {} : { job_id: 'test-job', batchId: 'test-batch' } });
      }
      if (url.pathname === '/feedback.js') return route.fulfill({ contentType: 'text/javascript', body: script });
      return route.fulfill({ contentType: 'text/html', body: `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prueba aislada de feedback</title><body style="margin:0;background:#eef3f8;font-family:system-ui"><main style="padding:24px;min-height:100vh"><p>PRUEBA LOCAL · ${app.name}</p><h1>Revisión de staging</h1><p>Datos sintéticos exclusivos de esta prueba.</p><section style="background:white;padding:24px;border-radius:16px"><h2>Pantalla de prueba</h2><p>Ejemplo para comprobar capturas y comentarios.</p><input type="password" value="not-captured"></section></main><script type="module">import { mountFeedback } from '/feedback.js'; mountFeedback(${JSON.stringify(config)});</script></body></html>` });
    });
    await page.goto(app.origin);
    await page.getByRole('button', { name: 'Abrir feedback', exact: true }).click();
    assert.equal(await page.locator('.launcher svg').count(), 1);
    await page.getByRole('button', { name: 'Dibujar en pantalla', exact: true }).click();
    await page.locator('#editor').waitFor({ state: 'visible' });
    const canvas = page.locator('#drawing-canvas');
    const box = await canvas.boundingBox();
    assert.equal(box.width, 390); assert.equal(box.height, 844); assert.equal(box.x, 0); assert.equal(box.y, 0);
    const x = box.x + box.width * .2, y = box.y + box.height * .3;
    await page.mouse.move(x, y); await page.mouse.down();
    await page.mouse.move(x + 50, y + 20, { steps: 8 });
    await page.mouse.move(x + 65, y + 70, { steps: 8 }); await page.mouse.up();
    await page.locator('#drawing-hint').filter({ hasText: '1 trazo' }).waitFor();
    const cdps = await context.newCDPSession(page);
    const touch = async (type, xx, yy) => cdps.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x: xx, y: yy }] });
    await touch('touchStart', x + 90, y + 20);
    for (let i = 1; i <= 8; i++) await touch('touchMove', x + 90 + i * 4, y + 20 + i * 5);
    await touch('touchEnd', 0, 0);
    await page.locator('#drawing-hint').filter({ hasText: '2 trazos' }).waitFor();
    await page.getByRole('button', { name: 'Rectángulo', exact: true }).click();
    await page.mouse.move(x - 5, y - 15); await page.mouse.down();
    await page.mouse.move(x + 145, y + 100, { steps: 5 }); await page.mouse.up();
    await page.getByRole('button', { name: 'Flecha', exact: true }).click();
    await page.mouse.move(x + 110, y + 130); await page.mouse.down();
    await page.mouse.move(x + 45, y + 50, { steps: 5 }); await page.mouse.up();
    await page.locator('#drawing-hint').filter({ hasText: '4 trazos' }).waitFor();
    await page.getByRole('button', { name: 'Deshacer trazo', exact: true }).click();
    await page.locator('#drawing-hint').filter({ hasText: '3 trazos' }).waitFor();
    const redPixels = await canvas.evaluate(c => {
      const data = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      let count = 0; for(let i=0;i<data.length;i+=4) if(data[i]>190 && data[i+1]<70 && data[i+2]<70) count++;
      return count;
    });
    assert.ok(redPixels > 100, 'drawn strokes must be visible pixels');
    for (const [width,height] of [[360,800],[430,932],[768,1024],[1440,900],[1728,1117],[780,360]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(100);
      for (const locator of [page.locator('#drawing-tools')]) {
        const bounds = await locator.boundingBox();
        assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= width + 1 && bounds.y + bounds.height <= height + 1, 'editor fits viewport');
      }
      await page.screenshot({ path: resolve(output, `${app.sourceApp}-drawing-${width}.png`), fullPage: false });
    }
    await page.getByRole('button', { name: 'Comentar', exact: true }).click();
    await page.getByLabel('¿Qué querés cambiar?').fill('Mejorar el espacio de esta sección.');
    await page.getByRole('button', { name: 'Editar dibujo', exact: true }).click();
    await page.locator('#drawing-hint').filter({ hasText: '3 trazos' }).waitFor();
    await page.getByRole('button', { name: 'Comentar', exact: true }).click();
    await page.getByRole('button', { name: 'Guardar en la cola', exact: true }).click();
    await page.locator('#status').filter({hasText:'Guardado en este navegador'}).waitFor();
    assert.equal(posts.length, 0, 'saving must not submit');
    await page.reload();
    await page.getByRole('button', { name: 'Abrir feedback, 1 pendientes', exact: true }).click();
    await page.getByRole('button', { name: 'Ver pendientes (1)', exact: true }).click();
    assert.match(await page.locator('#queue').innerText(), /Mejorar el espacio/);
    fail = true;
    await page.getByRole('button', { name: 'Enviar a Codex', exact: true }).click();
    await page.locator('#status').filter({ hasText: '503' }).waitFor();
    assert.match(await page.locator('#queue').innerText(), /Mejorar el espacio/);
    fail = false;
    await page.getByRole('button', { name: 'Enviar a Codex', exact: true }).click();
    await page.locator('#status').filter({ hasText: 'Enviado a Codex' }).waitFor();
    assert.equal(posts.length, 2);
    assert.equal(posts[1].sourceApp, app.sourceApp);
    assert.equal(posts[1].releaseWhenComplete, false);
    assert.ok(posts[1].items[0].selectionPoints.length > 20);
    assert.deepEqual(posts[1].items[0].contextMetadata.annotations.strokes.map(s => s.tool), ['pen','pen','rectangle']);
    assert.ok(posts[1].items[0].screenshotPngBase64.length > 100);
    assert.equal(posts[1].workflowPresetId, 'default');
    assert.match(await page.locator('#queue').innerText(), /Todavía no/);
    await page.getByRole('button', { name: 'Nueva captura', exact: true }).click();
    await page.locator('#editor').waitFor({ state: 'visible' });
    await canvas.click({ position: { x: 20, y: 20 } });
    await page.locator('#drawing-hint').filter({ hasText: '1 trazo' }).waitFor();
    await page.getByRole('button', { name: 'Borrar dibujos', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Deshacer trazo', exact: true }).isDisabled(), true);
    await page.goto(app.production);
    assert.equal(await page.locator('[data-codex-feedback]').count(), 0);
    results.push({ app: app.sourceApp, passed: true, viewports: [360,430,768,1440,1728,780], checks: ['local queue', 'reload persistence', 'freehand mouse and touch', 'rectangle and arrow', 'undo', 'editable drawing', 'PNG pixels', 'native-size canvas and responsive floating toolbar', 'failed send preserves queue', 'batch contract', 'successful send clears queue', 'production hidden'] });
    await context.close();
  }
  await writeFile(resolve(output, 'browser-tests.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
} finally { await browser.close(); }
