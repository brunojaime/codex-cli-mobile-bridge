# Mejoras pedidas → implementación → comprobación

Implementado localmente el 28/09/2026 sobre el ledger de calidad existente.
No crea otro gestor de incidencias. El resultado pertenece al pedido de feedback,
su contrato, sus pruebas y una versión concreta. No constituye aceptación
comercial, confirmación de Bruno ni autorización para publicar.

También admite [requerimientos nuevos sin captura de feedback](requirement-validation.md),
con criterios originales que el plan debe conservar.

## Qué hace el circuito

1. El envío de un lote al **Bridge DEV** conserva el comentario y las
   transcripciones originales, redactando patrones conocidos de secretos.
   Las capturas de un recorrido y las notas asociadas se agrupan por sus
   identificadores explícitos. No se fusionan pedidos por parecido textual.
2. El agente recibe ese pedido y debe preparar criterios y un plan de
   comprobación. Reutiliza `QualityContract`, `feedback_item_id`, comandos y
   recibos existentes. No se añadió un segundo LLM extractor.
3. Implementa y ejecuta los checks registrados. Cada check debe observar el
   comportamiento real y emitir los hechos exigidos por el plan.
4. Si falta evidencia, hay fallos o no coincide el despliegue, las reglas dejan
   el pedido pendiente o incumplido **sin consultar a Jev**.
5. Con pruebas suficientes y aprobadas, Jev recibe una descripción minimizada
   del pedido y los hechos estructurados. Evalúa si esos hechos cubren lo pedido.
   Su respuesta puede impedir el cierre, pero no convertir una prueba fallida
   en aprobada. Sus probabilidades no se usan como umbral ni certeza calibrada.
6. El resultado se devuelve en `resolution.improvements`, uno por pedido padre,
   y en el resumen de feedback que ya consume la app. La terminación del job se
   mantiene separada: `completed` no equivale a mejora comprobada.

Con un preset que incluye revisor, los pendientes vuelven al generador dentro
del presupuesto de vueltas existente. Un preset de sólo generador conserva
el pendiente y el resumen, pero no adquiere mágicamente un ciclo de revisión.
Los presets no se cambiaron en esta implementación.

Estados: `fulfilled`, `partial`, `not_fulfilled`, `insufficient_evidence`.
Jev apagado, ocupado o con error deja la evaluación semántica pendiente cuando
no existe una evaluación previa vigente.
Las pruebas técnicas pueden estar aprobadas al mismo tiempo: son estados distintos.

## Ejemplo: el cliente guardado debe aparecer al volver

Pedido original: «Creo un cliente, guardo y al volver no aparece en la cartera».
Antes de corregir, conservar el filtro original y distinguir persistencia,
filtro activo y falta de actualización. No cambiar el filtro silenciosamente
para hacer aprobar una prueba que ya no reproduce el problema.

Un contrato posible en `.codex/quality.json` de la app:

```json
{
  "version": 1,
  "project_id": "SOURCE_APP_REAL",
  "environment": "dev",
  "criteria": [{
    "id": "cliente-visible",
    "description": "El cliente creado aparece al volver y después de recargar, con el usuario y filtro acordados",
    "feedback_item_id": "ID_PADRE_REAL",
    "check_ids": ["cliente-en-dev"]
  }],
  "checks": [{
    "id": "cliente-en-dev",
    "argv": ["node", "scripts/check-client-feedback.mjs"],
    "timeout_seconds": 120
  }]
}
```

**El script es específico de la app y aún debe escribirse para este piloto.**
No se añadió un test universal que pueda reproducir cualquier recorrido.
Debe usar datos de prueba permitidos en DEV, leer la identidad real del
despliegue, crear el cliente, comprobar persistencia, volver a la cartera y
comprobar visibilidad después de recargar. No registrar nombres, cookies o
cuerpos de peticiones en el resumen enviado al modelo.

