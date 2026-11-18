# Prompt para pasarle al agente de la Lenovo

Implementá en este programa de grabación/transcripción/subida una confirmación fiable de entrega para Codex Mobile Bridge. Inspeccioná primero el código real del proyecto y reutilizá su integración autenticada con Google Drive. No solicites ni muestres secretos; usá el gestor de credenciales del programa.

## Organización acordada

Google Drive, carpeta existente `codex-folder`, ID verificado `11wixeZFVL4X-l71TYInIYl-lYanjek7a`:

```text
codex-folder/
  <nombre-exacto-del-proyecto-en-Bridge>/
    relevamientos/
      foco.md                       # opcional; no lo genera ni modifica el grabador
      <fecha-hora_tema-de-reunion>/
        audio.mp3                   # o video.mp4; una sola grabación principal
        transcripcion.md            # .md/.txt/.srt/.vtt UTF-8
        resumen.md                  # .md/.txt/.srt/.vtt UTF-8
        adjuntos/
          foto.jpg
          documento.pdf
        LISTO.json                  # generado y subido automáticamente AL FINAL
```

Cada reunión tiene su propia carpeta. No subir fuentes en la raíz del proyecto ni crear una carpeta `sesiones` intermedia. Respetar los nombres y la organización existente fuera de esta entrega. Usar IDs de Drive después de resolver la raíz; nombres repetidos de carpetas/archivos son un error que requiere resolución, no elegir el primero. El nombre del proyecto debe coincidir exactamente con el registrado en Bridge.

## Contrato LISTO.json, versión 1

```json
{
  "schema_version": 1,
  "status": "complete",
  "project": "nombre-exacto-del-proyecto-en-Bridge",
  "meeting_id": "c6b50a44-cea3-47f5-9425-2e1355e68388",
  "revision": 1,
  "folder_id": "ID_REAL_DE_LA_CARPETA_DE_ESTA_REUNION",
  "completed_at": "2026-11-03T18:30:00-03:00",
  "files": [
    {
      "path": "video.mp4",
      "drive_id": "ID_REAL_DEL_VIDEO",
      "role": "video",
      "size": 123456,
      "sha256": "HASH_SHA256_REAL_DE_64_CARACTERES_EN_MINUSCULAS"
    },
    {
      "path": "transcripcion.md",
      "drive_id": "ID_REAL_DE_LA_TRANSCRIPCION",
      "role": "transcript",
      "size": 2345,
      "sha256": "HASH_SHA256_REAL_DE_64_CARACTERES_EN_MINUSCULAS"
    },
    {
      "path": "resumen.md",
      "drive_id": "ID_REAL_DEL_RESUMEN",
      "role": "summary",
      "size": 456,
      "sha256": "HASH_SHA256_REAL_DE_64_CARACTERES_EN_MINUSCULAS"
    },
    {
      "path": "adjuntos/foto.jpg",
      "drive_id": "ID_REAL_DE_LA_FOTO",
      "role": "attachment",
      "size": 7890,
      "sha256": "HASH_SHA256_REAL_DE_64_CARACTERES_EN_MINUSCULAS"
    }
  ]
}
```

El JSON anterior ilustra el formato; sus IDs, tamaños y hashes son ejemplos, no valores para subir. Generar todos los valores reales. `meeting_id` es un UUID generado una vez por reunión y persistido antes de subir; no regenerarlo al reintentar. `folder_id` es el ID real de su carpeta remota. Las rutas son relativas a esa carpeta y usan `/`.

La lista incluye exactamente una grabación principal: un video (mp4, mkv, mov, webm, m4v o avi) con `role: "video"` O un audio MP3 con `role: "audio"`; además, una transcripción, un resumen y todos los archivos de `adjuntos`, incluidos los de subcarpetas. Si no hay adjuntos, omitir sus entradas; la carpeta puede quedar vacía o no existir. No incluir LISTO.json dentro de su propia lista. No agregar archivos temporales, fuentes ocultas ni accesos directos de Drive. Los documentos deben ser archivos subidos (PDF, DOCX, XLSX, etc.); para documentos nativos Google se requiere exportación previa a un formato de archivo, no un shortcut.

