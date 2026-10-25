# Circuito local completo de aceptación

28/09/2026. Amplía [feedback](feedback-validation.md) y
[requerimientos](requirement-validation.md). Implementación local, sin despliegue.

## Del chat a un requerimiento

En Bridge DEV, un mensaje humano de la conversación principal dentro de un
workspace permitido conserva su contexto textual como `requirement_source`.
El prompt del agente incluye su ID y el comando para definir los criterios
antes de implementar. El original se obtiene del registro: el agente no lo
reemplaza al enviar los criterios. Los turnos internos de agentes no generan
nuevas fuentes automáticamente.

Esto captura la fuente; **el agente interpreta si es un pedido de implementación**.
Una pregunta o consulta de estado no se convierte automáticamente en requisito
ni bloquea un merge. Para feedback ya registrado debe reutilizar el caso existente.
No se promete clasificación infalible de cualquier conversación. Si el contexto
supera 10.000 caracteres, se indica registrar requisitos explícitos contra la
fuente completa; no se trunca silenciosamente para darlo por cubierto.

Desde el checkout del Bridge:

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER sources --workspace RUTA_APP
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER requirement-from-source ID_SOURCE --file CRITERIOS.json
```

`CRITERIOS.json` admite `requirement_id`, `project_id`, `environment` y `criteria`
(lista de `id` y `description`). No admite `text` ni `source_ref`: los recupera
del mensaje conservado. API equivalente: `GET /pipeline-quality/sources` con
workspace y `POST /pipeline-quality/sources/{id}/requirements`.

Después se vincula el contrato y plan existentes, se implementa, ejecuta y
evalúa. El generador recibe también los pedidos activos del workspace. Con
**Generador + revisor**, la evidencia pendiente vuelve al generador dentro del
presupuesto configurado. No se alteraron los presets ni se añadieron vueltas
ilimitadas. Usar ese preset para el flujo de revisión independiente.

La recepción sigue disponible aunque haya una prueba ejecutándose: la captura
inmutable se serializa en SQLite, sin exigir el bloqueo exclusivo del runner.

## Cambio legítimo de alcance

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER revise-requirement ID_ANTERIOR --file REVISION.json
```

El archivo contiene `definition` (nueva definición completa, con otro
requirement_id), `reason` y `decision_ref` (referencia a la decisión que autorizó
el cambio). Se exige el mismo proyecto, workspace y ambiente. API:
`POST /pipeline-quality/requirements/{id}/revise`.

Se conserva el original y se registra su sustitución. La revisión no hereda
aprobaciones ni pruebas de la anterior. El nuevo alcance empieza pendiente.
La escritura del nuevo pedido, la relación y los cambios de estado de paquetes
se hace en una transacción. Los reintentos equivalentes son idempotentes y no
se permiten ciclos ni reutilizar un requisito existente como sustituto.

Un paquete dedicado exclusivamente al requisito anterior queda `superseded` y
sale de la cola activa. Si mezclaba otros requisitos, sigue activo y debe
revisarse su contrato: no se descartan las otras obligaciones. Las dependencias
también deben actualizarse explícitamente; no se consideran satisfechas por
una tarea sustituida. `reason` y `decision_ref` son registros del operador,
no una firma ni una autorización humana verificadas por el sistema.

## Repetición manual

