# Decisión editorial y receta parametrizada

Trabajar desde `/home/batata/Projects/codex-cli-mobile-bridge` usando el Python
`/home/batata/.local/share/rd-video-lab/venv/bin/python`.

## Resumen previo

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/editorial.py \
  --source reports/rd-video-guia-20260929/body --output reports/mi-video/brief.json
```

Leé `brief.json` y escribí `pacing-plan.json`, sin servicio externo. Ejemplo completo
válido: `reports/rd-video-editorial-20260929/pacing-plan.json`. Usar sus valores como
referencia, no copiarlos indiscriminadamente a otras tareas.

El esquema tiene únicamente `version: 1`, `input_digest`, `editor: "Codex"` y
`scenes`. Cada escena contiene `lead_seconds`, `tail_seconds`, `pauses`, `reason`.
Cada pausa contiene `after_speech_seconds` (límite aprobado en el WAV) y `seconds`.
Cubrir exactamente los IDs del resumen. `input_digest` vincula audio, receta,
marcas y captura. Si cambian, regenerá el resumen y decidí nuevamente el plan.

Límites del validador: entrada 0,35–2,5 s, salida 0,5–4 s, pausas 0,25–2,5 s.
No mover los puntos de corte de voz sin revisar alineación y energía. Los tiempos
se aplican conjuntamente a voz, subtítulos, marcas y movimiento, por interpolación
local de las capturas. No se acelera el WAV ni se llama a un LLM.

## Ejecutar y revisar

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/run_guided.py \
  --source reports/rd-video-guia-20260929/body \
  --pacing-plan reports/mi-video/pacing-plan.json --output reports/mi-video
```

`run.json`, `render.json` y `guide-qc.json` conservan huellas, tiempos y resultados.
Se puede volver a ejecutar `editorial.py --source reports/mi-video/body` para ver
silencios medidos después. Las medidas son evidencia instrumental; el criterio
editorial sigue siendo responsabilidad del Codex activo.

Esta receta tiene IDs y captions RD. Para otra funcionalidad adaptar primero la
receta y su grabación; revisar `record_rd_v2.mjs`, `rd-documents.json`, `render_v2.py`
y los cortes de `pacing.py` sólo cuando sea necesario. El esquema actual rechaza
IDs ajenos para impedir una falsa sincronización. Mantener las comprobaciones
contra las nuevas acciones. Si faltan acceso local o capturas, explicitarlo.
