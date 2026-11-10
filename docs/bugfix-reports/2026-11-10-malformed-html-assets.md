# Recursos HTML malformados — corrección para DEV

Estado inicial: rama `dev/bridge-bugfixes-20261107`, HEAD `e2699bc7a1aab9f663e1ef718a5a62d7dbb9d80f`, checkout limpio. Se revisaron [el procedimiento DEV](../automatic-dev-bugfixes.md) y [el resultado anterior](2026-11-08-github-release-pagination.md). La paginación GitHub ya estaba resuelta y no se modificó; tampoco se repitió la corrección de endpoints del visor.

## Cambio acotado

En [_asset](../../frontend/mobile_app/lib/src/services/html_document.dart), el `try` existente ahora incluye la resolución de URI, la comprobación de origen y la decodificación del path. Una referencia que falla durante su interpretación devuelve una cadena vacía y suma una unidad a `unavailableAssets`, sin llegar al cargador ni abortar el documento. Los controles de origen, tipos, solicitudes, bytes, profundidad, timeout, caché y ciclos CSS conservan su orden y valores. No se cambia la CSP ni el comportamiento de enlaces, recursos data o fragmentos.

## Regresión y validación real

Se agregaron ocho casos en [html_document_test.dart](../../frontend/mobile_app/test/html_document_test.dart): dos referencias inválidas en imágenes, hojas de estilo, bloques `style` y atributos `style`.

- `http://[` provoca `FormatException: Missing end ] to match [ in host` al resolver la URI.
- `%FF.png` provoca `FormatException: Invalid UTF-8 byte (at offset 8)` al decodificar el path.
- Cada prueba comprueba además que la referencia realmente lanza `FormatException`, para evitar una regresión basada en una URL que Dart tolere.
- Tras cada recurso inválido, una hoja de estilo y una imagen válidas se siguen cargando. Se conserva el texto y, para CSS inline, la declaración de color. Sólo se solicitan `reports/valid.css` y `reports/valid.png`.
- Se incluye una imagen de red bloqueada: el contador final es exactamente 2 (malformada + red), el cargador no recibe ninguna de esas referencias y se conserva `connect-src 'none'`.

Comandos desde `frontend/mobile_app`, con `CI=true FLUTTER_SKIP_UPDATE_CHECK=true`:

```text
flutter test test/html_document_test.dart --plain-name malformed --reporter expanded
Antes del arreglo: exit 1, 0 aprobadas, 8 fallos.
Cuatro fallos de resolución en _asset y cuatro de decodificación en _asset.

flutter test --no-pub test/html_document_test.dart test/html_file_preview_test.dart --reporter expanded
Después del arreglo: exit 0, 14 aprobadas, All tests passed! (43 segundos).

flutter analyze --no-pub lib/src/services/html_document.dart test/html_document_test.dart test/html_file_preview_test.dart
Exit 0, No issues found! (4.5 segundos).
```

Desde la raíz del checkout:

```text
dart format frontend/mobile_app/lib/src/services/html_document.dart frontend/mobile_app/test/html_document_test.dart
Formatted 2 files (0 changed).
git diff --check
Exit 0, sin errores.
```

La primera ejecución de formato encontró una caché incompleta (`PathNotFoundException` para `flutter_lints-5.0.0/lib/flutter.yaml`). La preparación de Flutter descargó las dependencias y la validación posterior terminó correctamente, sin cambios en el lockfile ni actualizaciones de versiones del proyecto. La comprobación es local mediante pruebas Dart/Flutter; no acredita ejecución en un APK distribuido ni en una WebView Android real.

## Entrega y publicación pendiente

No se hizo push, no se crearon tags ni releases, no se publicó APK y no se modificaron ni reiniciaron servicios PROD o DEV. Esta entrega contiene código móvil: una publicación backend no acredita que la aplicación instalada incorpore el arreglo.

El coordinador debe validar el commit y los hashes, preparar el incremento de versión en `frontend/mobile_app/pubspec.yaml` y seguir `scripts/publish_android_release.sh --channel dev --push`, verificando antes el backend DEV real y los defines del actualizador. No usar el canal predeterminado PROD ni habilitar mock/demo. Verificar después el workflow, el APK DEV y la actualización real. La elección de build y la publicación quedan pendientes del coordinador conforme al alcance autorizado.

Hashes SHA-256 para cotejar el parche respecto del HEAD inicial:

| Archivo | Antes | Después |
| --- | --- | --- |
| `frontend/mobile_app/lib/src/services/html_document.dart` | `8e60a58c7ece87eefa2394db0366f27cc3593671c82963be5e226a2f02dcf450` | `16152ecaa7daaa31a05e3f57ef490ae9b0fe5a762cf786dc9c56ca0386077ffd` |
| `frontend/mobile_app/test/html_document_test.dart` | `4694902a6b1435eafb50b9a969b785e43a53a5fd8771edce6fdc7c91c9b81d7a` | `8c7af40ade722ecebc963a6b121779e9aacbfa7434e9cd2019a3bb184903527b` |
