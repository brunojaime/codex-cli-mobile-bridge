---
name: generator-reviewer
description: Preparar prompts libres de Generator y Reviewer y un kickoff, y arrancarlos en un chat nuevo del mismo proyecto mediante la herramienta generator-reviewer. Usar cuando el usuario pida delegar una tarea a ese ciclo o use /ejecutar; también para preparar sus prompts sin arrancar si sólo pide un borrador. No usar para revisiones simples en el chat actual.
---

# Generator + Reviewer

El usuario define el trabajo y el enfoque en lenguaje natural. No hay un catálogo
ni prompts fijos: redactá ambos prompts a partir del contexto. Un generador puede
centrarse en implementar, investigar o corregir; el revisor puede priorizar
seguridad, funcionamiento, pruebas o los aspectos pedidos. No reduzcas el alcance
ni inventes autorizaciones para publicar, gastar, enviar mensajes o usar datos.

## Preparar y lanzar

1. Leé las instrucciones y el estado del proyecto. Conservá decisiones, límites,
   criterios de aceptación y referencias a archivos o adjuntos necesarios. Sólo
   preguntá si falta una decisión material que no se puede recuperar del contexto.
2. Escribí un prompt específico para Generator, otro para Reviewer y un kickoff
   autosuficiente con el objetivo concreto, contexto, pruebas y entregables. No
   copies historiales completos, secretos ni pendientes de otros proyectos. Los
   prompts se guardan en la configuración del chat y el motor existente los aplica
   a cada agente. No modifican los perfiles globales.
3. Cada agente dispone de **25 turnos máximos** si el usuario no indica otro valor.
   Los límites son independientes: «4 para Generator y 3 para Reviewer» significa
   4/3; «4 para Generator» significa 4/25. Usá enteros positivos. No son 25 rondas
   compartidas ni una obligación de consumirlos. El motor puede terminar antes y
   no se agregan turnos automáticamente al agotarlos. Si un límite no permite más
   alternancia, los turnos sobrantes del otro agente no se fuerzan.
4. Si sólo pidió ejemplos o prompts, entregalos sin llamar la herramienta. Si
   autorizó arrancar, usá `start_generator_reviewer` del MCP generator-reviewer.
   Tomá `bridge_url`, `source_session_id` y `source_message_id` del **Bridge handoff
   context del turno humano actual**. No deduzcas IDs por el chat más reciente ni
   pruebes otro backend. Si faltan la herramienta, los metadatos o la ruta, explicá
   que falta instalar/activar la integración; no simules un arranque con terminal.
5. Pasá título, prompts, kickoff y límites. El backend usa el mismo workspace,
   configura ambos agentes antes del kickoff y conserva los IDs de origen. El
   kickoff indica ejecutar el trabajo directamente en el nuevo chat: no debe
   pedir que ese chat vuelva a delegarlo a otro Generator/Reviewer.
6. Respondé con estado real, título, límites efectivos y `[Abrir conversación](chat_link)`.
   No cambies la conversación seleccionada ni navegues automáticamente. `started`
   acredita que se envió el kickoff; no que la tarea ya terminó. Si el cliente aún
   no admite enlaces internos, el chat se puede seleccionar desde su lista.

## Repetición y fallos

Cada mensaje humano admite un lanzamiento. Conservar los mismos IDs y todos los
parámetros hace idempotente un reintento. No cambies el contenido al reintentar:
produciría conflicto. Una tarea distinta requiere un nuevo pedido humano.

Ante timeout, consultá `get_launch` si recibiste el ID o repetí exactamente la
misma llamada. `uncertain` significa que no se confirmó el arranque: inspeccioná
el chat y los trabajos antes de proponer recuperación. `failed` significa que
falló la preparación. No mandes un kickoff alternativo ni inventes que no hubo
actividad. La consulta nunca inicia otro trabajo.

## Ejemplos de pedidos

- «Arrancá en otro chat la implementación acordada; que el revisor compruebe
  seguridad y persistencia». Redactá los tres textos; límites 25/25.
- «/ejecutar Corregí el formulario, 4 turnos de Generator y 3 de Reviewer».
  Redactá prompts adaptados al defecto; límites 4/3.
- «Mostrame los prompts antes de ejecutarlos». Sólo entregá los textos.

El selector `/ejecutar` inserta un pedido editable. Seleccionarlo no inicia nada;
la persona debe completar y enviar el mensaje. La instalación de esta skill y el
MCP no sustituye la activación del backend ni la actualización de la app móvil.