La lectura de un pedido devuelve `technical_verified`, `verified`,
`human_review` y, cuando existe plan vigente, `evidence_key`.

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER request-status ID_REQUEST
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER manual-review ID_REQUEST --file REPETICION.json
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER request-history ID_REQUEST
```

`REPETICION.json`:

```json
{
  "evidence_key": "HASH_ACTUAL_DEVUELTO_POR_EL_SERVIDOR",
  "outcome": "confirmed",
  "note": "Repetí el caso y ahora se cumple",
  "decision_ref": "chat:REFERENCIA_REAL_DE_LA_RESPUESTA",
  "actor_label": "PERSONA_QUE_REALMENTE_LO_PROBO"
}
```

Alternativas: `still_failing` e `inconclusive`. API:
`POST /pipeline-quality/requests/{id}/manual-review` y
`GET /pipeline-quality/requests/{id}/history`.

Para alcance `deployed`, el archivo debe incluir además `observed_target`
con exactamente el `environment`, `origin` y `release_id` del destino probado.
El operador debe registrar la versión observada al repetir el caso. Se rechaza
otra versión o ambiente; el sistema no descubre por sí solo qué versión estaba
viendo la persona.

- Una confirmación no reemplaza pruebas técnicas faltantes o fallidas.
- La clave vincula pedido, plan, fuente, recibos, destino y evaluación. Si
  cambiaron, se rechaza una confirmación enviada desde una vista antigua.
- «Sigue fallando» reabre el paquete, mantiene pendiente el pedido y bloquea
  cierre, exportación como verificado y trabajos dependientes.
- Volver a aprobar tests no borra ese reporte manual. Se requiere una nueva
  confirmación con la evidencia vigente. «No pude comprobar» no borra el fallo.
- Una confirmación anterior no equivale a haber probado una versión posterior.

Son respuestas **registradas por un operador** con atribución declarada. No se
añadió una firma de identidad de Bruno ni aceptación comercial o autorización
de producción. El agente puede registrar la respuesta explícita recibida en el
chat; no debe inventarla. No se añadieron botones nuevos en Gestión o un APK.

## Alcance entre proyectos y preparación de activación

`PIPELINE_QUALITY_PROJECT_ROOTS` permite una lista separada por comas de
workspaces de apps autorizados, además del worktree del Bridge. Queda vacío
por defecto. Para Gestión DEV debe apuntar al checkout de `develop` correcto,
y `FEEDBACK_SOURCE_WORKSPACE_ALIASES` debe mapear `nienfos-gestion` al mismo
checkout. No ampliar la raíz a todo el disco para evitar un error de mapeo.

El backend y la CLI deben usar la misma `PIPELINE_QUALITY_DATABASE`. Los
launchers foreground/detached ya admiten estas variables y las opciones de
Jev desde su archivo de entorno. No se cambiaron `.env`, claves, procesos ni
URLs del entorno publicado. `PIPELINE_QUALITY_JEV_ENABLED` sigue apagado por
defecto; una CLI con `--jev` habilita la consulta para esa operación.

## Pruebas locales reproducibles

```sh
.venv/bin/python -m pytest tests/test_acceptance_workflow.py tests/test_requirement_validation.py tests/test_feedback_validation.py tests/test_pipeline_quality.py tests/test_pipeline_feedback_dependencies.py -q
.venv/bin/python -m pytest tests/test_message_flow.py -k 'dev_chat_captures or feedback_batch or terminal_reviewer_response' -q
.venv/bin/python -m pytest tests/test_dev_pipeline.py tests/test_backend_process_scripts.py -q
.venv/bin/python scripts/jev_lab/acceptance_browser_demo.py --node RUTA_NODE_20_O_SUPERIOR --output reports/MI_PRUEBA_LOCAL
```

La demostración levanta y cierra una app temporal sólo en loopback, con SQLite
y datos sintéticos. Playwright guarda un cliente, vuelve a la lista y recarga.
Primero reproduce un defecto real de la función de listado y después ejecuta
una reparación predeterminada. Las capturas muestran explícitamente que es
laboratorio. Sin `--live-jev` usa una respuesta simulada; esa opción permite
como máximo una consulta real con resumen y hechos sintéticos, sin adjuntos.

No es Gestión DEV, no mide productividad de un agente programando por sí solo
y no reemplaza el piloto futuro contra el release autorizado. Antes de publicar,
se pueden verificar código, tests y flujo local. El requisito «comprobado en
DEV» queda pendiente hasta ejecutar contra el despliegue real: no se rebaja a
alcance local para marcarlo cumplido.