Límites actuales del receptor: 100 adjuntos, 25 MB por transcripción/resumen/adjunto, 100 MB sumados entre transcripción/resumen/adjuntos, 4 GiB por grabación principal (video o MP3), 5 GiB de entrega total. El receptor limita el contexto textual completo a 500.000 bytes y 20 imágenes; no debe truncar silenciosamente una reunión larga. Manifest máximo 128.000 bytes. No más de cinco niveles de subcarpetas en adjuntos. Archivos vacíos no se admiten. Detectar y explicar límites antes de prometer compatibilidad.

## Entrega de audio MP3

El receptor acepta audio MP3 desde el 04/11/2026, conservando `schema_version: 1` y compatibilidad con los videos existentes. Para una reunión de audio, reemplazar únicamente la entrada de video del ejemplo por:

```json
{
  "path": "audio.mp3",
  "drive_id": "ID_REAL_DEL_AUDIO",
  "role": "audio",
  "size": 123456,
  "sha256": "HASH_SHA256_REAL_DE_64_CARACTERES_EN_MINUSCULAS"
}
```

Generar tamaño, ID y hash reales. El nombre del MP3 es libre y la extensión no distingue mayúsculas. Conservar transcripción, resumen, adjuntos y `LISTO.json` con el mismo orden de subida y verificación. No etiquetar un MP3 como `video` ni como `attachment`; la grabación principal va en la raíz de la reunión. No incluir simultáneamente audio y video como grabaciones principales. El Bridge usa la transcripción existente: no vuelve a transcribir el MP3. Adaptar la selección de formato y la generación del manifiesto en el programa de la Lenovo; esta documentación no modifica ese programa remoto.

## Orden obligatorio de finalización

1. Finalizar grabación, Whisper y resumen. Congelar la lista de adjuntos seleccionados para esta entrega. Calcular tamaño y SHA-256 de los bytes finales de cada archivo; no calcularlos sobre archivos que todavía estén escribiéndose.
2. Subir todos los archivos, esperar el cierre confirmado de cada carga y persistir sus IDs. No tomar “agregado a la cola de sincronización” como “subido”.
3. Consultar Drive autenticado para verificar la ubicación de cada archivo (parents), su tamaño y, cuando esté disponible, `sha256Checksum`. Si falta checksum remoto, verificar los bytes remotos por descarga/hash antes de publicar el marcador. Comprobar que no hay archivos extra, nombres duplicados ni adjuntos pendientes.
4. Sólo después, generar el JSON y crear `LISTO.json` remoto con contenido completo en una operación de subida. Confirmar que quedó subido y que su contenido coincide. Nunca crear primero un LISTO vacío ni publicarlo mientras faltan archivos. Un archivo local dentro de una carpeta sincronizada no demuestra ese orden remoto: si se usa Drive Desktop, conectar la verificación con la API autenticada o implementar otra confirmación real antes de publicar el marcador.
5. Una falla/interrupción deja la entrega incompleta, SIN publicar una confirmación válida. Persistir el avance para reanudar conservando meeting_id y los IDs de archivos ya verificados. Antes de modificar una entrega cerrada, retirar/inactivar su marcador remoto y verificar esa operación; no dejar un LISTO antiguo presentando archivos mutables como completos.
6. Incorporar adjuntos posteriores requiere una nueva revisión del manifiesto después de volver a verificar todo. El Bridge no relanza automáticamente un análisis ya aceptado por editar una carpeta: requiere reprocesamiento explícito. Informar al usuario si la primera entrega ya pudo haber sido analizada.

El monitor de Bridge revisa cada 600 segundos. Verifica el marcador, inventario exacto, IDs, tamaños, hashes y estabilidad de la entrega durante la validación. Sin LISTO.json válido, espera. No depende de que el usuario mande un mensaje. El análisis y sus resultados permanecen en un chat del proyecto; el Bridge NO sube relevamientos ni otros resultados a Drive.

## Validación y entrega del trabajo

Probar carga parcial sin marcador, interrupción de carga, hash incorrecto, adjunto faltante, adjunto no listado, reanudación sin duplicados y entregas completas de video y MP3. Comprobar también rechazo de dos grabaciones principales, MP3 con rol incorrecto y descarga/hash de audio cuando Drive no provee checksum. Usar una carpeta de prueba explícita para la prueba real y reportar sus IDs sin credenciales. No afirmar que Bridge ya lo procesó si sólo se verificó la subida. Dejar un ejemplo real del marcador (sin contenido privado adicional), la ruta de la implementación y los pasos para repetir la prueba.
