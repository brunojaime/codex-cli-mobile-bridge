# Deploys por proyecto y por workspace

El panel izquierdo ofrece **Deploys** y **Notificaciones** dentro de cada proyecto, antes de sus conversaciones. El menú del proyecto ofrece los mismos accesos. El menú superior incluye **Deploys · Workspace**, con búsqueda por nombre o ruta. El backlog conserva su acceso global.

`GET /work/deployments` devuelve todos los proyectos descubiertos y `GET /work/deployments?workspace_path=...` sólo el proyecto exacto autorizado por el listado de workspaces. Ambos admiten el prefijo `/api/v1`. Siguen el coordinador central configurado con `WORK_HUB_URL`.

Siempre devuelve Dev, QA y Pro, con publicación vigente, último intento e historial disponible. La ausencia de registro muestra una raya. Un error de lectura se muestra como error, no como ausencia confirmada. Una actualización fallida conserva la consulta anterior y la identifica como tal.

## Evidencia y comparación

Fuentes automáticas: comprobantes de tareas completadas del coordinador y estados guardados de previews web. Los previews se presentan como Dev. Un plan de preview o un build no acreditan un deploy. El historial de previews contiene el estado que conserva ese servicio; no reconstruye publicaciones que ese servicio ya sobrescribió.

Los publicadores externos pueden registrar sus comprobantes en `<proyecto>/.codex/deployments.json`. No se inspeccionan archivos `.env`, tokens, respaldos ni logs de publicación. No se consulta GitHub o Cloudflare en vivo. Un deploy externo que no emite comprobante figura como **sin deploy registrado**, aunque exista fuera del Bridge.

La comparación utiliza los campos compartidos entre publicaciones: commit completo y/o release. Si cualquiera de las identidades compartidas difiere, indica releases diferentes. Si faltan identidades comparables, indica trazabilidad insuficiente. Dos ambientes iguales con un tercero ausente nunca se presentan como tres ambientes sincronizados. Un error de lectura impide afirmar igualdad.

Un intento fallido/en curso no reemplaza la última publicación exitosa. Una desactivación o vencimiento posteriores sí la retiran. La fecha se muestra en la zona horaria local del cliente. Publicado significa comprobante de publicación, no disponibilidad verificada en este instante.

## Emitir comprobantes desde un publicador

Ejecutar después de la publicación real, usando el Python del Bridge:

```bash
.venv/bin/python scripts/record_project_deployment.py \
  --project /ruta/al/proyecto \
  --id deploy-123-publicado \
  --environment prod \
  --status published \
  --deployed-at 2026-11-06T15:30:00Z \
  --release v1.2.3 \
  --commit 0123456789abcdef0123456789abcdef01234567
```

Los valores del ejemplo son ilustrativos. Reemplazarlos por el ID, fecha e identidad reales. Este comando sólo registra evidencia: no publica, verifica ni promociona código. `--environment` acepta `dev`, `qa`, `prod`; `--status` acepta `published`, `deploying`, `failed`, `disabled`, `expired`. Release y commit son opcionales: omitirlos deja explícita la falta de trazabilidad. La fecha debe incluir zona horaria.

Cada evento necesita un ID único. Repetir el mismo comprobante con el mismo ID y fecha es idempotente; un contenido distinto con ese ID se rechaza. El escritor usa lock, reemplazo atómico y conserva hasta 1000 eventos. Para importar despliegues anteriores, usar su fecha real. No usar la fecha de importación como fecha de publicación.

Formato:

```json
{
  "version": 1,
  "deployments": [
    {
      "id": "deploy-123-publicado",
      "environment": "prod",
      "status": "published",
      "deployed_at": "2026-11-06T15:30:00Z",
      "release": "v1.2.3",
      "commit": "0123456789abcdef0123456789abcdef01234567"
    }
  ]
}
```

## Notificaciones

El acceso del proyecto lleva su nombre y usa una conversación de ese mismo proyecto para resolver el logo. No reutiliza una conversación de otro proyecto. Sin conversación cargada disponible, lo informa y no ofrece una edición de logo sin destino. La activación y prueba push siguen siendo configuración del teléfono y se identifican como aplicables a todos los proyectos. El menú global abre únicamente esa configuración general.

## Validación

```bash
.venv/bin/pytest tests/test_project_deployments.py tests/test_work_hub.py tests/test_web_preview_deploy_service.py -q
cd frontend/mobile_app
flutter test test/deployments_screen_test.dart test/chat_screen_overflow_test.dart test/notification_settings_screen_test.dart
```

Para regenerar capturas del widget real con fixtures de prueba, sin construir un APK ni habilitar datos de demostración en producción:

```bash
cd frontend/mobile_app
CAPTURE_DEPLOYS=1 flutter test test/deployments_screen_test.dart
```

Las capturas se guardan en `reports/project-deployments/screenshots`. La captura opcional usa DejaVu Sans del sistema y Material Icons del bundle de Flutter.

## Sincronización de ambientes existentes (06/11/2026)

El backend combina los comprobantes anteriores con `.data/project-deployments/index.json`, producido por `scripts/sync_project_deployments.py`. El colector consulta únicamente metadatos de Cloudflare Workers/Pages, sin desplegar apps, modificar DNS, consultar datos de clientes ni copiar credenciales a su índice. Las fechas provienen de los despliegues del proveedor, no de la fecha del relevamiento.

La asociación cruza manifiestos, nombres exactos, dominio personalizado propietario y repositorio común de los worktrees. La etiqueta técnica `environment=production` de Cloudflare no equivale al ambiente comercial Pro: también aparece en workers Dev/QA. Se evita asociar aplicaciones embebidas de otro proyecto al repositorio Bridge. Las plantillas o ramas sin publicación no crean registros.

Los identificadores de versión de Cloudflare quedan en el ID del comprobante, no como release comparable entre workers diferentes. El commit sólo se incorpora cuando existe una vinculación explícita con la versión realmente desplegada (por ejemplo, un comprobante `sourceVersionVerified` que coincide exactamente con el worker y version ID). Diferencias conocidas entre QA/Pro se informan aunque falte la identidad de Dev.

El índice conserva registros previos ante fallos y señala desactualización al superar una hora. La sincronización se programa cada diez minutos; una sesión del CLI existente puede renovarse mediante su mecanismo normal y sin login interactivo. Una falla de acceso conserva el índice anterior y requiere revisar el servicio. No se presenta una configuración antigua como despliegue vigente.
