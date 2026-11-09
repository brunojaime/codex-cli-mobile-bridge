# Paginación de releases GitHub — DEV

Encargo limitado al backend, en la rama `dev/bridge-bugfixes-20261107` y el checkout separado autorizado. Estado inicial: HEAD `941aba7e1cf19c0a2db3718e4d7a33c0e87c1963`, sin cambios pendientes. Se revisó el informe anterior de reintentos de la cola móvil; ese cambio ya estaba aplicado y no se repitió. El recibo Android aportado corresponde a esa entrega previa, no a este parche.

## Cambio

[HttpGitHubReleaseClient.list_releases](../../backend/app/application/services/app_update_service.py) acumula las releases y sigue el enlace HTTP `Link` con relación `next` hasta que no existe otra página. Cada petición conserva headers, token y timeout. Cada página valida el estado HTTP y el tipo lista antes de incorporar sus releases. Un error HTTP posterior se propaga como `GitHubReleaseError`, sin devolver resultados parciales.

No se modificaron los filtros de canal, paquete, tags o assets ni la configuración de entornos. La búsqueda PROD de las pruebas es un caso simulado: no implica acceso ni publicación en producción.

## Regresiones y validación

[Pruebas](../../tests/test_app_updates.py) con `httpx.MockTransport`, sin red:

- Primera página DEV y segunda página PROD: tanto `check_update` como `resolve_apk_asset` consultan ambas páginas y encuentran la actualización y su APK. Se verifican orden de peticiones, autenticación, Accept, versión de API y timeout en ambas páginas. Un enlace `prev` en la última página no prolonga el recorrido.
- Respuesta sin `next`: una sola petición y conservación del funcionamiento sin token.
- Segunda página con HTTP 503: `GitHubReleaseError` conserva como causa `httpx.HTTPStatusError`.

Antes de cambiar el método, la ejecución dirigida (`-k http_release_pagination`) produjo **3 fallos y 1 aprobación**: actualización ausente, APK rechazado y error posterior ignorado. Los tres fallos reproducen el defecto descrito.

Comandos ejecutados con el Python del entorno existente del proyecto, desde este checkout:

- `python -m pytest tests/test_app_updates.py -q`: **68 aprobadas** en 43 segundos; 464 advertencias de deprecación de eventos FastAPI, sin fallos.
- `python -m ruff check backend/app/application/services/app_update_service.py tests/test_app_updates.py`: sin incidencias.
- `git diff --check`: sin errores.

## Entrega al coordinador

No se publicaron releases, no se hizo push ni se reiniciaron servicios. No se modificó producción. Conforme a [automatic-dev-bugfixes.md](../automatic-dev-bugfixes.md), la publicación DEV queda exclusivamente a cargo del coordinador: verificar Git y los hashes, esperar trabajos y mensajes aceptados, aplicar drain, activar el parche y comprobar revisión servida y HTTP real. Este cambio es backend y no requiere un APK nuevo.

No hay evidencia de publicación de este parche todavía. Las pruebas no consultaron GitHub ni verificaron un incidente real en repositorios privados.
