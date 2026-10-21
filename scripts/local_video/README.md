# Tutoriales locales de RD

Decisión del 29/09/2026: **voz 1 por defecto en todos los videos normales**.
Es Chatterbox Multilingual v3, referencia Buenos Aires `arm_06136`, parámetros
fijados en `voices.json`. Peter (`spanish_24l`) se usa únicamente con `--fast`
y sólo cuando la persona pide expresamente rapidez. No hay fallback automático.
Si falla voz 1, se informa el error y se conserva la elección.

La receta `rd-documents.json` contiene el texto por escena. `record_rd.mjs`
recorre la interfaz real local de RD con Playwright, graba sus cambios y muestra
los toques. `voice.py` sintetiza en CPU; `render.py` compone MP4 vertical con voz,
texto visible y SRT. No hay agente pensando cada clic ni API de IA en estos scripts.
Cambios de pantalla requieren mantener los selectores, como un test de navegador.

## Repetir sin Codex

Desde la raíz de este workspace, con los modelos y dependencias ya instalados:

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/run.py \
  --rd-project /home/batata/Projects/rd-gestion-hse/tmp/document-renewal-dev \
  --node /home/batata/.nvm/versions/node/v22.22.2/bin/node \
  --output reports/mi-video-rd
```

Para cambiar sólo la composición o repetir el render de una carpeta existente:

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/run.py \
  --output reports/rd-video-local-20260929 --reuse-capture
```

`--fast` cambia explícitamente a Peter. Omitirlo siempre selecciona voz 1.
El comando debe ejecutarse con el Python del laboratorio, que incluye Pillow.
Requiere el checkout de RD con dependencias y build web ya preparados. El servidor
E2E crea datos ficticios en su almacenamiento aislado del puerto 18879 y se cierra
al terminar. No usar un puerto ocupado por otra prueba. No se conecta a RD publicado.

## Costo y reutilización

| Trabajo | Tokens facturados de API |
|---|---|
| Sintetizar voz local, capturar UI, subtitular, editar y exportar | 0 |
| Repetir este comando desde terminal/tarea programada sin agente | 0 |
| Conversar con Codex para escribir o modificar la receta | Usa la cuota/tokens de Codex |

