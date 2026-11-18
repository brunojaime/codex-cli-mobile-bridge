import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { readFileSync } from 'node:fs';

const [playwrightModule, output] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(playwrightModule).href);
const origin = `http://127.0.0.1:${readFileSync('.runtime/port', 'utf8')}`;
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const before = await (await context.request.get(`${origin}/version`)).json();
  await page.goto(origin);
  await page.getByLabel('Nombre de prueba').fill('Cliente de laboratorio');
  await page.getByRole('button', { name: 'Guardar cliente' }).click();
  await page.locator('#saved[data-id]').waitFor();
  const id = await page.locator('#saved').getAttribute('data-id');
  const persisted = await (await context.request.get(`${origin}/api/clients/${id}`)).json();
  await page.goto(origin);
  await page.getByText('Lista actualizada', { exact: true }).waitFor();
  const visibleOnReturn = await page.locator(`[data-client-id="${id}"]`).count() === 1;
  await page.reload();
  await page.getByText('Lista actualizada', { exact: true }).waitFor();
  const visibleAfterReload = await page.locator(`[data-client-id="${id}"]`).count() === 1;
  const after = await (await context.request.get(`${origin}/version`)).json();
  const facts = { persisted: persisted?.id === Number(id), return_visible: visibleOnReturn, reload_visible: visibleAfterReload, same_release: before.release_id === after.release_id };
  await page.screenshot({ path: join(output, visibleAfterReload ? 'corregido.png' : 'fallo.png'), fullPage: true });
  console.log('NIENFOS_OBSERVATIONS_V1 ' + JSON.stringify({ observations: facts }));
  process.exitCode = Object.values(facts).every(Boolean) ? 0 : 1;
} finally { await browser.close(); }
