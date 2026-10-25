# Comprobación de requerimientos nuevos

Primera extensión local: 28/09/2026. Reutiliza el registro y la evaluación de
[mejoras por feedback](feedback-validation.md). No necesita capturas, no crea
otro backlog y no introduce un chat de IA para el usuario final de la app.

## Flujo de trabajo propuesto

1. Bruno plantea un requerimiento en el chat o en el documento del proyecto.
2. El agente conserva el texto y una referencia a su origen, y lo divide en
   condiciones comprobables. Antes de programar presenta una interpretación
   breve: qué debe ocurrir, casos alternativos, permisos y límites relevantes.
   Pregunta sólo por ambigüedades que cambian el comportamiento del producto.
3. Registra el requerimiento y sus criterios. Prepara el contrato de pruebas,
   incluyendo regresiones relacionadas. El revisor contrasta los criterios con
   el original: una omisión en esta traducción puede engañar al evaluador final.
4. Implementa y ejecuta las comprobaciones. Se conservan pruebas fallidas y
   posteriores resultados; no basta la narrativa de que el agente terminó.
5. Para un requerimiento de una app publicada, después de publicar la corrección
   autorizada en DEV se comprueba el comportamiento allí, en un release identificado.
6. Jev compara la intención resumida con los hechos emitidos por las pruebas.
   Si no alcanzan o cubren sólo una parte, el trabajo sigue pendiente. Los fallos
   objetivos se detectan antes de llamar al modelo.
7. Se devuelve un resultado por requerimiento: cumplido, parcial, no cumplido o
   evidencia insuficiente. Una confirmación de Bruno sobre comodidad o intención
   de negocio sigue siendo distinta de la comprobación técnica.

**Roles:** las reglas verifican vínculos, vigencia, ambiente y resultados; el
agente traduce el pedido y escribe código/tests; el revisor contrasta original,
plan e implementación; Jev evalúa cobertura semántica de la evidencia; Bruno
resuelve decisiones de producto y confirma lo subjetivo. No se delega toda la
UAT a Jev ni se le atribuye navegación o comprensión de audio/capturas en esta
integración.

## Ejemplo de requisito, sin encargar esa funcionalidad

«Quiero filtrar la cartera por estado y conservar el filtro al recargar».

Condiciones candidatas: sólo aparecen elementos del estado seleccionado;
el filtro se conserva al recargar; si no hay coincidencias aparece el estado
vacío; quitar el filtro restaura la lista dentro de los permisos del usuario.
El significado de los estados o el alcance entre dispositivos, si no están
definidos, son decisiones por aclarar. Una captura del selector o un test que
sólo compruebe que la página abre no satisface ese requerimiento.

La prueba ejecutada en esta entrega fue más acotada: una función local de filtro
debía excluir estados distintos y devolver vacío si no había coincidencias.
No probó navegador, persistencia de filtros ni Gestión publicada.

## Entrada disponible para el agente

Desde el checkout del Bridge:

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER register-requirement --workspace RUTA_APP --file REQUERIMIENTO.json
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER requirements --workspace RUTA_APP
```

Ejemplo de archivo (es una definición ilustrativa, no un pedido aprobado):

```json
{
  "requirement_id": "REQ-FILTRO-001",
  "project_id": "nienfos-gestion",
  "source_ref": "spec:ID_REAL_DEL_REQUERIMIENTO",
  "text": "Quiero filtrar la cartera por estado y conservar el filtro al recargar",
  "environment": "dev",
  "criteria": [
    {"id": "filtro-coincide", "description": "Sólo aparecen elementos del estado seleccionado dentro del alcance del usuario"},
    {"id": "filtro-recarga", "description": "Al recargar se conserva el filtro y su resultado"},
    {"id": "filtro-vacio", "description": "Si no hay coincidencias se muestra el estado vacío"},
    {"id": "filtro-quitar", "description": "Quitar el filtro restaura la lista dentro del alcance del usuario"}
  ]
}
```

Después se registra un paquete de calidad normal. Cada criterio de su contrato
debe mantener exactamente el ID y la descripción originales, declarar los
`check_ids` ejecutables y vincular el `feedback_item_id` devuelto por el registro.
Para requerimientos, este campo legado funciona como referencia compartida
(`requirement:REQ-FILTRO-001`); no implica inventar una captura ni un comentario
de feedback. El registro indica explícitamente `origin=requirement`.

Los comandos genéricos nuevos son alias del mismo mecanismo de validación:

```sh
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER request-plan ID_REQUEST --file PLAN.json
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER run ID_PACKET --attempt intento-1
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER request-status ID_REQUEST
.venv/bin/python scripts/pipeline_quality.py --database RUTA_LEDGER --jev evaluate-request ID_REQUEST
```

El plan y el formato de hechos son los mismos de la [guía de feedback](feedback-validation.md).
Cada criterio exige al menos una observación del check registrado. En DEV/QA el
plan exige origen y release observado antes y después; un test local no los
sustituye. `--jev` habilita una consulta potencialmente facturable con Secrets;
registrar, listar y consultar estado no llaman a un modelo.

API interna DEV:

- `POST /pipeline-quality/requirements`: definición anterior más `workspace`.
- `GET /pipeline-quality/requirements?workspace=...`: requerimientos registrados.
- `PUT /pipeline-quality/requests/{id}/plan`: vincular el plan.
- `GET /pipeline-quality/requests/{id}`: leer el resultado.
- `POST /pipeline-quality/requests/{id}/evaluate`: evaluar evidencia disponible.

Las rutas antiguas de feedback siguen siendo compatibles. Todos los tipos de
pedido usan el mismo runner, revisor, caché, límites y controles de cierre.
La exportación sigue proyectando los paquetes existentes y no crea trabajos
fantasma por registrar un requisito antes de tener un paquete.

## Alcance y límites de esta primera versión

El original es inmutable e idempotente por proyecto, workspace y requirement_id.
El plan rechaza criterios omitidos o descripciones debilitadas respecto del
registro. Esto protege frente a reescrituras posteriores; no demuestra que la
primera traducción de las palabras de Bruno haya sido completa. Tampoco certifica
por sí solo que el registro haya precedido a todo cambio de código.

Cambios legítimos de alcance necesitan revisión explícita. No se añadió todavía
una aprobación comercial automática. El [circuito completo](acceptance-workflow.md)
incluye ahora revisión explícita con motivo y referencia de decisión, conservando
el original y exigiendo evidencia nueva. Registrar otro ID por sí solo no cancela
el anterior. No editar el ledger a mano para forzar una aceptación.

El chat DEV ya conserva la fuente textual y entrega al agente las instrucciones
de registro. El agente identifica los pedidos de implementación y define sus
criterios: no existe una detección infalible de cualquier requerimiento dictado.
No se añadió una nueva pantalla de Gestión. La activación publicada sigue
pendiente; registrar un requisito no autoriza por sí solo un despliegue.

Jev recibe únicamente el resumen minimizado y hechos estructurados; no el texto
original completo, adjuntos o logs. Su utilidad incremental debe compararse
con el mismo flujo sin Jev mediante A/B/C y evaluación independiente: omisiones
encontradas, cierres falsos, reaperturas, tiempo humano, reprocesos y costo.
