# Propuestas del agente: bandeja, decisiones y ejecución

Implementación del 5 de noviembre de 2026. La campana del chat consume propuestas
del Bridge seleccionado. La maqueta local anterior permanece separada y sus datos
no se importan ni se convierten en órdenes reales.

## Flujo

Un productor publica una propuesta con proyecto registrado, identidad estable,
objetivo, motivo, evidencias, encargo y prompts/presupuestos de Generator y Reviewer.
El servicio persiste la propuesta sin iniciar agentes. El cliente consulta mientras
la aplicación está activa, agrupa avisos nuevos y conserva un registro local por
servidor/propuesta/versión para no repetirlos en cada consulta ni al volver a abrir.

Abrir obtiene la versión actual y marca su lectura en servidor. Cada decisión
incluye la versión vista. Una respuesta sobre otra versión devuelve conflicto:
el usuario debe actualizar el detalle antes de decidir.

- **Ejecutar:** registra la aceptación y su contenido antes de crear el chat.
  Configura Generator y Reviewer con topes independientes de 1–25 turnos y envía
  un kickoff. El motor puede terminar antes. Es un ciclo con alternancia acotada;
  no es todavía un coordinador de varios chats o planes de múltiples tandas.
- **Rechazar:** conserva la decisión, suprime la lectura pendiente y evita que
  repetir la misma identidad vuelva a crear el aviso.
- **Observaciones:** registra el texto y pone la propuesta en `needs_revision`.
  No ejecuta agentes ni modifica el alcance automáticamente. El productor debe
  incorporar cambios mediante una revisión; sólo entonces vuelve a estar pendiente.

El detalle permite revisar el encargo, evidencias e instrucciones de cada agente
y abrir el chat reservado/iniciado. El kickoff limita la ejecución al alcance
aceptado; no concede autorización para publicar ni contactar terceros.

## API

Rutas disponibles con y sin prefijo `/api/v1`, bajo el mismo límite de acceso de
red y catálogo de proyectos que el resto del Bridge. No exponer estas rutas como
un servicio público independiente. La creación corresponde al productor/operador
del proyecto; la app no contiene un endpoint público de envío de avisos.

| Método | Ruta | Operación |
| --- | --- | --- |
| POST | `/agent-proposals` | Crear o recuperar por `dedupe_key` y proyecto |
| GET | `/agent-proposals?limit=100&offset=0` | Bandeja, contador de no leídas y paginación |
| GET | `/agent-proposals/{id}` | Detalle y conciliación del arranque |
| POST | `/agent-proposals/{id}/read` | Marcar leída con `{ "revision": 1 }` |
| POST | `/agent-proposals/{id}/decisions` | Responder con versión, acción y observaciones |
| PUT | `/agent-proposals/{id}` | Revisar contenido conservando identidad/proyecto |

El esquema OpenAPI describe `ProposalDraft`, `ProposalRevision` y `ProposalDecision`.
La identidad del productor es `dedupe_key`; repetirla con contenido diferente da
409. La revisión contiene `revision` esperada y `proposal` completo. La revisión
incrementa la versión, conserva las observaciones y vuelve a habilitar un aviso.
No se puede revisar una propuesta ya ejecutada o rechazada. No hay datos sembrados.

## Persistencia y fallos

SQLite `*.proposals.sqlite3` junto al chat store del ambiente, separado entre
backends. Tablas `proposals` y `proposal_events`, con historial de contenido,
revisiones y decisiones. Conservar este registro junto al chat store al migrar.

Bloqueo de archivo entre procesos serializa decisiones de propuestas. Los IDs del
chat derivan de propuesta y versión. Un reintento recupera la misma decisión; no
envía otro kickoff. `starting` se guarda antes del envío. Si se pierde la respuesta,
`uncertain` exige conciliar con los trabajos guardados y nunca reenvía a ciegas.
`started` acredita el envío al motor; el progreso y resultado se consultan en su chat.

Se rechaza un inicio si se observa otro trabajo/ciclo activo del mismo proyecto.
Esta comprobación no instala un bloqueo global nuevo para todos los lanzadores
manuales existentes. El proyecto se vuelve a validar contra el catálogo en cada acceso.
Una caída de red conserva los datos visibles del cliente y muestra un error; el
cliente no afirma que una decisión se haya guardado hasta obtener respuesta.

## Notificación y límites de entrega

El Bridge conserva su transporte local `flutter_local_notifications`, con canal
`agent_proposals`, mensaje genérico y destino ligado a servidor/propuesta/versión.
El toque abre el detalle en el servidor correspondiente, incluso recuperando un
aviso ya existente al arrancar. No cambia automáticamente de backend ni abre un
destino de otro servidor. La lectura de bandeja y la recepción del aviso son distintas.

Mientras está activa, la app consulta cada 30 segundos y al volver a primer plano.
Una tanda de propuestas nuevas produce un único aviso que abre la primera; el resto
queda en la bandeja. No se generan avisos por bandejas vacías ni por cada refresco.
Si falla la notificación nativa, permanece el acceso por bandeja y aviso interno.

**Todavía no hay transporte Firebase para este producto.** No se encontró registro
Firebase de Codex Mobile ni configuración nativa Google Services. Se consultó el
contrato canónico `nienfos-notifications` y su guía de consumidor; no se crearon
recursos remotos ni se copiaron credenciales o módulos de otros productos.
La llegada de propuestas nuevas con la app completamente cerrada requiere esa
adopción/configuración y una prueba física. Recuperar el toque de un aviso existente
al arrancar no demuestra entrega push con la aplicación cerrada.

## Estado de entrega

Implementados servicio, rutas, cliente, bandeja, decisiones, arranque y enlace de
notificación. El supervisor periódico que investiga proyectos y produce propuestas
es un componente posterior: la API ya define dónde entregar sus resultados.

La validación usa bases temporales, proveedor controlado y respuestas HTTP de prueba.
No certifica recepción en Android, ejecución con un modelo remoto ni despliegue.
No se reiniciaron backends ni se publicó un APK durante esta implementación.
Ver [informe y capturas](../reports/agent-proposals-implementation/README.md).