El modo «local» de Codex **no** convierte su modelo en un modelo local sin consumo.
[Documentación oficial de uso de Codex](https://learn.chatgpt.com/docs/pricing).
No medimos aquí una factura ni el número de tokens de esta conversación.
Sí se usa CPU, memoria, disco, electricidad y tiempo; no es costo operativo cero.

La caché en `~/.cache/rd-local-video/audio` depende del texto, perfil, parámetros
y huella de la referencia. Verifica SHA-256 antes de reutilizar. Cambiar una frase
regenera sólo esa escena; cambiar el perfil invalida las escenas de ese perfil.
El render y la captura funcionan sin modelo de lenguaje. Un video completamente
nuevo necesita un guion y una secuencia de acciones, que pueden escribirse a mano
o con Codex una vez y reutilizarse después. Pedírmelo en el chat también usa Codex,
aunque el programa que ejecuto no tenga llamadas de API.

## Entorno instalado

Fuera del repositorio, en `~/.local/share/rd-video-lab`:

- `venv`: Python, torch/torchaudio 2.6 CPU, Chatterbox 0.1.7, NumPy 1.26.4,
  Transformers 5.2.0, imageio-ffmpeg 0.6.0, Pillow y faster-whisper.
- `chatterbox`: fuente fijada al commit `5de7a54aa4e5e2baadb0182dde554908b48b85c2`.
- `pocket-env`: entorno separado, Pocket TTS 3.3 y NumPy 2.5.3.
- Pesos en caché Hugging Face. La revisión de Chatterbox está en `voices.json`.
  `voice.py` exige pesos locales y bloquea conexiones de Python durante la síntesis.

El arranque desde una máquina nueva requiere instalar estos entornos y descargar
los pesos antes de trabajar offline; no se incluyeron gigabytes de modelos en Git.
La referencia aprobada sí está en `assets`, junto a su atribución CC BY-SA 4.0.
Se conserva la marca de agua nativa del modelo. La narración es sintética, no una
grabación del voluntario diciendo el guion. Ver [atribución](assets/ATTRIBUTION.md).

## Comprobaciones

`check.py` valida MP4/audio, movimiento, la referencia elegida, el modo rápido,
reutilización real de caché y rechazo de un archivo alterado. `transcribe.py` es
una comprobación adicional de inteligibilidad con Whisper local: no califica la
naturalidad ni certifica un acento. Los subtítulos se muestran por escena.

## Segunda versión: movimiento y sincronización

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/run.py \
  --v2 \
  --rd-project /home/batata/Projects/rd-gestion-hse/tmp/document-renewal-dev \
  --node /home/batata/.nvm/versions/node/v22.22.2/bin/node \
  --output reports/rd-video-local-v2-20260929
```

Agregar `--reuse-capture` reutiliza las imágenes existentes. `--v2` conserva voz 1.
Peter sigue disponible con `--fast` en la receta original, sin `--v2`: las marcas
revisadas de V2 corresponden a la locución aprobada y no se transfieren a otra voz.

La grabación V2 incluye scroll suave, puntero animado y captura de cada cambio
que entrega Chromium. `align.py` obtiene marcas de palabras con Whisper local
(no un LLM) y las cachea por huella del audio. `render_v2.py` aplica nueve marcas
de acciones a una línea temporal, muestra subtítulos por frase y monta una sola
pista PCM antes de codificar AAC. No modifica el tono ni la velocidad de la voz.
El guion no se vuelve a generar: se reutilizan sus cuatro WAV verificados.

Las marcas son específicas de este guion, esta referencia y estos parámetros.
Whisper proporciona estimaciones; cambiar el guion requiere revisar las palabras
y las marcas de la receta. No se añadió una promesa de sincronizar cualquier
aplicación automáticamente. Para repetir una receta revisada no hace falta
ninguna consulta de IA externa. Crear un guion o adaptar código con Codex sí
consume su uso; editarlo a mano y ejecutar el programa no consume tokens de API.

`check_v2.py --replay` vuelve a realizar el flujo de RD en otro entorno local
vacío, reutiliza voz y alineación, exporta un MP4 y valida el archivo entregado:
comparación de imágenes en las nueve marcas, comprobación de tiempos de audio,
movimiento real y conservación de los WAV. Las muestras de imágenes no reemplazan
la evaluación humana de la fluidez del video completo.

## Ritmo predeterminado para mostrar a clientes

Decisión del 29/09/2026: usar el montaje tranquilo de aproximadamente 44 segundos,
con más tiempo para cada pantalla, conservando voz 1 a velocidad natural. La receta
`pacing.py` contiene las pausas y tiempos. Para esta funcionalidad, reutilizar V2:

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/run_calm.py \
  --source reports/rd-video-local-v2-20260929 \
  --output reports/rd-video-local-v3-20260929
```

El comando conserva la fuente, copia sólo su captura y narración DEMO y ejecuta el
render local con `--calm`. No invoca TTS, Whisper ni un LLM. Las cinco pausas se
insertan en límites revisados del audio; los fragmentos conservan duración y tono,
con fundidos de 4 ms en los empalmes. Para otros guiones hay que revisar sus límites.

## Presentación completa, hasta un minuto

`bookends.py --config scripts/local_video/rd-bookends.json --output CARPETA`
añade apertura y cierre al tutorial aprobado. Ejecutar con el Python del laboratorio
local. El JSON configura cliente, título, subtítulo, CTA, frases, logos y pausas.
La configuración RD usa 43,83 s de recorrido y dos placas breves. El límite de
60 s es obligatorio aunque el JSON pida más. Un texto demasiado largo debe
acortarse; nunca se acelera el tutorial para hacerlo entrar.

Los logos reales se conservan en `assets/brand`, con origen y SHA-256. Para otro
cliente, copiar su recurso autorizado y cambiar `client_logo`; Nienfos aparece
únicamente en el cierre. La plantilla conserva proporciones y colores, y elimina
sólo el margen transparente. No genera marcas con IA.

La voz nueva usa el perfil predeterminado y caché por texto/parámetros. El cuerpo
se copia como video sin recodificar; el audio PCM completo se monta y codifica una
sola vez para evitar deriva en los empalmes. Subtítulos y marcas se desplazan por
la duración exacta de la apertura, sin LLM. Un guion distinto en el cuerpo exige
su propia receta y alineación previa. No representa grabación automática de
cualquier función por conocer únicamente su título.

## Guía con portada inmediata y controles editoriales

Para la versión RD aprobada, ejecutar `run_guided.py --output CARPETA`.
Reutiliza sus capturas y audio, conserva todos los tiempos, amplía la permanencia
de subtítulos y anima la pequeña barra de progreso del paso. No necesita TTS ni
alineación nuevos. La placa inicial ahora tiene `instant_intro: true` en el JSON:
el título se ve desde el fotograma cero; también se entrega `portada.jpg`.

`guide_qc.py CARPETA` comprueba fotograma inicial, duración, subtítulos y audio
PCM mediante píxeles, tiempos y energía. Sus umbrales son decisiones editoriales
locales, sin IA ni servicio externo. La receta falla ante un control incumplido.
Para otra funcionalidad se necesita su recorrido/alineación propios; las reglas
de calidad y la plantilla de placas se pueden reutilizar. Los videos anteriores
permanecen disponibles para comparación.

## Dirección editorial de Codex

El flujo recomendado para decidir silencios es `editorial.py --source BODY --output
brief.json`, lectura de ese resumen por el Codex activo, escritura de `pacing-plan.json`
y `run_guided.py --source BODY --pacing-plan PLAN --output CARPETA`. El plan tiene
huella de entrada, tiempos distintos por escena y motivos editoriales. El render
no llama a Codex. Ver `skill/local-feature-videos/pacing.md` para el esquema.
La skill instalada es `local-feature-videos`; su fuente revisable está en
`skill/local-feature-videos`. Ya no se considera que 40–45 s de cuerpo sea una
meta obligatoria: se decide según contenido, manteniendo el tope de un minuto.
Sin `--pacing-plan` se conserva el modo anterior para reproducir comparaciones.

## Música ambiental opcional

`music.py --source VIDEO_SECO --plan MUSIC_PLAN --output OTRA_CARPETA` genera una
base procedural local de acordes sostenidos y mezcla sin modificar la voz o el
video. `run_guided.py --music-plan MUSIC_PLAN ...` integra esa etapa y conserva
ambas versiones. El JSON elige `none` o `soft-ambient`, nivel relativo, atenuación
y fundidos. No hay modelos musicales ni pistas descargadas. Ver
`skill/local-feature-videos/music.md`. Los silencios se miden siempre en la voz
separada, y la mezcla final se comprueba además por sus niveles y sincronización.
