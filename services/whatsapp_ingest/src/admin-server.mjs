import http from 'node:http'

const dashboardHtml = `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>WhatsApp Intake · Nienfos</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #0b1412; color: #e8f3ef; }
    main { width: min(920px, calc(100% - 32px)); margin: 32px auto; }
    .card { background: #14231f; border: 1px solid #294039; border-radius: 18px; padding: 22px; margin: 16px 0; }
    h1, h2 { margin: 0 0 14px; }
    .status { display: inline-flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: 999px; background: #20342e; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: #d5a53a; }
    .connected .dot { background: #31c48d; }
    .logged_out .dot, .error .dot { background: #f05252; }
    #qr { width: min(320px, 100%); background: white; border-radius: 14px; padding: 12px; display: none; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 9px 6px; border-bottom: 1px solid #294039; }
    code { color: #9ee7ce; overflow-wrap: anywhere; }
    .muted { color: #9eb4ad; }
  </style>
</head>
<body>
<main>
  <h1>WhatsApp Intake</h1>
  <p class="muted">Receptor silencioso de grupos · acceso privado por Tailscale</p>
  <section class="card">
    <div id="status" class="status"><span class="dot"></span><span>Consultando…</span></div>
    <p id="detail" class="muted"></p>
    <img id="qr" alt="Código QR para vincular WhatsApp">
  </section>
  <section class="card">
    <h2>Grupos detectados</h2>
    <table><thead><tr><th>Grupo</th><th>Proyecto / bandeja</th><th>Estado</th><th>Draft</th><th>ID</th></tr></thead><tbody id="groups"></tbody></table>
  </section>
  <section class="card">
    <h2>Últimas capturas</h2>
    <table><thead><tr><th>Hora</th><th>Proyecto</th><th>Tipo</th><th>Estado</th></tr></thead><tbody id="recent"></tbody></table>
  </section>
</main>
<script>
const text = (value) => document.createTextNode(value == null ? '' : String(value));
function cell(row, value, code = false) { const td = document.createElement('td'); const el = code ? document.createElement('code') : td; if (code) td.appendChild(el); el.appendChild(text(value)); row.appendChild(td); }
async function refresh() {
  const response = await fetch('/whatsapp/api/status', { cache: 'no-store' });
  const data = await response.json();
  const status = document.getElementById('status');
  status.className = 'status ' + data.connection;
  status.lastElementChild.textContent = data.connection_label;
  document.getElementById('detail').textContent = data.detail || '';
  const qr = document.getElementById('qr');
  if (data.qr_available) { qr.src = '/whatsapp/qr.png?t=' + Date.now(); qr.style.display = 'block'; } else { qr.style.display = 'none'; qr.removeAttribute('src'); }
  const groups = document.getElementById('groups'); groups.replaceChildren();
  for (const group of data.groups) { const row = document.createElement('tr'); cell(row, group.subject || 'Sin nombre'); cell(row, group.project || group.inbox_project || 'Sin asignar'); cell(row, group.status || 'desconocido'); cell(row, group.project_factory_draft_id || group.draft_status || '—', true); cell(row, group.id, true); groups.appendChild(row); }
  const recent = document.getElementById('recent'); recent.replaceChildren();
  for (const item of data.recent) { const row = document.createElement('tr'); cell(row, item.received_at); cell(row, item.project); cell(row, item.kind); cell(row, item.status); recent.appendChild(row); }
}
refresh().catch(console.error); setInterval(() => refresh().catch(console.error), 2500);
</script>
</body>
</html>`

export function createAdminServer({ state, host, port, logger }) {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url || '/', 'http://localhost')
    const pathname = stripPublicPrefix(url.pathname)
    if (request.method !== 'GET') return sendJson(response, 405, { error: 'method_not_allowed' })

    if (pathname === '/' || pathname === '/index.html') {
      return send(response, 200, 'text/html; charset=utf-8', dashboardHtml)
    }
    if (pathname === '/health') {
      return sendJson(response, 200, {
        status: 'ok',
        connection: state.connection,
        captured_messages: state.capturedMessages,
      })
    }
    if (pathname === '/api/status') {
      return sendJson(response, 200, state.snapshot())
    }
    if (pathname === '/qr.png') {
      if (!state.qrPng) return sendJson(response, 404, { error: 'qr_unavailable' })
      return send(response, 200, 'image/png', state.qrPng)
    }
    return sendJson(response, 404, { error: 'not_found' })
  })

  server.listen(port, host, () => {
    logger.info({ host, port }, 'WhatsApp admin server listening')
  })
  return server
}

function stripPublicPrefix(pathname) {
  if (pathname === '/whatsapp') return '/'
  if (pathname.startsWith('/whatsapp/')) return pathname.slice('/whatsapp'.length)
  return pathname
}

function sendJson(response, status, payload) {
  return send(response, status, 'application/json; charset=utf-8', `${JSON.stringify(payload)}\n`)
}

function send(response, status, contentType, body) {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'Content-Type': contentType,
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
  })
  response.end(body)
}
