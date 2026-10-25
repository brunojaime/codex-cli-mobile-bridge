# Evidencia, diagnóstico y reparación del pipeline

Implementación local: 27/09/2026. El Bridge coordina la ejecución; Gestión recibe
observaciones técnicas. Jev sólo emite sugerencias. No cambia aceptaciones
comerciales ni permisos de publicación.

Ampliación local del 28/09: [validación de las mejoras pedidas por feedback](feedback-validation.md).
Incluye pedido original, plan de comprobación, hechos emitidos por los checks y
evaluación semántica optativa de cobertura. En ese circuito Jev puede mantener
un cierre pendiente; nunca reemplaza evidencia ejecutada. No está activado por
el mero hecho de que los archivos existan en este checkout.

## Operación

`PIPELINE_QUALITY_ENABLED=true` activa el registro y el requisito adicional de
evidencia en el merge DEV. `PIPELINE_QUALITY_DATABASE` identifica la SQLite
compartida por el Bridge y los operadores. Respaldar esa base con el procedimiento
de datos del host; no publicarla ni copiarla a reportes. Para retirar el requisito
durante un rollback explícito existe `PIPELINE_QUALITY_ENABLED=false`; no es un
fallback automático ante fallos.

El cliente Jev se activa con `PIPELINE_QUALITY_JEV_ENABLED=true` en el proceso del
backend, o con `--jev` en la CLI. Usa `OPEN_ROUTER_API_KEY` de Secrets. Por defecto
permanece apagado para que instalar la actualización no envíe logs de otras apps
sin seleccionar primero el piloto. El diagnóstico general recibe extractos redactados
de fallos y condiciones de hasta cinco lecciones, nunca archivos `.env`. Para los
nuevos pedidos de feedback se omite ese envío de logs y se usa la evaluación de
cobertura con el resumen minimizado y hechos estructurados de sus pruebas.
La redacción elimina patrones conocidos; no garantiza detectar todos los datos
personales que una aplicación escriba indebidamente en sus logs.

En cada proyecto crear `.codex/quality.json`:

```json
{
  "version": 1,
  "project_id": "identidad-estable-de-la-app",
  "environment": "dev",
  "component_ids": ["componente-compartido"],
  "max_attempts": 6,
  "criteria": [{
    "id": "persistencia",
    "description": "El dato guardado sigue disponible al volver a consultar",
    "check_ids": ["persistencia"]
  }],
  "checks": [{
    "id": "persistencia",
    "argv": ["npm", "run", "test:persistencia"],
    "timeout_seconds": 120,
    "required": true
  }]
}
```

El comando debe existir en ese proyecto: el ejemplo no crea ni sustituye tests.
Cubrir los criterios reales del spec y conservar los controles obligatorios. Un
criterio sin checks queda pendiente. `decision_pending` registra una decisión de
producto que impide ejecutar. `dependencies` contiene IDs de paquetes que deben
estar verificados; `feedback_item_id` vincula un criterio con un comentario.
Ambientes admitidos: local, dev y qa. No crea nuevos entornos publicados.

Desde la raíz del Bridge, usando su Python:

```sh
.venv/bin/python scripts/pipeline_quality.py register --workspace RUTA_APP --work-item ID_TAREA --stage-id ID_STAGE
.venv/bin/python scripts/pipeline_quality.py --jev run ID_PAQUETE --attempt intento-1
.venv/bin/python scripts/pipeline_quality.py status ID_PAQUETE
.venv/bin/python scripts/pipeline_quality.py diagnose ID_PAQUETE
.venv/bin/python scripts/pipeline_quality.py learn ID_PAQUETE --file LECCION.json
.venv/bin/python scripts/pipeline_quality.py close ID_PAQUETE
```

Usar `--database RUTA_SQLITE` antes del subcomando si la CLI se ejecuta desde otro
directorio. Debe ser la misma base configurada en el backend. La CLI es una
herramienta local del operador; no constituye una frontera contra alguien que ya
puede editar la SQLite o el código del Bridge.

Una lección requiere IDs de una ejecución fallida y otra aprobada del mismo check,
con cambio de fuente y paquete actualmente verificado; más `symptom`,
`cause_hypothesis`, `resolution` y `conditions`. La reparación está observada; la
explicación causal sigue siendo una hipótesis. La lección es inmutable y se
recupera sólo para el mismo proyecto o componentes compartidos declarados.

`close` saca un paquete verificado de la cola de reparación activa. No aprueba un
merge ni confirma una entrega. Los paquetes viejos deben cerrarse al concluir su
revisión para que no se traten como trabajo activo en futuras conversaciones.

## Integraciones incluidas

- API interna `/pipeline-quality`: registrar, ejecutar, consultar, diagnosticar,
  guardar lecciones, cerrar y exportar. DEV únicamente. No admite resultados de
  tests declarados por el cliente. El registro de comandos tiene el mismo nivel
  de confianza que las operaciones de desarrollo existentes; no es un sandbox.
- Merge: exige paquetes vinculados al stage, checks aprobados y huella de fuente
  vigente. Sigue exigiendo aprobación, árbol limpio, rama correcta y SDD doctor.
- Revisor: para trabajo registrado, recibe criterios y evidencia; se omite la
  última narrativa del generador y se inicia otra sesión del proveedor. No se
  modifica la memoria global de herramientas externas. La cadena no acepta un
  `complete` mientras el registro mantiene bloqueos.
