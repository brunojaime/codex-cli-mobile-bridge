# Decisiones sobre bloqueos de recuperación

Los bloqueos que ya no admiten recuperación automática se conectan a `work_questions`, la misma bandeja de Trabajo → Decisiones. No se crea otra cola de tareas ni otro sender.

La reconciliación corre en el scheduler antes de los presupuestos y de la admisión nocturna. Incluye los bloqueos anteriores con política habilitada; excluye una primera diagnosis automática todavía pendiente y las tareas detenidas explícitamente. Una decisión tiene identidad determinista ligada a tarea, revisión y evidencia del fallo. Cambios de estado internos equivalentes no generan otro aviso. La decisión queda obsoleta si la tarea cambia o termina.

Opciones:

- **Comprobar nuevamente sin publicar**: conserva el ID, encargo, adjuntos, base e historial; encola una diagnosis bajo los locks, rama, limpieza, validaciones y verificación Git/DEV oficiales. No publica, no cambia credenciales, no descarta WIP y no reinicia el presupuesto de recuperaciones. Si la diagnosis acredita lo ya entregado, puede completar la tarea. Una validación reparable puede volver al ciclo automático autorizado por la política. Un fallo persistente vuelve a pedir atención.
- **Mantener bloqueado**: conserva el encargo sin lanzar trabajo. Rechazar la decisión también conserva el bloqueo. No genera decisiones repetidas para el mismo incidente.

Una respuesta desactualizada devuelve conflicto. Repetir la misma elección es idempotente. Observaciones se conservan en la decisión; no se interpretan como autorización para publicar ni como comandos.

Cada decisión genera un mensaje explícito del coordinador en un chat estable del proyecto, sin modelo ni job. Su trigger SQL usa el transporte de notificaciones Nienfos ya instalado. Una caída entre el guardado del mensaje y el recibo del ledger no duplica el aviso. Un fallo al guardar un aviso no bloquea otros proyectos y se reintenta; queda anotado estructuralmente en `work_meta`.

Elegir, rechazar o invalidar la decisión cancela el evento push pendiente. Los avisos ya mostrados pueden conservarse en el teléfono; abrir la bandeja muestra el estado vigente. El aviso abre el chat de coordinación e indica Trabajo → Decisiones. No requiere una APK nueva para este recorrido. Se mantienen el opt-in, dispositivos verificados, Firebase separado, retención, recibos y permisos del transporte existente. Persistencia y aceptación de FCM no prueban recepción física.

Validación: `tests/test_work_decisions.py`, regresiones de coordinador/recuperación/hub/historial y push. No se envían avisos de prueba a otros destinatarios ni se modifica ninguna credencial.
