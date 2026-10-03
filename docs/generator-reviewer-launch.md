# Lanzar Generator + Reviewer desde un chat

La skill compartida `generator-reviewer` redacta dos prompts libres y un kickoff
según el trabajo pedido. La herramienta MCP crea una conversación en el mismo
workspace y backend del origen, guarda los prompts y envía un único kickoff.
No modifica perfiles globales ni cambia la conversación seleccionada.

Ejemplo para un nuevo chat del proyecto:

> Usá generator-reviewer para implementar el filtro que acordamos. Que el
> generador implemente y que el revisor compruebe permisos y persistencia.
> Arrancalo en otro chat y dejame el enlace.

Los dos límites por defecto son **25 turnos por agente**. Se pueden cambiar por
separado: «4 para Generator y 3 para Reviewer», o «4 para Generator», que conserva
25 como límite de Reviewer. Son topes, no una obligación de agotar el presupuesto:
se puede terminar antes; cuando no hay posibilidad de continuar la alternancia,
no se gastan turnos sobrantes ni se amplían límites automáticamente.

`/ejecutar` inserta un pedido editable en el compositor. Elegirlo no envía nada;
completá la tarea y enviá el mensaje. El enlace `Abrir conversación` sólo navega al
tocarlo y se resuelve en el servidor actual. Un destino inexistente conserva el
chat origen. El menú y esta navegación requieren la versión móvil que los incluya.

## Componentes y activación

- Skill fuente: `codex-skills/generator-reviewer/SKILL.md`; instalación compartida
  bajo `~/.codex/skills/generator-reviewer`, mediante sincronización habitual.
- MCP: `mcp_apps/generator_reviewer/app.json` y `server.py`. Es descubrible por
  Apps; `get_app_manifest` no crea chats ni trabajos. `start_generator_reviewer`
  escribe; `get_launch` consulta y puede recuperar un recibo de envío persistido.
- Backend: `POST /agent-launches/generator-reviewer` y
  `GET /agent-launches/{launch_id}`, también bajo `/api/v1`.
- El contexto del turno humano entrega la URL loopback exacta, ID del chat e ID
  del mensaje origen. No se adivinan por fecha ni se cambia automáticamente entre
  DEV y PROD. La herramienta no acepta hosts externos o redirecciones.
- Registro durable: archivo `*.launches.sqlite3` junto al chat store de cada
  backend. No se comparten los registros entre ambientes. Conservarlo al mover
  o respaldar una instalación junto con su chat store.

Cada mensaje humano tiene un lanzamiento. Repetir los mismos parámetros recupera
el resultado; cambiar el contenido con la misma fuente devuelve conflicto. Se
reserva el ID de conversación antes de crearla y se serializan llamadas
concurrentes. Un arranque incierto nunca reenvía el kickoff automáticamente.

Estados: `started` confirma que se envió el primer trabajo, no su terminación;
`failed` informa fallo de preparación; `uncertain` exige inspeccionar la actividad
existente. Ante timeout, repetir exactamente la llamada o consultar el ID recibido.
Los trabajos siguen usando la configuración y las restricciones del motor actual,
incluida la protección del repositorio de Bridge desde PROD.

## Validación reproducible

Desde la raíz:

```sh
.venv/bin/python scripts/check_generator_reviewer_launch.py
```

Usa SQLite temporal, proveedor de ejecución controlado, protocolo MCP real por
stdio y pruebas Flutter. No llama a modelos ni crea trabajos en el Bridge activo.
Incluye topes 25/25, 4/3 y límites omitidos, cierre anticipado, concurrencia,
conflictos, fallos de preparación, pérdidas de confirmación y recuperación tras
interrupción; también comprueba selección del menú y navegación al tocar el enlace.

Resultados y límites de la comprobación están en
`reports/generator-reviewer-launch/report.html`. Las pruebas locales no equivalen
a una publicación de APK ni a un ciclo con modelos contra un despliegue.
