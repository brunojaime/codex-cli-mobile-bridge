# Actividad del agente en el chat

Cada respuesta puede incluir un historial de avances públicos, pasos de plan y
herramientas. Se abre durante la ejecución y se contrae al terminar, salvo que
la persona haya elegido una presentación. Las seis actividades más recientes
aparecen primero; «Ver pasos anteriores» permite consultar todo el historial.
Cada herramienta conserva su identidad al pasar de ejecución a resultado.
Los comandos, archivos afectados y resultados de texto se consultan desde la fila.

Los eventos se capturan en LocalExecutionProvider (Codex app-server, Codex exec
y Claude Code), viajan como `activities` en JobResponse/WebSocket y como
`job_activities` en cada ChatMessageResponse. SQLite migra automáticamente con
una columna `activities_json`, vacía para trabajos anteriores. El historial no
se reconstruye retroactivamente. El proveedor Lambda conserva su contrato anterior.
La autorización de lectura sigue siendo la de los chats y trabajos existentes.

Sólo se incluyen avances públicos y herramientas. Los bloques de razonamiento
privado no se convierten en actividades. El detalle de cada entrada se limita
a 16.000 caracteres y los avances a 12.000. Si una herramienta no informa su
resultado antes de terminar el trabajo, aparece como «Sin resultado confirmado».
Una cancelación o un fallo interrumpen los pasos pendientes sin atribuirles éxito.

## Verificación local

- Backend: pruebas de eventos de Codex y Claude, actualizaciones sin duplicados,
  snapshots independientes, resultados inciertos, planes y persistencia SQLite
  después de reabrir la base. Regresión de sesiones e historial: 77 pruebas.
- Flutter: actividad en vivo, expansión de detalles, historial anterior,
  teclado, estados fallidos/inciertos, refresco y eventos atrasados: 16 pruebas. Capturas
  de widgets reales a 320, 390 y 1280 px con texto ampliado 1,25 veces.
- Compilación web debug correcta. El dry run de Wasm informa incompatibilidades
  preexistentes de flutter_tts; la compilación JavaScript termina correctamente.
- Las capturas usan fixtures exclusivamente en tests. No prueban una sesión
  real de Codex/Claude en la app publicada ni la recepción en un teléfono.
  Actualización local: frontend publicado en los cuatro accesos de Lenovo y backend
  con historial completo en la instancia de revisión local; no se publicó APK.

Comandos desde la raíz:

```sh
uv run --group dev pytest tests/test_agent_activity.py tests/test_claude_bridge.py tests/test_session_management.py tests/test_session_listing.py tests/test_local_provider_app_server.py -q
cd frontend/mobile_app
flutter test test/agent_activity_timeline_test.dart test/chat_controller_streaming_response_test.dart test/chat_controller_run_history_test.dart test/chat_controller_initialize_test.dart test/chat_controller_active_job_summary_test.dart
flutter build web --debug --no-pub
```

Los accesos de Lenovo DEV (5178), Lenovo PROD (5179), Batata DEV (5188) y
Batata PROD (5189) comparten el mismo build, con `bridge-config.json` separado
para conservar el backend y canal de cada uno. La instancia Actividad (5180)
usa un backend real local en 8011 con historial separado. Los servidores
sin eventos estructurados muestran y acumulan las actualizaciones de estado
que entregan; no se reconstruyen comandos ni salidas ausentes.

La publicación de assets conserva backups y no reinicia los trabajos activos.
Repetirla con `scripts/publish_local_web_fronts.py --build-dir RUTA_BUILD`.

El compositor conserva el envío mientras otro turno está activo y muestra
cuántos están en curso o en cola. Se verificó con Codex real: el segundo envío
fue aceptado en 0,08 s mientras el primero seguía ejecutándose; ambos
terminaron correctamente. Esto es una cola por conversación, no entrega de
correcciones al turno nativo en curso (`turn/steer`).

La evidencia visual y el delta de criterios se registran en
[agent-activity-review.json](agent-activity-review.json).
