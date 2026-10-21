# Pedir videos desde cualquier proyecto

Esta skill es compartida por las sesiones de este usuario en esta computadora.
No copiar modelos ni el motor a cada repositorio. En otra máquina hay que instalar
skill, dependencias, modelos y referencias antes de prometer el mismo flujo.

## Cuándo entrar

- «Implementá X y después hacé un video»: registrar el pedido y mantenerlo en el
  handoff del trabajo; terminar y validar la función antes de guion, capturas o render.
- «Hacé un video de X» con función existente: revisar su estado y seguir directamente.
- Sin pedido: al cerrar una función visible se puede ofrecer una única vez. Consultar
  historial; no insistir si ya se ofreció o rechazó. No preguntar por videos en bugs
  internos, revisiones o estados. No preparar un guion, cargar modelos ni renderizar
  por una mera mención descriptiva o por el recordatorio del pipeline.

El recordatorio es una instrucción al Codex activo, no un detector de intenciones
ni una máquina de estados automática. Codex decide usando el contexto. No crea una
segunda sesión ni llama a otra API de modelos.

## Registrar sólo un pedido explícito

Ejecutar desde el workspace solicitante, con un ID corto y una referencia real al
pedido. Describir la función sin datos de clientes ni credenciales:

```bash
python3 /home/batata/Projects/codex-cli-mobile-bridge/scripts/local_video/project.py \
  --workspace "$PWD" --feature-id nueva-funcion \
  --feature 'Explicar la nueva función validada' --request-ref 'REFERENCIA_REAL'
```

Agregar `--feature-ready` sólo cuando la funcionalidad haya sido validada.
`--fast` sólo si el usuario pidió rapidez explícitamente. Por defecto voz 1,
música B baja, máximo 60 segundos y `screen_template` para pantalla grande.
La geometría fuente (`source_ui_rect`) queda pendiente del adaptador específico. Guarda `.local-videos/ID/request.json` y propone
`reports/videos/ID/` como entrega en ese proyecto. Repetir el mismo ID reutiliza el
registro: no duplica videos ni borra el progreso. Un cambio material requiere otro
ID o actualizar explícitamente el registro. Los bloqueos de recursos quedan visibles.
La revisión inicial sólo comprueba archivos; no acredita modelos, dependencias ni
un recorrido ejecutable. No declarar que ya existe video ni un render en marcha.

## Completar el trabajo con el mismo Codex

Leer el registro y el proyecto. Para un proyecto nuevo hay que preparar su propio
adaptador de grabación, guion y referencias visuales. Registrar la ruta de la receta
local en `recipe`, los resultados de validación y los bloqueos concretos. Nunca
usar pantallas RD para representar otro proyecto. Logos auténticos; datos DEMO;
no enviar correos reales. Preparar referencia de voz y caché como indica SKILL.md.

Seguir el flujo de resumen compacto y plan editorial de [pacing.md](pacing.md).
Invocar los scripts con rutas explícitas del proyecto. La receta RD es un ejemplo
adaptable, no un ejecutor universal: sus IDs y marcas requieren adaptación.
Usar [default-music-plan.json](default-music-plan.json), conservar salida sin música,
ejecutar controles sobre voz aislada y MP4 final. Al entregar, actualizar `status`
a `delivered`, `recipe` y enlaces relativos de entregables/evidencia en el registro;
si falla, `blocked` con el motivo. Esos estados los mantiene Codex con evidencia,
no el preparador. Conservar versiones anteriores y reflejarlo en el handoff.

Guion, adaptación del recorrido y decisiones editoriales consumen uso de Codex.
La síntesis, la sincronización, la música y el montaje son locales sin APIs de
modelos. No prometer costo cero de todo el trabajo ni igual duración para una
funcionalidad nueva. No publicar backend, app ni archivos como efecto lateral.