Desde la raíz del Bridge, con su Python y la misma SQLite del backend:

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER feedback-list --workspace RUTA_APP
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER register --workspace RUTA_APP --work-item ID_TRABAJO --stage-id ID_STAGE
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER feedback-plan ID_REQUEST --file PLAN.json
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER run ID_PACKET --attempt intento-1
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER feedback-status ID_REQUEST
```

Reemplazar los identificadores con los devueltos por el ledger. `--stage-id`
sólo corresponde cuando existe una etapa de desarrollo asociada. No reemplazar
otros checks obligatorios del proyecto al registrar este contrato.

`PLAN.json` (los valores entre mayúsculas son marcadores, no datos ejecutables):

```json
{
  "version": 1,
  "request_digest": "HASH_SHA256_DEL_PEDIDO",
  "packet_id": "ID_PACKET",
  "semantic_brief": "Un cliente creado debe aparecer al volver a la cartera y seguir visible después de recargar, con el mismo usuario y filtro acordados.",
  "scope": "deployed",
  "target": {
    "environment": "dev",
    "origin": "https://ORIGEN_DEV_REAL",
    "release_id": "IDENTIDAD_RELEASE_REAL"
  },
  "observations": [
    {"id":"persistido","criterion_id":"cliente-visible","check_id":"cliente-en-dev","description":"El cliente guardado se recupera por su ID dentro del alcance del usuario"},
    {"id":"al-volver","criterion_id":"cliente-visible","check_id":"cliente-en-dev","description":"El cliente aparece al volver a la cartera con el usuario y filtro acordados"},
    {"id":"al-recargar","criterion_id":"cliente-visible","check_id":"cliente-en-dev","description":"El cliente sigue visible al recargar esa misma cartera"}
  ]
}
```

El check emite **una sola línea** con el prefijo `NIENFOS_OBSERVATIONS_V1 `,
seguido de JSON con esta forma (ejemplo de resultado parcial):

```json
{
  "observations": {"persistido": true, "al-volver": true, "al-recargar": false},
  "target_before": {"environment":"dev","origin":"https://ORIGEN_DEV_REAL","release_id":"IDENTIDAD_RELEASE_REAL"},
  "target_after": {"environment":"dev","origin":"https://ORIGEN_DEV_REAL","release_id":"IDENTIDAD_RELEASE_REAL"}
}
```

Los booleanos se calculan a partir de observaciones de la prueba, no se escriben
como constantes para aprobar. Los targets se leen del destino real al comienzo
y al final; copiar el target esperado del plan **no prueba el despliegue**.
El check debe fallar cuando no se cumple una aserción. Para errores o acciones
no ejecutadas, omitir el hecho: no inventar un `true` o un `false`.

Ese resultado queda parcial. Sólo se intenta la evaluación semántica cuando
todos los hechos requeridos son verdaderos y los checks están aprobados:

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER --jev evaluate-feedback ID_REQUEST
```

También puede usarse `--jev run ...` para consultar al terminar la ejecución.
`--jev` es optativo y puede generar gasto. Reutiliza la key de Secrets; no pegar
credenciales en comandos. Sin esa opción la CLI no llama al proveedor. El
backend usa `PIPELINE_QUALITY_JEV_ENABLED`, apagado por defecto.
`run` y `evaluate-feedback` retornan código 2 si queda aceptación pendiente.

## Condiciones de cierre y límites de confianza

- El plan debe coincidir con el hash original, proyecto, workspace, ambiente,
  contrato y todos sus criterios asociados. Nuevas versiones del contrato
  requieren revisar el plan.
- Las observaciones llegan exclusivamente del subprocess registrado. La API
  no admite recibos o un `verified=true` enviados por el cliente.
- Huella de fuente, recibos, plan, modelo y rúbrica determinan la caché. Consultar
  estado no produce llamadas a Jev. Cambiar código, contrato, pruebas o plan
  obliga a una nueva comprobación; se revisan también cambios durante la llamada.
