#!/usr/bin/env python3
"""Render recorded evidence as an offline, mobile-friendly demonstration."""

import argparse
import json
from pathlib import Path


TEMPLATE = r"""<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Un comentario comprobado demasiado pronto · Nienfos</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#192b32;background:#f3f6f4;font-synthesis:none}*{box-sizing:border-box}body{margin:0}main{max-width:860px;margin:auto;padding:28px 20px 50px}header{margin-bottom:26px}.eyebrow{font-size:12px;font-weight:750;letter-spacing:.12em;text-transform:uppercase;color:#48675c}h1{font-size:clamp(29px,6vw,44px);line-height:1.12;letter-spacing:-.035em;margin:14px 0}p{line-height:1.55}.intro{font-size:17px;color:#4d6167}.notice{font-size:13px;border-left:3px solid #527a68;padding-left:12px;color:#4d6167}.controls{display:flex;gap:8px;margin:24px 0 14px}button{font:inherit;cursor:pointer;border:1px solid #b7c8be;background:white;color:#213b30;border-radius:10px;padding:13px 15px;flex:1;font-weight:650}button[aria-pressed=true]{background:#183e31;color:#fff;border-color:#183e31}button:focus-visible,a:focus-visible{outline:3px solid #ba7800;outline-offset:3px}.panel{background:white;border:1px solid #d8e3dd;border-radius:18px;padding:22px;margin:16px 0;box-shadow:0 7px 25px #1c39270a}.label{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:#657871;font-weight:700}h2{font-size:23px;letter-spacing:-.02em;margin:8px 0 18px}.row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:15px 0;border-bottom:1px solid #e8efeb}.row:last-of-type{border:0}.row span:first-child{max-width:65%;line-height:1.35}.badge{border-radius:7px;padding:5px 8px;font-size:13px;font-weight:750;white-space:nowrap}.good{background:#e1f4e9;color:#145137}.pending{background:#fff0cf;color:#734d04}.bad{background:#ffe3e0;color:#8f2d26}.explanation{padding:15px;background:#f3f6f4;border-radius:10px;margin:14px 0 0;line-height:1.5}.timeline{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:13px}.timeline div{background:#f2f6f3;border-radius:9px;padding:12px;line-height:1.5}.timeline b{display:block;margin-bottom:5px}code{font-family:ui-monospace,monospace;font-size:12px;overflow-wrap:anywhere}details{margin:16px 0}summary{cursor:pointer;line-height:1.5}pre{font-size:11px;overflow:auto;background:#eff4f1;padding:12px;border-radius:8px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px}.metric{padding:16px;border:1px solid #d8e3dd;border-radius:12px}.metric b{display:block;font-size:23px;margin:6px 0}.metric small{color:#576c62}a{color:#165b43;text-underline-offset:3px}footer{font-size:13px;color:#596e66;line-height:1.55;margin-top:25px}.next{font-size:15px}.caption{font-size:13px;color:#536a60}@media(max-width:450px){main{padding:22px 16px 35px}.panel{padding:18px}.timeline{grid-template-columns:1fr}.timeline div{display:flex;gap:12px;align-items:baseline}.timeline b{margin:0}.metrics{gap:8px}.metric{padding:12px}.metric b{font-size:20px}}
</style>
<main>
<header><div class="eyebrow">Nienfos / Evidencia de desarrollo</div><h1>Decía “comprobado”.<br>Faltaba una condición.</h1><p class="intro">Encontramos y corregimos un fallo real en el código nuevo del Bridge: el estado de un comentario ignoraba una dependencia pendiente.</p><p class="notice">Demostración local · datos de prueba aislados.<br>Esta página muestra resultados registrados; no es Gestión publicada.</p></header>
<div class="controls" role="group" aria-label="Comparar versiones"><button id="before" aria-pressed="false">Antes de corregir</button><button id="after" aria-pressed="true">Después</button></div>
<section class="panel" aria-live="polite"><div class="label" id="version"></div><h2>Comentario de desarrollo</h2><div class="row"><span>Prueba propia del trabajo</span><span class="badge good">Aprobada</span></div><div class="row"><span>Dependencia requerida, después de un cambio</span><span class="badge pending">Sin validar</span></div><div class="row"><span>Estado que devuelve el Bridge para el comentario</span><span id="feedback" class="badge"></span></div><p id="explanation" class="explanation"></p></section>
<section class="panel"><div class="label">Tres momentos del mismo caso</div><h2>Qué pasa al cambiar la dependencia</h2><div id="timeline" class="timeline"></div><p class="caption">La prueba propia del comentario no cambió. Lo que cambió fue la vigencia de la evidencia de su dependencia.</p><details><summary>Ver datos registrados de esta versión</summary><pre id="raw"></pre></details></section>
<section class="panel"><div class="label">Control de calidad</div><h2>El runner detectó la inconsistencia</h2><p>La nueva prueba falló con el código anterior y bloqueó el cierre técnico. Con la corrección, la misma prueba aprobó. Otro cambio de fuente volvió a exigir una comprobación.</p><div class="metrics"><div class="metric"><small>Condiciones comprobadas</small><b id="checks"></b><small>en el recorrido aislado</small></div><div class="metric"><small>Pruebas de regresión</small><b>35 aprobadas</b><small>motor y feedback</small></div></div></section>
<section class="panel"><div class="label">Qué aportó Jev</div><h2 id="cause"></h2><p id="model"></p><p>La inspección y la corrección las hizo el desarrollador. Jev recibió el fallo de la prueba y sugirió una categoría de causa. No aprobó el trabajo ni escribió la solución.</p><p class="explanation"><strong>Resultado:</strong> comprobamos que el control encuentra este fallo. Todavía no medimos si Jev reduce el tiempo o la intervención humana.</p></section>
<p class="next"><a href="informe.md">Leer el informe y reproducir el caso</a> · <a href="resultados.json">Abrir la evidencia completa</a></p>
<footer>27/09/2026 · Código local, sin despliegue ni datos de clientes. El defecto se observó en la implementación antes de activarla. Los datos del escenario son fixtures; la lógica probada es la del Bridge.</footer>
</main>
<script id="evidence" type="application/json">__EVIDENCE__</script>
<script>
const data=JSON.parse(document.getElementById('evidence').textContent);
const labels={verified:'Comprobado',blocked:'Bloqueado',unverified:'Sin comprobar',failed:'Falló'};
function show(mode){const before=mode==='before'; const observed=data[before?'before_fix':'after_fix'];const changed=observed.dependency_changed; document.getElementById('version').textContent=before?'Versión anterior · fallo observado':'Versión corregida · prueba aprobada'; for(const name of ['before','after'])document.getElementById(name).setAttribute('aria-pressed',String(name===mode));const badge=document.getElementById('feedback');badge.textContent=labels[changed.feedback_status];badge.className='badge '+(before?'bad':'pending');document.getElementById('explanation').textContent=before?'El comentario aparecía comprobado aunque el trabajo tenía una dependencia sin validar. La nueva prueba detectó esta contradicción.':'El comentario queda bloqueado y conserva la causa. Recupera el estado comprobado al volver a validar la dependencia.';const timeline=document.getElementById('timeline');timeline.replaceChildren();for(const [key,title] of [['before','1. Todo validado'],['dependency_changed','2. Dependencia cambia'],['dependency_rechecked','3. Se vuelve a probar']]){const item=document.createElement('div');const heading=document.createElement('b');heading.textContent=title;const value=document.createElement('span');value.textContent=labels[observed[key].feedback_status];item.append(heading,value);timeline.append(item);}document.getElementById('raw').textContent=JSON.stringify(observed,null,2);}
document.getElementById('before').onclick=()=>show('before');document.getElementById('after').onclick=()=>show('after');show('after');
document.getElementById('checks').textContent=Object.values(data.checks).filter(Boolean).length+' / '+Object.keys(data.checks).length;
const advice=data.jev;const cause=advice.answers?.cause;document.getElementById('cause').textContent=cause?.choice==='code'?'Señaló “problema de código”':cause?'Sugirió: '+cause.choice:'No hubo respuesta del modelo';
document.getElementById('model').textContent=advice.status==='answered'?`Una consulta real · ${Math.round(advice.latency_ms)} ms · USD ${Number(advice.cost).toFixed(8)}. Modelo: ${advice.resolved_model}.`:'Estado de la consulta: '+advice.status;
</script></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    args.output.write_text(
        TEMPLATE.replace(
            "__EVIDENCE__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        )
    )


if __name__ == "__main__":
    main()
