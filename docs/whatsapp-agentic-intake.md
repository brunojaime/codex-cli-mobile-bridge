# WhatsApp Agentic Intake

## Objetivo

Convertir los textos, audios e imágenes recibidos por WhatsApp en un historial
auditable por proyecto, detectar trabajo accionable y, según la política del
proyecto, proponerlo o ejecutarlo con Codex. El sistema nunca responde al grupo
de WhatsApp.

## Flujo general

```text
WhatsApp
  -> captura y normalización
  -> historial textual por proyecto
  -> ventana de agrupación
  -> triage con LLM en modo lectura
  -> tarea pendiente o archivo
  -> aprobación/política del proyecto
  -> Codex ejecutor del proyecto
```

Los mensajes privados de Bruno también admiten el control exacto `CLI`. Ese
modo omite el triage y abre una conversación estándar en
`codex-cli-mobile-bridge`; el texto y las transcripciones se envían sin un
prompt envolvente y las imágenes se adjuntan como en la aplicación.

## 1. Captura e historial determinístico

Cada mensaje se conserva con:

- identificador único;
- grupo y proyecto asociado;
- identificador y nombre visible del remitente;
- fecha y hora;
- tipo de mensaje;
- texto original;
- archivo de audio original, cuando corresponda;
- transcripción del audio;
- archivo de imagen original y su caption, cuando corresponda;
- estado de procesamiento.

El remitente de una nota de voz proviene de los metadatos de WhatsApp. Whisper
solamente transcribe el contenido y no decide quién habló. La diarización de
varias voces dentro de un mismo audio queda fuera de la primera versión.

Ejemplo de historial normalizado:

```text
[10:31] Bruno: El cliente quiere cambiar el botón.
[10:32] Cliente — audio transcripto: Preferiría que fuera azul.
[10:33] Socio: Dale, lo revisamos.
```

## 2. Agrupación

Los mensajes se acumulan por grupo/proyecto durante una ventana corta, por
ejemplo 45 segundos desde el último ingreso. Una explicación enviada en varios
mensajes produce así un único análisis y una única unidad de trabajo.

No se invoca un LLM por cada mensaje individual. El historial completo queda
guardado aunque un bloque no requiera análisis o acción.

## 3. Triage

Un worker invoca un LLM efímero con un skill específico de ingreso de WhatsApp.
El triage recibe:

- el bloque de mensajes nuevos;
- una ventana compacta del historial anterior;
- las tareas, preguntas y propuestas todavía pendientes;
- la política operativa del proyecto.

Su salida debe ser JSON validable, por ejemplo:

```json
{
  "actionable": true,
  "type": "change_request",
  "summary": "Cambiar el botón principal a azul",
  "risk": "low",
  "approval_detected": false,
  "requires_approval": true
}
```

El contexto es imprescindible: “dale, buenísimo” puede ser conversación social
o la aprobación de una propuesta pendiente. El triage clasifica y propone, pero
no modifica archivos.

## 4. Tareas y modos por proyecto

Cuando existe trabajo accionable se crea una tarea pendiente con trazabilidad a
los mensajes originales. Cada proyecto puede operar en uno de estos modos:

- `observar`: guardar historial sin generar acciones;
- `consultar`: analizar, notificar y esperar aprobación;
- `automatico-seguro`: ejecutar solamente categorías previamente permitidas;
- `automatico-completo`: ejecutar sin aprobación manual, con auditoría.

La primera versión debe usar `consultar`. La interfaz ofrece al menos
`Descartar`, `Editar instrucción` y `Ejecutar`.

## 5. Ejecución y concurrencia

Al aprobar una tarea se inicia un Codex efímero con el workspace del proyecto,
el resumen del triage y referencias al historial relevante.

- Proyectos distintos pueden ejecutar en paralelo.
- Dentro de un mismo proyecto se permite un solo ejecutor con escritura.
- Una segunda tarea del mismo proyecto espera o se combina con la activa.
- Un límite global configurable protege los recursos de Batata, sin cambiar el
  modelo de concurrencia por proyecto.

Por ejemplo, diez proyectos independientes pueden tener diez ejecuciones en
paralelo; dos escrituras simultáneas sobre el mismo proyecto no están permitidas
en la primera versión. En el futuro podrían aislarse mediante worktrees.

## 6. Responsabilidades

- **Capturador:** recibe WhatsApp y persiste evidencia inmutable.
- **Transcriptor:** convierte localmente los audios a texto.
- **Agrupador:** cierra bloques después de la ventana de espera.
- **Skill de triage:** define taxonomía, criterio y contrato de salida.
- **Coordinador:** mantiene estado, idempotencia, colas y bloqueos.
- **Ejecutor:** inicia Codex dentro del proyecto autorizado.
- **Frontend:** muestra tareas, decisiones, progreso y resultados.

El estado y las garantías operativas pertenecen al coordinador; el criterio
semántico pertenece al skill; la modificación del proyecto pertenece al
ejecutor.

## Primera implementación

1. Historial normalizado con remitente, texto y transcripción.
2. Ventana de agrupación configurable, inicialmente 45 segundos.
3. Skill de triage con respuesta JSON validada.
4. Para cada decisión accionable, un chat nuevo con el perfil verde
   `WhatsApp Intake` y el workspace del proyecto.
5. El primer turno comprende el pedido, presenta el plan y espera aprobación.
6. Sólo una aprobación posterior de Bruno Jaime dentro de ese chat permite
   implementar; una aprobación escrita en WhatsApp nunca autoriza cambios.
7. Paralelismo configurable entre proyectos independientes.

La primera versión usa el propio chat como superficie de aprobación, sin una
cola o botón de aprobación separado. Un bloqueo de escritura por proyecto puede
agregarse después si aparecen ejecuciones aprobadas simultáneas sobre el mismo
workspace.