- Para feedback de una app DEV/QA se exige `scope=deployed` y coincidencia
  exacta de ambiente, origen e identidad antes/después. Un test local no sirve.
  `scope=local` se reserva para pedidos de alcance local explícito.
- El cierre del paquete, el requisito de merge y las observaciones exportadas
  a Gestión conservan el bloqueo por mejora no verificada. Los pendientes
  activos del workspace también impiden el merge de su etapa: usar worktrees
  separados para trabajos independientes, como prevé el pipeline.
- La evidencia acredita **la ejecución registrada contra ese release**, no una
  vigilancia continua del sitio. No hay consulta automática universal a
  Cloudflare para detectar despliegues posteriores. Un nuevo release exige
  actualizar el target y repetir la comprobación.
- Los tests y el resumen semántico siguen siendo una frontera de confianza.
  Un test trivial o mentiroso puede emitir hechos falsos. El revisor debe comparar
  los originales con el plan y leer el test; Jev no descubre por sí solo una
  omisión escondida en el resumen. No se implementó certificación visual.

## Datos y API

El ledger reutiliza cuatro tipos de registros: `feedback_request`,
`feedback_plan`, `feedback_assessment` y los recibos de ejecución existentes.
Los eventos alimentan la exportación existente; no se añadió otra lista de
incidencias ni un nuevo esquema remoto de Gestión.

En el Bridge quedan los textos originales y los IDs de adjuntos de la cola.
Las imágenes y audios permanecen en su almacenamiento existente. El agente
puede inspeccionarlos mediante el circuito actual. **Jev sólo recibe** el resumen
minimizado, descripciones de comprobaciones, booleanos e IDs de recibos.
No recibe capturas, audio, transcripciones completas, salidas del subprocess,
URLs, cookies ni cuerpos de peticiones por esta evaluación. El operador/agente
debe excluir también datos de negocio al redactar el resumen; la redacción de
patrones conocidos no es un anonimizador universal.

API interna DEV:

- `GET /pipeline-quality/feedback?workspace=...`
- `PUT /pipeline-quality/feedback/{request_id}/plan`
- `GET /pipeline-quality/feedback/{request_id}`
- `POST /pipeline-quality/feedback/{request_id}/evaluate`

El intake automático se conectó al envío por lote usado por Feedback Web.
No se migraron retroactivamente lotes antiguos ni se incorporó el endpoint
legado de envío individual. El estado de trabajos anteriores sigue disponible.

## Qué falta para el primer uso real

Publicar esta versión en Bridge DEV mediante su procedimiento habitual,
verificar el mapeo `sourceApp → workspace` y la SQLite compartida, y seleccionar
el preset con revisor para el piloto. Esto no requiere otro paquete instalado.
Preparar el check concreto de Gestión DEV y un target observable; desplegar una
corrección en la app sólo dentro de su autorización de publicación. Primero
comprobar los hechos; después habilitar Jev para esa entrada minimizada.

El [circuito completo](acceptance-workflow.md) añade registro de repetición manual
y reapertura ante un fallo reportado. No se añadieron botones UAT, un grabador
de consola/red, generación fiable de tests arbitrarios ni publicación automática.
Repetir el caso manualmente con Bruno sigue siendo diferente de ejecutarlo con
un test; la atribución del registro manual la declara el operador.

Medir A/B/C: A = circuito anterior; B = mismos pedidos, planes, evidencia y
revisión sin Jev; C = B más Jev. La comparación B/C necesita adjudicación externa:
el `verified` operativo de C no sirve como árbitro de su propia calidad. Registrar
reproducción/diagnóstico, minutos corrigiendo sugerencias, reprocesos, reaperturas,
cierres falsos y costo. El [evaluador existente](../scripts/jev_lab/evaluate_pipeline.py)
compara tiempo total, minutos humanos, costo y cierres falsos; las métricas más
finas se conservan aparte. No atribuir a Jev los beneficios del registro nuevo.