- Project Factory: vuelve a validar la candidata después de `publish-finalize`
  y del commit, antes de publicar. Un contrato del proyecto amplía los controles;
  el fallback registra sólo la validación técnica generada y lo declara así.
- Feedback: conserva `status/workflowStatus` por compatibilidad y agrega
  `resolution` por ítem. Varios criterios asociados deben estar comprobados.
  Una dependencia requerida sin evidencia vigente bloquea los ítems vinculados,
  incluso cuando sus checks propios aprobaron; `blockers` identifica la causa.
- Gestión: migración local preparada `0065_pipeline_evidence.sql`, importación y
  consulta con RBAC y alcance de cliente, eventos inmutables, secuencia por
  productor/paquete, pantalla por proyecto accesible en development. No modifica
  hitos, dinero, entrega aceptada ni configuración productiva del MCP.

## Exportar y sincronizar Gestión

```sh
.venv/bin/python scripts/pipeline_quality.py gestion-pack ID_PAQUETE --project-id ID_CANONICO_GESTION > observacion.json
.venv/bin/python scripts/sync_pipeline_gestion.py observacion.json
```

El segundo comando prepara el plan. La pantalla de Gestión permite importar el
archivo autenticado con sesión propia. Para sincronización directa, instalar
primero el receptor y migración en DEV, configurar `GESTION_PIPELINE_TOKEN` en
Secrets con capacidades dev `operations:read/write`, y ejecutar el sincronizador
con `--send`. Consulta estado canónico antes y después; confirma el ID importado.
Sólo admite el origen exacto de Gestión DEV o una instancia local aislada; usa el
guard de ambientes y no sigue redirecciones. La importación se puede reintentar
con el mismo archivo. No hay daemon periódico instalado en esta entrega.
La API de agentes existente limita cada petición a 16 KiB; para observaciones
mayores usar la pantalla del proyecto (archivo de hasta 200 KB).

El export identifica productor, secuencia, revisión, ambiente, contrato, criterios
y recibos. Gestión lo presenta como observación histórica reportada por Bridge,
no como demostración de qué versión sigue desplegada. El mapeo al ID canónico de
Gestión debe ser explícito; no se adivina por nombres similares.

## Límites y recuperación

Intentos idempotentes y lock de workspace evitan ejecuciones duplicadas. Después
de una interrupción no se inventa éxito: el intento queda interrumpido; revisar
antes de usar una clave nueva. Timeouts matan el grupo de procesos. Salida limitada
a un extracto de 12 KB; el proceso se detiene al superar 10 MB. Sólo se hereda un
grupo pequeño de variables del sistema, no secretos del Bridge.

La huella cubre archivos de Git y archivos no ignorados, omitiendo secretos y
directorios de dependencias. No prueba identidad de un despliegue ni cambios en
servicios externos. Para eso el contrato debe incluir tests contra el ambiente
seleccionado y comprobación de versión. Tests que alteran la fuente invalidan su
propio resultado. Guards y comandos dependen de un contrato de aceptación honesto;
un comando trivial no prueba un requisito sólo por estar registrado.

Ante error o timeout de Jev se conserva diagnóstico existente y se abre un cooldown
de 30 s. No puede aprobar checks, omitir controles, cerrar ítems ni publicar.
La detección automática de estancamiento usa repetición de firma observada;
la equivalencia semántica sugerida por Jev se guarda como consejo sin umbrales
copiados de benchmarks ajenos.

## Verificación y medición

```sh
.venv/bin/python -m pytest tests/test_pipeline_quality.py tests/test_dev_pipeline.py tests/test_project_factory_job_runner.py tests/test_developer_feedback_integration.py
.venv/bin/python scripts/jev_lab/pipeline_smoke.py --live-jev --output reports/pipeline-smoke.json
```

El smoke usa un defecto sintético y una reparación predeterminada. Ejecuta procesos
reales y hasta dos consultas Jev; no mide velocidad de programación autónoma.
El protocolo A/B/C de investigación sigue siendo la referencia para comparar
productividad sobre trabajos reales. Esta entrega no presenta un porcentaje
inventado de ahorro humano.

Para analizar el piloto, registrar una línea JSON por ejecución en un archivo
JSONL con `case_id`, `repeat`, `arm` (A/B/C), `accepted`, `elapsed_ms`,
`human_minutes`, `cost_usd` y `false_closure`. A es el flujo anterior, B agrega
criterios/evidencia/revisión independiente y C agrega Jev al mismo flujo B.
`accepted` y `false_closure` deben provenir de una evaluación independiente,
incluyendo ejecuciones fallidas. Ejecutar:

```sh
.venv/bin/python scripts/jev_lab/evaluate_pipeline.py mediciones.jsonl --output comparacion.json
```

El analizador exige pares completos A/B/C y agrupa repeticiones por caso; menos
de 12 casos con 3 repeticiones devuelve resultado inconcluso. Un cierre falso
en C detiene su recomendación. Es una regla de selección del piloto, no una
prueba de significación estadística. El archivo de mediciones no se rellena
con resultados simulados para aparentar mejoras.

La [demostración de feedback y dependencias](../reports/jev-demostracion-feedback-20260927/informe.md)
documenta un defecto observado en este código, su reproducción con la versión
anterior, la corrección y una consulta real a Jev. No mide productividad.
