---
name: local-feature-videos
description: Crear tutoriales breves de funcionalidades con grabación local, voz rioplatense y subtítulos; Codex decide el ritmo a partir de un resumen compacto y los scripts montan el video. Usar para demos de software y para mejorar pausas o sincronización de esos videos.
---

# Videos de funcionalidades con dirección editorial

El Codex de esta conversación es el editor. Decide pausas según lo que el cliente
necesita entender; entrega un JSON y ejecuta scripts. No añadas un segundo agente
ni una API de modelos al render. Los silencios medidos no equivalen automáticamente
a errores: lectura, búsqueda de un control y confirmación requieren tiempos distintos.

## Recursos instalados en esta computadora

- Motor: `/home/batata/Projects/codex-cli-mobile-bridge/scripts/local_video`.
- Python: `/home/batata/.local/share/rd-video-lab/venv/bin/python`.
- Voz predeterminada: `voz-1`, Chatterbox Multilingual v3, referencia `arm_06136`.
  Peter es sólo para una petición explícita de rapidez, nunca un fallback.
- Ejemplo RD aprobado: `reports/rd-video-guia-20260929/body` dentro del Bridge.
- Esquema, ejemplo y límites: [referencia de ritmo](pacing.md). Cargar cuando haya
  que generar o ajustar el JSON, sin leer todos los scripts y reportes históricos.

## Entrada desde proyectos y pipeline

Para un pedido nuevo de video, cargar [pipeline.md](pipeline.md): registra el pedido
en el proyecto solicitante, espera la validación de la función y continúa en esta
sesión. No preparar videos durante el desarrollo si no fueron pedidos.

## Flujo

1. Localizá el proyecto y la función real. Inspeccioná sólo los archivos relevantes
   y el recorrido. Prepará datos DEMO y evitá destinatarios reales. La receta RD
   es un ejemplo específico, no un grabador genérico para cualquier app: otra
   función requiere adaptar acciones de Playwright, guion, captions y marcas de
   palabras. Nunca uses las capturas RD para representar otro cliente.
2. Prepará frases breves con voseo profesional y una indicación por acción. Reutilizá
   audios y capturas existentes cuando el contenido no cambió. Para una receta nueva,
   `voice.py` sintetiza localmente y `align.py` obtiene marcas locales aproximadas;
   revisá los límites de frase y acciones, sin suponer que la transcripción es exacta.
3. Generá el resumen con `editorial.py`. Si es una función nueva y todavía no hay
   `render.json` ni `aligned-narration.wav`, generá primero un borrador local con
   la receta adaptada y tiempos iniciales; no requiere observarlo entero ni otra
   llamada a un modelo. Leé ese JSON: contiene el texto, acciones,
   duración de voz, pausas y espera acumulada entre escenas. Normalmente eso basta
   para decidir; pedí fotogramas de las marcas dudosas si faltan datos visuales.
   No cargues cientos de frames o logs completos al contexto.
4. Escribí el plan: entrada y salida por escena, pausas internas y una razón concreta.
   Evitá sumar una larga pausa final y otra inicial por defecto. Dejá más lectura
   para fechas, destinatarios o una plantilla que para un clic sencillo. Decidí por
   contenido, sin aplicar el mismo multiplicador a todas las escenas ni perseguir
   una duración fija a costa de comprensión. Conservá velocidad y tono de voz.
5. Ejecutá una receta con `--pacing-plan`, y los controles de `guide_qc.py`. El modelo
   no participa mientras corre. Reutilizar el mismo texto, voz y parámetros debe dar
   caché por huella. Si falla, corregí el motivo concreto; no desactives el control.
6. Leé sólo el resumen de resultados y observá una lámina de inicio, acciones y cierre.
   Ajustá el plan si las medidas o imágenes lo justifican. No prometas perfección ni
   naturalidad auditiva sin escuchar. Entregá MP4, portada y explicación de cambios
   en el workspace del chat actual; si está en otro proyecto, copiá sólo esos entregables
   no secretos antes de enlazar. Conservá la versión anterior.

## Convenciones de este flujo

Máximo un minuto, salvo nueva indicación. Apertura y cierre breves, título visible
ya en t=0. Logos originales de Nienfos y cliente juntos sólo en cierre; no inventar
ni deformar marcas. Subtítulos legibles, puntero y scroll suaves, avisos de DEMO.
No publicar apps ni enviar correos como efecto lateral de producir un tutorial.

Preparar guion y criterio editorial en Codex consume uso del chat. Medir, sintetizar
localmente, sincronizar y renderizar no llaman a modelos externos. Informá caracteres
medidos del resumen si ayuda; no conviertas eso en una factura o tokenización exacta.

## Música opcional

El usuario prefiere la entrega con música baja; conservar también la opción seca.
El estilo recurrente elegido es B, `light-keys`, al volumen aprobado. Consultar
[música local](music.md), elegir modo/nivel/atenuación y ejecutar la mezcla.
No usar la energía de la mezcla para juzgar silencios de la voz: medir la narración
aislada y verificar también el audio final. No declarar escucha si sólo se midió.

Para resaltar pulsaciones o controles, consultar [actions.md](actions.md).

## Composición predeterminada

Aplicar [screen-template.md](screen-template.md) para que la app ocupe casi todo el
cuadro vertical. Personalizar cliente y colores; mantener subtítulos compactos
fuera de los controles. Este es el formato de entrega de los nuevos videos.
