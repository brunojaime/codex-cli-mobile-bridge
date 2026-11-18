# Relevamientos automáticos desde Google Drive

Actualizado el 04/11/2026. Soporta video o audio MP3 como grabación principal. Receptor implementado y activado en Batata; primera entrega real pendiente.

**Actualización operativa posterior del mismo día:** autorización renovada con `brunoe.jaime@gmail.com`, acceso real a Drive comprobado, endpoint cargado y monitor habilitado/activo con primera revisión `scan_complete`. Batata está lista para recibir una entrega real; la carpeta de prueba aún está vacía. Ver [estado actual y evidencia](../../../reports/relevamientos-automaticos/INFORME.md). Las descripciones de bloqueos OAuth y activación pendientes más abajo conservan el historial previo a esta comprobación.

## Organización definitiva

```text
Google Drive/
  codex-folder/
    <nombre-exacto-del-proyecto-en-Bridge>/
      relevamientos/
        foco.md
        2026-11-03_153000_revision-de-permisos/
          audio.mp3                 # o video.mp4, una sola grabación
          transcripcion.md
          resumen.md
          adjuntos/
            foto.jpg
            documento.pdf
          LISTO.json
        2026-11-10_100000_seguimiento/
          video.mp4
          transcripcion.md
          resumen.md
          adjuntos/
          LISTO.json
```

El proyecto va directamente dentro de Codex Folder; cada reunión, directamente dentro de `relevamientos`. No hay nivel intermedio `sesiones`. La carpeta del proyecto debe coincidir exactamente con `name` del catálogo `/workspaces` del Bridge. Coincidencias inexistentes o ambiguas quedan pendientes, sin crear proyectos ni adivinar asociaciones.

Se verificó con el conector autenticado la raíz `codex-folder`, ID `11wixeZFVL4X-l71TYInIYl-lYanjek7a`. No usar el ID de la antigua carpeta global `relevamientos` como raíz nueva.

**El Bridge no escribe resultados en Google Drive.** El informe completo queda en un chat de esa reunión dentro del proyecto en la app. Los archivos recibidos son fuentes; el resumen no sustituye la transcripción completa.

## Confirmación y disparador

El servicio independiente revisa Drive al arrancar y espera **600 segundos** después de cada recorrido antes de revisar nuevamente. Puede funcionar con la app cerrada una vez activado y autorizado.

La Lenovo publica `LISTO.json` como último paso automático, después de finalizar Whisper, el resumen y todas las cargas, incluidos los adjuntos. Un archivo local sincronizado o unos minutos sin cambios no confirman una entrega remota.

El marcador incluye versión del contrato, proyecto, UUID persistente de reunión, revisión, ID de carpeta, fecha con zona horaria e inventario completo de archivos con ruta, ID remoto, rol, tamaño y SHA-256. Ver el [prompt para la Lenovo y formato exacto](PROMPT_LENOVO.md).

El monitor exige exactamente una grabación principal (video con `role: "video"` o MP3 con `role: "audio"`), una transcripción y un resumen no vacíos, más todos los adjuntos declarados. Verifica inventario exacto (sin archivos extra), IDs, tamaños, permiso de descarga y huellas. Para textos y adjuntos descarga y calcula SHA-256; para la grabación de video o audio compara la huella de Drive y, si no está disponible, descarga en streaming para calcularla. Una segunda lectura del árbol confirma que ni fuentes ni marcador cambiaron durante la validación. Si algo falla, espera al siguiente ciclo y no inicia el análisis.

Los documentos deben ser archivos subidos como PDF/DOCX/etc.; no shortcuts ni documentos nativos Google sin exportación. Los límites están especificados en el prompt de integración.

## Foco, análisis y resultado

[prompt-base.md](prompt-base.md) requiere analizar las fuentes completas y contrastar cada pedido con documentación, código y pruebas del proyecto. La salida es una lista de 5–10 cambios accionables para Codex (menos si alcanza), con objetivo de 200–300 palabras y máximo de 350. Se omiten crónica, horarios, metadatos, tablas de evidencia y reparto de responsabilidades. Lo ya resuelto no se propone de nuevo; las preguntas se limitan a decisiones que bloquean una tarea concreta. El archivo opcional `relevamientos/foco.md` orienta las entregas futuras hasta editarlo o borrarlo; ver [ejemplo](foco.example.md).

El monitor congela prompt, foco y fuentes antes de enviar el pedido. Cada reintento usa la misma composición. El backend abre un chat con un agente y una respuesta de relevamiento, sandbox de lectura y conectores MCP/apps desactivados. No implementa cambios ni publica resultados.

