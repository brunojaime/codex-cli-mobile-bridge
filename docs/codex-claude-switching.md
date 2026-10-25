# Proveedor de IA del Bridge

## Configuración vigente en DEV

El backend decide el proveedor, modelo y esfuerzo de todos los trabajos generales
de IA. El frontend conserva sus contratos HTTP, chats, agentes, archivos y URLs.
No hace falta publicar un APK para activar esta configuración:

```dotenv
AI_PROVIDER=codex
AI_MODEL=gpt-6.1-sol
AI_EFFORT=medium
AGENT_DEFAULT_MODEL=gpt-6.1-sol
```

Estos valores están activos en `.run/dev-backend-8118/dev.env` y en los valores
predeterminados del lanzador DEV. `CLAUDE_COMMAND` permite indicar una ruta
absoluta. Claude debe estar autenticado como el usuario del servicio:

```sh
claude auth status
```

DEV: `http://batata-default-string.tail0302c4.ts.net:8118`.
`GET /ai/runtime` muestra la configuración efectiva y las limitaciones.
`GET /codex/tooling` conserva el formato que entiende la app, pero informa el
estado de Claude cuando ése es el proveedor activo. No expone credenciales.
Producción en 8000 no fue reiniciada ni migrada.

Con `AI_PROVIDER=claude`, incluso un frontend antiguo que envíe `model=gpt-5.4`
recibe la configuración efectiva de Claude. Los títulos y trabajos sin modelo
explícito también pasan por la política central. Los perfiles guardados no pueden
cambiar de proveedor por encima de esa política.

Para seleccionar Codex desde el backend, configurar `AI_PROVIDER=codex`,
`AI_MODEL` con un identificador Codex válido y `AI_EFFORT`. Reiniciar sólo el
ambiente elegido después de drenar sus trabajos. `AI_PROVIDER=auto` conserva el
modo anterior: selección por modelo de cada agente y fallback a
`AI_MODEL`/`AGENT_DEFAULT_MODEL`. El selector Engine del frontend sólo decide el
motor en ese modo; en modo fijo prevalece el backend.

Cambio solicitado el 23/10/2026 tras alcanzar el límite de Claude: DEV usa
Codex con GPT-6.1 Sol y esfuerzo medium. Verificado con respuesta real
`SOL61_MEDIUM_OK` y contexto nativo `model=gpt-6.1-sol`, `effort=medium`;
12 pruebas de esfuerzo pasaron. Evidencia en `.run/sol61-medium-20261023/`.
La política fija prevalece sobre
los modelos guardados en los chats. La integración Claude descrita abajo
se conserva como referencia del proveedor anterior.

## Capas y cobertura

`AiRuntimePolicy` resuelve el destino antes de entregar una tarea al proveedor.
`LocalExecutionProvider` conserva colas, observadores, cancelación, imágenes e IDs.
`AgentCli` aplica la misma política a los procesos separados de SDD y Factory.
No se reintenta una tarea de Claude usando Codex como fallback silencioso.

| Superficie | Implementación / verificación |
| --- | --- |
| Chat y mensajes nuevos | Política central; prueba HTTP real con modelo GPT obsoleto enviado por el cliente |
| Generator / Reviewer y lanzador de ciclos | Política común por agente; tests de presupuestos, idempotencia, recuperación y protocolo MCP del lanzador; prueba HTTP real |
| Supervisor, especialistas y Summary | Mismo proveedor de ejecución; tests de enrutamiento, resúmenes y cierre del ciclo; Supervisor real devolvió JSON válido y cerró la ejecución |
| Títulos y resúmenes de turnos | Las llamadas internas, incluso sin modelo explícito, reciben el proveedor configurado |
| Handoff del pipeline DEV | Proveedor compartido y traducción de opciones de sólo lectura |
| SDD | CLI común, resultado JSON normalizado; tests del servicio y prueba real de lectura del archivo de tarea |
| Project Factory: generación, revisión y UX | CLI común; pruebas del runner. No se publicó una aplicación para validar esta integración |
| Relevamientos | Su proveedor local usa la política central; modo sin herramientas conservado. El proceso independiente debe cargar las mismas variables de ambiente |
| WhatsApp intake | Sigue usando la API del Bridge; traducción del modo de sólo lectura. No se enviaron mensajes a terceros |
| Imágenes, continuidad y cancelación | Tests del adaptador: imágenes, resume, cambio de motor, observación, timeout, cancelación, errores y permisos denegados |
| Skills locales seleccionadas | Se adjunta SKILL.md al contexto y se habilita su directorio; una skill ausente o incompatible falla explícitamente |
| Estado de herramientas | Estado/autenticación de Claude en el contrato existente; inventario MCP marcado como no completo |

