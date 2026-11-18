# Relevamientos de reuniones en Bridge DEV

Estado al 16/10/2026: **implementación local parcial bajo demanda; sin monitor periódico**.
No alcanza todavía para subir una reunión y obtener automáticamente sus resultados.
El pedido original se conserva; la decisión `source-aad59428ebc4ef733184fd9e` reemplaza el monitor por pedidos explícitos de carpeta. Requisito vigente: `REQ-BRIDGE-RELEVAMIENTOS-ON-DEMAND-20261016`.

## Ubicación y componentes

La carpeta [relevamientos](https://drive.google.com/drive/folders/1bSaRi8H3UoAguICer0_wedqkZukArzi5)
fue creada con el conector autenticado debajo de `codex-folder`, y verificada por
lectura de metadatos. Los IDs están en [drive-ids.json](drive-ids.json). Por pedido explícito se descargó el MP3 de Patsa para procesamiento privado; no se modificaron otras carpetas.

`services/relevamientos/` contiene:

- `core.py`: solicitudes acotadas por carpeta, SQLite, etapas, exclusión de salidas, deduplicación por cliente/file ID/revisión, espera de metadatos estables, integridad, reanudación y revisión de hablantes.
- `drive.py`: Drive v3, OAuth renovable, paginación, descarga en streaming y subida multipart; recibos por archivo, comprobación de contenido y actualizaciones condicionadas a ETag.
- `speech.py`: FFmpeg mono 16 kHz, WhisperX/alineación española y Pyannote community-1. Se ejecuta en otro intérprete, para no cambiar dependencias de Bridge.
- `analyzer.py`: reutiliza `LocalExecutionProvider`; configura sandbox read-only, herramientas shell/apps/MCP desactivadas y salida JSON con trazabilidad validada. No se ha probado una llamada real de esta integración ni su resistencia completa a instrucciones maliciosas; esa prueba es requisito previo de activación.
- `cli.py` y `relevamientos.service`: operador y servicio systemd independiente del backend; no requiere una sesión interactiva ni reiniciar DEV/PROD.

Bridge DEV existente: systemd de usuario `codex-mobile-bridge-dev.service`, checkout actual,
puerto interno 8118, health respondió `ok`, identidad `dev`, commit observado `5f95b3feaff5`.
La persistencia y faster-whisper `small` estaban disponibles. El proveedor local y los
adaptadores de transcripción existentes se inspeccionaron. El adaptador de voz actual
devuelve texto plano: no sustituye alineación y diarización de reuniones. El nuevo
worker conserva la caché Hugging Face predeterminada; descargó community-1 en la caché compartida.

## Bloqueos de activación

1. El conector Drive del chat funciona, pero no equivale a un token renovable disponible
   para systemd. Faltan en Secrets `RELEVAMIENTOS_GOOGLE_CLIENT_ID`,
   `RELEVAMIENTOS_GOOGLE_CLIENT_SECRET`, `RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN`.
   No copiar credenciales del conector ni pegarlas en chats, argumentos o archivos de reportes.
   Verificar con ese usuario OAuth lectura de la carpeta existente y escritura únicamente
   dentro del alcance elegido. La API no ofrece un scope OAuth arbitrario por carpeta:
   usar `drive.file` si el grant permite todos los archivos entrantes; si no, acordar un
   grant/identidad dedicada con acceso suficiente. La restricción por IDs de este worker
   no reemplaza la restricción de permisos del proveedor.
2. `HF_TOKEN` y acceso de lectura quedaron verificados (HTTP 200); se descargó el modelo
   [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).
   [WhisperX oficial](https://github.com/m-bain/whisperX) documenta esa dependencia. El repositorio
   se comprobó también mediante `gh repo view` autenticado. No se dedujo ausencia de ningún repositorio por un 404.
3. Se instaló `.venv-relevamientos` aislado con WhisperX 3.8.6, Pyannote 4.0.7 y Torch 2.8.0+cpu. Pasaron una transcripción española sintética y la diarización de una muestra pública; la reunión real sigue en validación. No se instaló sobre el venv activo.
   Host: 4 CPU, 15,4 GiB RAM total, unos 2,3 GiB disponibles y 4 GiB swap ocupada en la inspección;
   no se encontró `nvidia-smi`. Esto no es una prueba de ausencia física de GPU.
   Conviene un worker con memoria disponible o esperar una ventana de recursos.
4. Falta probar el procesamiento y la frontera de herramientas del analizador con material
   sintético, y luego una grabación autorizada en carpeta de prueba. Verificar IDs, resultados,
   reinicio, corrección de participantes y sincronización real con esa identidad OAuth.

FFmpeg quedó instalado **aislado** mediante `imageio-ffmpeg==0.6.0` en
`.data/relevamientos-tools/`, con enlace `ffmpeg`. Se ejecutaron conversiones reales de
WAV, MP3, M4A, MP4 y MKV sintéticos. No se tocó el venv de Bridge. Esto no demuestra transcripción.

## Preparación del worker

Desde la raíz del checkout, con recursos suficientes, preparar un intérprete aislado:

```sh
uv venv .venv-relevamientos
uv pip install --python .venv-relevamientos/bin/python -r services/relevamientos/requirements-speech.txt
```

El rango de dependencia es una receta pendiente de resolución/lock y validación en el worker
objetivo, no una combinación ya probada. Reusar `HF_HOME` y cachés compatibles. Descargar los
modelos sólo con acceso autorizado; las licencias y aceptación de Hugging Face pertenecen al titular.
Para otra máquina Linux, `RELEVAMIENTOS_SPEECH_ARGV` admite un array JSON de argumentos del
adaptador del operador. Recibe un único argumento: ruta absoluta a un JSON con `stage`, `audio`,
`aligned` y `output`. Debe escribir atómicamente ese output y terminar con código 0; archivos
privados deben estar montados o transportarse explícitamente por canal autorizado. No hay
transporte SSH/HTTP automático implementado. El timeout predeterminado es 14.400 segundos.
El proceso separado evita contaminar dependencias, pero sin systemd no limita memoria por sí mismo.

```sh
RELEVAMIENTOS_FFMPEG="$PWD/.data/relevamientos-tools/ffmpeg" .venv/bin/python -m services.relevamientos.cli doctor
.venv/bin/python -m services.relevamientos.cli status
```

La CLI lee el entorno, no interpreta `.env` como shell. systemd usa `EnvironmentFile`.
Para invocaciones manuales cargar únicamente las variables necesarias mediante un gestor de
entorno seguro; no ejecutar `source .env` ni imprimirlo. `doctor` sólo muestra nombres faltantes.

La unidad preparada no tiene activación al iniciar sesión ni reinicio automático.
No instalar temporizadores ni ejecutar `enable --now`. Cada pedido debe proporcionar
carpeta y referencia explícitas. Ejemplo con OAuth disponible:

```sh
.venv/bin/python -m services.relevamientos.cli run --folder Patsa --source-ref ID_DEL_PEDIDO
```

La CLI verifica una única carpeta (ID o nombre no ambiguo), guarda el pedido, hace dos
lecturas de estabilidad y termina. Repetir el pedido conserva trabajos terminados.
Para reanudar, ejecutar nuevamente el mismo pedido; otras carpetas no se procesan.
El conector del chat permite obtener material cuando falta OAuth del worker, pero esa
operación asistida no demuestra automatización autónoma completa.

## Estados y recuperación

Sin polling. Una espera de estabilidad mínima de 60 s dentro del pedido
(`RELEVAMIENTOS_SETTLE_SECONDS`). Cliente vacío sólo se registra. Se consideran grabaciones
los archivos directos del cliente con extensión compatible, tamaño positivo, revisión y permiso
de descarga. Se comprueba revisión antes/después y tamaño/hash, no se confía sólo en el nombre.
Las salidas están en subcarpetas y los `.md/.json` nunca son entradas.

Estados persistidos: DISCOVERED, WAITING_UPLOAD, QUEUED, DOWNLOADING, TRANSCRIBING,
DIARIZING, NEEDS_SPEAKER_REVIEW, ANALYZING, SYNCING, COMPLETED y FAILED.
Eventos quedan en la misma SQLite. Fallos guardan etapa y clase de error sin mensajes privados.
Reintentos con backoff hasta 3600 s; un reinicio continúa la etapa registrada. Una caída dentro
de un cálculo puede repetir esa etapa; no hay garantía exactly-once de consumo de Codex si cae
entre su respuesta y el guardado. Fallos de sincronización no repiten transcripción ni análisis.

```sh
.venv/bin/python -m services.relevamientos.cli retry ID_JOB
.venv/bin/python -m services.relevamientos.cli reprocess ID_JOB
.venv/bin/python -m services.relevamientos.cli speakers ID_JOB --file RUTA_PRIVADA_NOMBRES.json
```

`retry` exige FAILED. `reprocess` archiva el directorio anterior y reinicia la descarga.
Los nombres se asignan con un objeto como `{"SPEAKER_00":"Nombre confirmado"}` incluyendo
exactamente las etiquetas del transcript. `null` conserva la etiqueta sin atribuir identidad.
Corregir nombres sólo repite análisis/sincronización. Solapamientos o ausencia de etiqueta llevan
a revisión; los solapamientos se detectan por intersección de turnos, no por certeza de identidad.

Límites: 4 GiB por archivo, cuatro horas de audio, 500.000 bytes por contexto de análisis.
Se rechaza lo que excede, sin truncar silenciosamente transcripciones o historia del cliente.
No hay aún particionado automático de reuniones largas. Un ID de reunión es un hash estable
cliente/file ID/revisión, evitando colisiones por nombres iguales. Carpetas antiguas conservadas.

## Conciliación y privacidad

Cada archivo remoto se compara con la huella de la última subida. Si cambió manualmente, se
preserva y se crea `conflict.json` local; no se sobreescribe. Sin ETag la actualización falla cerrada.
Una conciliación requiere revisar ambas versiones y plasmar la corrección en fuentes/mapa o en
el resultado local **antes** de que coincida con el remoto. No editar recibos para forzar una subida.
No se implementó aún una interfaz de merge asistido; los conflictos permanecen pendientes.
Si el contenido remoto ya coincide con el resultado se recupera el recibo, cubriendo una caída
posterior a la subida. `estado.json` se sube al final; la SQLite es el estado operativo autoritativo.

El directorio privado es `.data/relevamientos/`, excluido de Git, con directorios 0700 y archivos
0600. Incluye originales descargados, audio, transcripciones, nombres, análisis, cola y recibos.
No subirlo a reportes ni backups públicos. No hay borrado automático ni política de retención
impuesta; conservar fuentes hasta acordar eliminación. Logs operativos sólo contienen contadores,
estados y clases de error; no habilitar volcado de respuestas HTTP o salida cruda de modelos.

**Codex puede transmitir la transcripción y el historial de reuniones a un servicio remoto**,
aunque WhisperX/Pyannote se ejecuten localmente. Eso puede consumir uso de Codex; no se midió
facturación. Jev no fue invocado ni recibió datos. Reglas de herramientas consultadas en
[la referencia oficial de Codex](https://learn.chatgpt.com/docs/config-file/config-reference).
Los flags de configuración reducen superficie, pero no sustituyen una prueba de aislamiento real.

## Evidencia reproducible

```sh
.venv/bin/python -m pytest tests/test_relevamientos.py -q
.venv/bin/python scripts/check_relevamientos.py
.venv/bin/python scripts/check_relevamientos_audio.py
```

Ver [informe y recibos](../../reports/relevamientos-20261016/INFORME.md).
Los tests usan Drive, ASR y analizador sintéticos; los transportes HTTP se ejercitan con MockTransport.
La prueba FFmpeg sí usa el binario real sobre tonos generados. Las pruebas de modelos están en `spanish-smoke.json` y `diarization-smoke.json`. No equivalen a comprensión semántica, flujo completo ni subida de resultados reales comprobados.
