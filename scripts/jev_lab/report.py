#!/usr/bin/env python3
"""Build a mobile-readable, offline report using recorded results only."""
import argparse
import hashlib
import json
from pathlib import Path

from lab import HERE

NAMES={'closure':'Cobertura de requisitos','retrieval':'Selección de contexto','scope':'Alcance',
       'coherence':'Coherencia documental','feedback':'Relación de feedback','regression':'Selección de regresión',
       'noul':'Control Noul','score':'Control Score'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report-root',type=Path,required=True)
    p.add_argument('--cases',type=Path,default=HERE/'cases.json')
    p.add_argument('--stem',default='resultados')
    args=p.parse_args();root=args.report_root
    dataset=json.loads(args.cases.read_text())
    digest=hashlib.sha256(args.cases.read_bytes()).hexdigest()
    runs=[]
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'metrics.json').is_file():continue
        run_meta=json.loads((folder/'run.json').read_text())
        if run_meta['dataset_sha256']!=digest:continue
        runs.append({'name':folder.name,'run':run_meta,
                     'metrics':json.loads((folder/'metrics.json').read_text()),
                     'rows':[json.loads(line) for line in (folder/'predictions.jsonl').read_text().splitlines()]})
    table=[]
    for family,title in NAMES.items():
        cells=[]
        for run in runs:
            f=run['metrics']['families'].get(family)
            cells.append(f"{f['correct']}/{f['cases']}" if f else 'Sin resultados')
        table.append('| '+title+' | '+' | '.join(cells)+' |')
    text='# Resultados registrados del laboratorio\n\n'
    text+='Las etiquetas son sintéticas y no tienen revisión independiente. Las variantes no agregan casos independientes. No hay ahorro humano medido.\n\n'
    text+='| Familia | '+' | '.join(r['name'] for r in runs)+' |\n'
    text+='|---|'+'---|'*len(runs)+'\n'+'\n'.join(table)+'\n\n'
    text+='Score cuenta error absoluto ≤ 0,5. Noul usa corte 0,5. La referencia baseline usa reglas simples y decisiones conservadoras; no representa un sistema de reglas optimizado. En la sensibilidad de Score se cuentan diferencias del valor numérico, aunque no cambie el nivel más cercano.\n\n'
    for run in runs:
        m=run['metrics'];text+=f"## {run['name']}\n\n"
        text+=f"- Estado: `{run['run']['status']}`. Intentos: {m['attempts']}; respuestas válidas: {m['valid_responses']}; errores: {m['errors']}.\n"
        if m['latency_p50_ms'] is not None:
            text+=f"- Mediana: {m['latency_p50_ms']} ms; p95: {m['latency_p95_ms']} ms.\n"
        else:
            text+='- Sin respuestas válidas para medir latencia de inferencia.\n'
        text+=f"- [Métricas completas]({run['name']}/metrics.json) · [Predicciones]({run['name']}/predictions.jsonl) · [Identidad de ejecución]({run['name']}/run.json).\n"
        for name,value in m['robustness'].items():
            text+=f"- {name}: {value['changed']} cambios entre {value['paired_cases']} pares; {value['accuracy_losses']} aciertos originales se vuelven errores.\n"
        text+='\n'
        if m['reported_cost_usd'] is not None:
            text+=f"- Costo reportado: USD {m['reported_cost_usd']:.8f} ({m['responses_with_reported_cost']} respuestas con costo).\n\n"
    (root/(args.stem+'.md')).write_text(text)
    live=[r for r in runs if r['run']['provider'] in ('openrouter','typesafe','cloudflare') and r['metrics']['valid_responses']>0]
    live_count=sum(r['metrics']['valid_responses'] for r in live)
    data=json.dumps({'cases':dataset['cases'],'runs':runs,'names':NAMES},ensure_ascii=False).replace('<','\\u003c')
    template='''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jev · Laboratorio Nienfos</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f4;color:#203a32;font:16px/1.55 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px 18px 60px}a{color:#17654d}nav{display:flex;justify-content:space-between;gap:14px;font-size:13px;flex-wrap:wrap}h1{font-size:38px;line-height:1.12;letter-spacing:-.04em;margin:30px 0 12px}h2{font-size:20px;line-height:1.3}.lead{color:#54665d}.status{background:#fff3da;border-left:4px solid #b7862c;padding:14px 16px;margin:24px 0}.filters{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}label{flex:1;min-width:145px;font-size:12px;font-weight:700}select{display:block;width:100%;padding:12px;margin-top:6px;border:1px solid #b9c8be;background:white;border-radius:8px;color:#203a32}#summary{background:#e6eee8;padding:18px;border-radius:12px;font-size:14px}.card{background:white;border:1px solid #d7e1db;border-radius:12px;padding:19px;margin:14px 0;overflow-wrap:anywhere}.meta{font-size:12px;color:#566c60}.outcome{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.pill{background:#edf2ef;padding:6px 10px;border-radius:6px;font-size:13px}.wrong{background:#fbe5de;color:#823e2c}.right{background:#e0f0e3;color:#265a35}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 system-ui,sans-serif;margin:10px 0}.muted{font-size:13px;color:#53685d}.table{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;border-bottom:1px solid #dce4de;padding:8px}summary{cursor:pointer;color:#17654d;font-size:13px}footer{border-top:1px solid #ccd9cf;margin-top:30px;padding-top:20px;font-size:14px}@media(max-width:500px){h1{font-size:32px}}
</style><main><nav><b>NIENFOS / LABORATORIO</b><a href="../../scripts/jev_lab/README.md">Pasos para activar Jev ↗</a></nav><h1>Medir antes de incorporar.</h1><p class="lead">73 casos de trabajo, con decisiones esperadas y variantes para comprobar estabilidad. Resultados registrados, sin datos de clientes.</p><div class="status"><b>Jev: pendiente de acceso.</b><br>Cloudflare devolvió HTTP 401. El SDK está instalado; esa instalación no demuestra inferencia. Los resultados locales pertenecen a Laya y a una referencia simple.</div>
<div class="filters"><label>Corrida<select id="run"></select></label><label>Familia<select id="family"><option value="all">Todas</option></select></label><label>Mostrar<select id="filter"><option value="all">Todos los casos</option><option value="wrong">Errores originales</option><option value="unstable">Cambios entre variantes</option></select></label></div><div id="summary" aria-live="polite"></div><div id="cards"></div><footer><p>La ventaja sobre una referencia sencilla no prueba ahorro operativo. Faltan etiquetas revisadas, casos reales sanitizados y tiempos de revisión medidos.</p><a href="resultados.md">Tabla y evidencia de las corridas</a> · <a href="revision-humana.csv">Plantilla de medición humana</a></footer></main><script type="application/json" id="data">__DATA__</script><script>
const data=JSON.parse(document.querySelector('#data').textContent),runSelect=document.querySelector('#run'),familySelect=document.querySelector('#family');
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
for(const [i,r] of data.runs.entries()){const o=el('option',r.name);o.value=i;runSelect.append(o);if(r.name==='laya')o.selected=true}
for(const [id,name] of Object.entries(data.names)){const o=el('option',name);o.value=id;familySelect.append(o)}
function render(){const run=data.runs[Number(runSelect.value)],family=familySelect.value,filter=document.querySelector('#filter').value,container=document.querySelector('#cards');container.replaceChildren();if(!run)return;let count=0;for(const c of data.cases){if(family!=='all'&&c.family!==family)continue;const rows=run.rows.filter(r=>r.id===c.id),base=rows.find(r=>r.variant==='original'&&r.repeat===0);const unstable=base&&rows.some(r=>r.predicted!==undefined&&r.predicted!==base.predicted);if(filter==='wrong'&&(!base||base.correct!==false))continue;if(filter==='unstable'&&!unstable)continue;count++;const card=el('article',undefined,'card');card.append(el('div',data.names[c.family]+' · '+c.id,'meta'));const state=typeof c.state==='string'?c.state:JSON.stringify(c.state,null,2);card.append(el('pre',state));const outcome=el('div',undefined,'outcome');outcome.append(el('span','Esperado: '+c.expected,'pill'));if(base&&base.predicted!==undefined)outcome.append(el('span','Obtenido: '+base.predicted,'pill '+(base.correct?'right':'wrong')));else outcome.append(el('span',base&&base.error?'Error de acceso/contrato':'Sin ejecutar','pill'));if(unstable)outcome.append(el('span','Cambió con variantes','pill wrong'));card.append(outcome);const detail=el('details');detail.append(el('summary','Ver pregunta, variantes y tiempos'));detail.append(el('pre',JSON.stringify(c.question,null,2)));for(const r of rows)detail.append(el('p',r.variant+' · repetición '+(r.repeat+1)+' · '+(r.predicted??r.error?.reason??'sin respuesta')+' · '+r.latency_ms+' ms','muted'));card.append(detail);container.append(card)}const m=run.metrics;document.querySelector('#summary').textContent=count+' casos visibles · '+m.valid_responses+' respuestas válidas / '+m.attempts+' intentos · Estado: '+run.run.status+'. Cada variante sigue perteneciendo al mismo caso.'}
for(const id of ['run','family','filter'])document.getElementById(id).addEventListener('change',render);render();
</script></html>'''
    if live:
        template=template.replace('<b>Jev: pendiente de acceso.</b><br>Cloudflare devolvió HTTP 401. El SDK está instalado; esa instalación no demuestra inferencia. Los resultados locales pertenecen a Laya y a una referencia simple.',
            f'<b>Jev: {live_count} respuestas reales registradas.</b><br>La conexión por API funciona. Compará cada decisión con su respuesta esperada. Este corpus exploratorio todavía no mide ahorro humano.')
    template=template.replace('73 casos de trabajo',str(len(dataset['cases']))+' entradas de prueba')
    template=template.replace('Pasos para activar Jev','Instrucciones del laboratorio')
    template=template.replace("if(r.name==='laya')o.selected=true", "if(r.run.provider==='openrouter'&&r.metrics.valid_responses>0)o.selected=true")
    template=template.replace('href="resultados.md"','href="'+args.stem+'.md"')
    (root/(args.stem+'.html')).write_text(template.replace('__DATA__',data))
    print('Resultados Markdown y HTML generados a partir de las corridas registradas.')


if __name__=='__main__':main()