Los nombres persistidos como `codex.*`, `reviewer_codex`, `.codex/` y los enlaces
`codex-bridge://` son contratos de compatibilidad; no seleccionan el ejecutable.
Los chequeos deterministas, Git, compilaciones, despliegues, transcripción de audio,
TTS y el asesor semántico especializado Jev mantienen sus propias herramientas.
El diagnóstico independiente `control_agent` todavía incluye chequeos específicos
de instalación/login de Codex; no es un ejecutor de tareas conversacionales.

## Permisos y diferencias que impiden afirmar “100%”

- Los perfiles de configuración, plugins y selecciones MCP de Codex no se copian
  automáticamente a Claude. Las selecciones incompatibles se rechazan. El
  instalador antiguo de apps MCP devuelve 422 bajo Claude para evitar configurar
  por error el proveedor inactivo. La migración completa de ese catálogo queda
  pendiente, incluyendo autenticación y herramientas de cada integración.
- `read-only` se traduce a herramientas `Read,Glob,Grep`, modo restringido, sin
  hooks/plugins ni MCP externos. Las tareas de análisis pueden desactivar todas
  las herramientas. Es una restricción de herramientas de Claude, **no** una
  implementación del sandbox de sistema operativo de Codex.
- DEV usa `auto`: Claude evalúa las acciones con su clasificador de permisos sin pedir aprobaciones rutinarias. Las acciones denegadas siguen haciendo fallar el trabajo; no se activa bypass. Las tareas de sólo lectura/sin herramientas conservan sus restricciones y `dontAsk`.
- `acceptEdits` permite ediciones de archivos. No habilita bypass general de
  permisos: otros comandos/herramientas pueden necesitar autorización/configuración
  del servidor. Las denegaciones hacen fallar el trabajo, aunque Claude produzca texto.
- Lambda no dispone de un adaptador Claude validado; la configuración incompatible
  se rechaza al construir el backend.
- La disponibilidad del modelo depende de la cuenta y del CLI. Una IA diferente
  no garantiza respuestas, uso de herramientas ni resultados idénticos.

Referencia: [CLI de Claude Code](https://code.claude.com/docs/en/cli-reference),
[permisos](https://code.claude.com/docs/en/permissions) y
[Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview).

## Historial y sesiones

El historial pertenece al Bridge. Al cambiar de motor se inicia una sesión nativa
compatible y se entrega el historial completado, acotado a 120.000 caracteres
(principio y final). No se transfiere el estado interno del modelo ni los binarios
de adjuntos antiguos. Las imágenes del turno actual sí se envían. El Reviewer
recibe su entrada específica, sin agregar el historial general del Generator por
esta vía, para conservar la revisión independiente.

Los IDs nativos de Claude llevan `claude:` dentro del Bridge. No se envían IDs de
Codex a Claude ni se aceptan IDs nativos obsoletos desde el frontend. Polling de
trabajos anteriores no restaura una sesión nativa incompatible.

## Evidencia y alcance de las pruebas — 20/10/2026

Claude Code 2.1.304 autenticado con Claude.ai. Pruebas reales: continuidad
Codex → Claude → Codex y Claude → Codex → Claude; modelo Opus 5.5 con esfuerzo
medium; lectura restringida de un archivo; tarea desde archivo para SDD;
creación de archivo con acceptEdits; Supervisor con cierre real y generación de título; detección de escritura denegada con permisos
por defecto. Evidencia HTTP del circuito central en
`.run/claude-compatibility-e2e.json`; verificaciones anteriores en
`.run/claude-dev-probe.json` y `.run/claude-dev-opus55.json`.

La batería de módulos involucrados pasó 123 tests antes de las últimas
regresiones añadidas; se ejecutaron nuevamente los tests afectados después de
cada corrección. Los 10 tests seleccionados de flujos de mensajes pasaron con
`PIPELINE_QUALITY_ENABLED=false`, aislando sus fixtures de la base de calidad real
del workspace. Con la configuración local real, dos de esos tests excedían su
plazo de cinco segundos por la preparación de contexto de calidad. Esto no es una
certificación de toda la suite ni de todas las integraciones externas.

La prueba real también detectó trabajo síncrono bloqueando el hilo HTTP al
consultar `/response`, y una carrera entre la preparación del Reviewer y la
recuperación de turnos. La consulta se trasladó al pool de hilos; el envío del
follow-up revalida la reserva bajo el mismo lock que el recuperador. Una prueba
con dos envíos concurrentes verifica que se crea un solo trabajo.

La repetición del ciclo tras las correcciones finalizó con exactamente un trabajo
Generator y uno Reviewer, ambos completos con IDs nativos Claude. La prueba de
Supervisor y título se guarda en `.run/claude-supervisor-e2e.json`.
