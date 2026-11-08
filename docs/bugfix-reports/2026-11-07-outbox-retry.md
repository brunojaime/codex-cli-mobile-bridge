# Espera de reintentos por conversación — DEV

Encargo: impedir reintentos automáticos prematuros de dos conversaciones con fallos transitorios. Rama: `dev/bridge-bugfixes-20261107`.

Estado inicial comprobado: checkout limpio, HEAD `7c6b67a04b1e9932d4041a639310dc1e3485ae0b`, coincidente con el recibo previo aportado. Esa entrega corresponde al trabajo anterior del visor. El defecto de la cola seguía presente; no se repitieron cambios del visor. El recibo anterior no acredita la entrega móvil de esta corrección.

## Cambio

[MessageOutbox](../../frontend/mobile_app/lib/src/services/message_outbox.dart) mantiene un temporizador por conversación y todo bombeo respeta esa espera. Al vencer se libera sólo esa conversación. El reintento manual explícito cancela su espera tras consultar el recibo. El cierre cancela todos los temporizadores. Se conservan selección de cabeceras, IDs estables y consultas de recibos antes de subir mensajes.

## Evidencia de validación

[Regresión](../../frontend/mobile_app/test/message_outbox_test.dart): reloj virtual con fallos transitorios controlados. A falla en t=0 y B en t=2; encolados adicionales y la entrega de C en t=4 no reactivan A ni B. A reintenta en t=5 y B en t=7, con comprobaciones un milisegundo antes de cada vencimiento. Al recuperar conectividad, los cinco mensajes se aceptan una sola vez y los mensajes de cada conversación conservan su orden.

La regresión ejecutada contra el código previo falló: B ya estaba `accepted` cuando aún debía estar `waiting_connection`, por haber consumido prematuramente los fallos simulados. El número de fallos está acotado para que una tormenta produzca una aserción fallida sin bloquear la prueba.

Comandos ejecutados desde `frontend/mobile_app` tras la corrección:

- `flutter test --no-pub test/message_outbox_test.dart`: 9 pruebas aprobadas; incluye recuperación por recibo sin segunda subida y persistencia de audio tras borrar el original.
- `flutter test --no-pub test/outbox_composer_test.dart`: 4 pruebas aprobadas.
- `flutter analyze --no-pub lib/src/services/message_outbox.dart test/message_outbox_test.dart`: sin incidencias.
- `git diff --check`: sin errores.

## Publicación pendiente

No se reiniciaron servicios, no se publicaron releases y no se modificó producción. Conforme a `docs/automatic-dev-bugfixes.md`, el coordinador debe comprobar el commit y el estado DEV y ejecutar la publicación que corresponda.

Este cambio es Flutter: publicar backend DEV no lo distribuye. Queda pendiente generar y verificar una entrega móvil DEV mediante `scripts/publish_android_release.sh --channel dev`, con incremento de versión y configuración real de backend y actualizador. No se cambió la versión ni se creó un tag como parte de esta ejecución. La evidencia de entrega móvil deberá incluir tag, workflow y APK correspondientes; no existe aún para este parche.