Se reutiliza la extracción textual de PDF, DOCX, XLSX y PPTX y se adjuntan imágenes al proveedor. ZIP aporta un listado; formatos sin extractor o documentos sin texto quedan señalados para revisión. No se vuelve a transcribir el video ni el MP3, ni se realiza análisis visual automático del video. El programa de la Lenovo debe declarar el MP3 con `role: "audio"` en `LISTO.json`, conservando el contrato versión 1 y el resto de las fuentes; ver [integración de MP3](PROMPT_LENOVO.md#entrega-de-audio-mp3). La consolidación de informes anteriores no está implementada en este primer flujo.

## Persistencia y recuperación

Cola privada: `.data/relevamientos-inbox/inbox.sqlite3`. Caché privada de fuentes y pedido congelado: `.codex-mobile-bridge/relevamientos/<clave>/` dentro del workspace seleccionado. Ambas están excluidas de Git; no copiarlas a reportes públicos.

La clave combina raíz Drive, carpeta de proyecto y UUID de reunión. El registro del backend (`*.meetings.sqlite3`, junto a su base de chats) reserva un ID determinista de chat y persiste la intención antes de iniciar. Una respuesta HTTP perdida se recupera con la misma clave. Si no puede confirmar si el proveedor arrancó, marca `uncertain` y no repite el pedido a ciegas.

Estados: `waiting`, `queued`, `submitting`, `running`, `completed`, `failed`, `cancelled`, `uncertain`. Una entrega aceptada queda congelada; editar después el foco, las fuentes o la revisión no relanza su análisis. Reprocesar una reunión aceptada todavía no tiene comando implementado y requiere una resolución explícita, sin borrar registros ni cambiar IDs para forzarla.

## Estado real y pasos pendientes

Implementados el contrato, monitor, validación, caché, endpoint idempotente `/meeting-intakes`, apertura de chat, seguimiento y unidad instalable. Las pruebas usan Drive y proveedor de ejecución sintéticos; no acreditan una carga real ni una respuesta real del modelo.

Validación local: **72 pruebas aprobadas** en `tests/test_meeting_inbox.py`, `tests/test_relevamientos.py` y `tests/test_session_management.py`. Cubren carga parcial, integridad, adjuntos, proyectos ambiguos, recuperación de respuestas HTTP perdidas, foco congelado, imágenes y DOCX, persistencia y ausencia de duplicados. También se probaron la reutilización del token OAuth configurado y el bloqueo de cambios en la asociación de un proyecto. Ruff, sintaxis del instalador y `git diff --check` pasaron. No se ensayó todavía un análisis semántico real ni la frontera de herramientas con un proveedor real.

Corrección del diagnóstico anterior: **Batata sí tenía credenciales de Drive**, en el archivo indicado por `GOOGLE_DRIVE_TOKEN_FILE`. El receptor ahora las reutiliza directamente, sin copiarlas a `.env` ni a informes. Se admite un archivo específico mediante `RELEVAMIENTOS_GOOGLE_TOKEN_FILE`. Como alternativa, siguen admitiéndose las variables:

- `RELEVAMIENTOS_GOOGLE_CLIENT_ID`
- `RELEVAMIENTOS_GOOGLE_CLIENT_SECRET`
- `RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN`

El acceso autónomo real fue probado: Google devolvió HTTP 400 `invalid_grant` al renovar ambos tokens locales existentes y HTTP 401 con el access token anterior. El conector del chat sigue funcionando, pero su autorización es independiente. La renovación interactiva con la cuenta abierta en Batata fue bloqueada por Google: la app `codex-access` está en pruebas y la cuenta no está habilitada. La consola de Google Cloud exige además verificación en dos pasos. No se cambiaron contraseñas, MFA, usuarios de prueba ni permisos para eludir ese bloqueo.

El servicio está instalado. Se preparó la carga del endpoint en el runtime DEV real sin sobrescribir sus otras funciones. `scripts/activate_meeting_inbox_after_drain.py` espera a que terminen los chats activos antes de reiniciar DEV, habilita el monitor y deja el estado verificable en `reports/relevamientos-automaticos/activacion.json`. Aunque el proceso monitor quede activo, la prueba real seguirá bloqueada hasta renovar la autorización local de Drive. El worker antiguo bajo demanda permanece separado.

Se creó y verificó la [carpeta de prueba](https://drive.google.com/drive/folders/1iV6qj567t8DSQj1ZeoVphoaRk99l0kAT) en `codex-folder/codex-cli-mobile-bridge/relevamientos`. Está vacía; no contiene entregas ficticias ni marcadores que disparen un análisis.

La primera coincidencia exacta guarda carpeta Drive, nombre y ruta del workspace. Si luego cambia la asociación, bloquea el trabajo en vez de redirigirlo. `LISTO.json.project` debe coincidir con el proyecto y `folder_id` con la carpeta real de la reunión. Nombres como `Patsa` y `patsa` no se consideran iguales automáticamente.

## Operación

Desde la raíz del repositorio:

```sh
.venv/bin/python -m services.relevamientos.inbox doctor
.venv/bin/python -m services.relevamientos.inbox doctor --check-drive
.venv/bin/python -m services.relevamientos.inbox status
.venv/bin/python -m services.relevamientos.inbox once
bash scripts/install_meeting_inbox_service.sh --enable-now
```

`doctor` comprueba configuración; `doctor --check-drive` comprueba renovación OAuth y lectura de la raíz y devuelve código 2 si falla. Ambos ocultan valores secretos. `--enable-now` exige acceso real a Drive y la ruta `/meeting-intakes` en el backend. El activador diferido permite dejar el monitor instalado y en espera de autorización, registrándolo expresamente. La CLI lee `.env` con dotenv sin ejecutarlo como shell. `RELEVAMIENTOS_BRIDGE_URL` configura la conexión interna con DEV; no es un enlace público para el teléfono.

```sh
systemctl --user status codex-meeting-inbox.service
systemctl --user stop codex-meeting-inbox.service
.venv/bin/python -m pytest tests/test_meeting_inbox.py tests/test_relevamientos.py -q
```

Primera prueba real: la carga parcial no inicia trabajo; LISTO completo inicia uno solo; faltar un adjunto o cambiar un hash bloquea; reiniciar o perder la respuesta HTTP no duplica el chat. Verificar también relevancia semántica y aplicación del foco con material autorizado.

Referencia de API consultada: [metadatos File de Google Drive](https://developers.google.com/workspace/drive/api/reference/rest/v3/files). `sha256Checksum` depende de disponibilidad para archivos almacenados; por eso existe la alternativa de descargar y calcular.
