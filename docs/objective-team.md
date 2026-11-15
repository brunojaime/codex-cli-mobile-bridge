# Equipo por objetivos

Entrada: menú de acciones o panel Projects → Equipo por objetivos. Lista de ejecuciones, aceptación de incrementos/historias, actividad por rol y chats en PROD, evidencia UX con commit y hallazgos abiertos/resueltos. Consultar no inicia, cancela ni cambia jobs. Los ciclos legacy siguen en sus chats y no se convierten en objetivos por inferencia.

El monitor lee el estado canónico `~/.local/state/nienfos-objective-team` (override `NIENFOS_OBJECTIVE_STATE` en el router integrado; `--state-root` en el servicio independiente). Sólo expone ejecuciones de proyectos registrados por el backend consultado. No expone prompts, comandos, fuentes ni logs privados. El servicio independiente cachea sólo el registro de proyectos durante 30 segundos para no redescubrir todos los repos por cada miniatura; el estado de ejecución siempre se relee. Capturas raster referenciadas por revisores se restringen al directorio de evidencias y SHA registrado; propuestas UX se restringen al workspace del job y aparecen sin revisión. HTML/SVG no se sirven como imágenes.

`GET /objective-team`, `GET /objective-team/{id}` y `GET /objective-team/{id}/images/{id}`. Sin endpoints de mutación. El avance por historias se deriva de todos sus incrementos aceptados; no implica por sí mismo verificación final. Implementado, verificado e integrado son estados separados; integrado no equivale a desplegado. Un error conserva la última consulta con aviso de desactualización. La fecha de consulta no es el heartbeat del agente.

## Publicación sin interrumpir agentes

El router puede montarse con el backend. Batata usa además `python -m backend.app.objective_team_server --port 8160 --backend-port 8000 --environment prod --web-root RUTA_PROD --dev-web-root RUTA_DEV` para servir las dos webs y la consulta de estado bajo el origen privado ya existente `/app`. Sólo escucha loopback y no carga el scheduler. `/app/objective-team` consulta el registro PROD; `/app/dev/objective-team` el DEV. Ambos observan el mismo coordinador por objetivos; no son dos escritores.

El define `CODEX_OBJECTIVE_TEAM_GATEWAY=https://batata-default-string.tail0302c4.ts.net/app` se usa en web/APK. Sólo se aplica cuando el host del servidor seleccionado coincide y el puerto es uno de los dos canales conocidos; otros servidores usan su `/objective-team`. DEV no ofrece abrir IDs de chat que pertenecen al store PROD. Sin esta configuración, el cliente usa el router del backend.

Mantener el acceso privado de Tailscale. No publicar este monitor mediante Funnel. La actualización del servicio web no reinicia el backend, el coordinador, ni Tailscale. Para volver atrás, retirar el drop-in de esta versión y reiniciar sólo `codex-bridge-prod-web.service`.

## Límites

Se muestran hasta 200 estados, 100 jobs recientes y 60 imágenes por ejecución; la lista avisa si se truncó. La lectura de imágenes no acredita su estética ni pruebas nuevas. Las propuestas aparecen cuando UX devuelve evidencia `kind: screenshot` o `browser` con ruta real dentro de su workspace y SHA de commit; los PNG de revisión aparecen con revisión registrada. No se fabrican propuestas a partir del relato del agente.

El diseño no agrega controles para iniciar/pausar ejecuciones: se conserva el lanzamiento por chat/operador del coordinador. La instalación en un teléfono y recepción de una actualización requieren comprobarse allí; publicar APK no demuestra instalación.

## Vista de trabajo

La ejecución abre Ahora (responsables, propósito, entrega esperada y dependencias), Producto (capacidades), Resultados (trabajos aceptados), Diseño y Atención. Los workspaces con el patrón exacto del coordinador se omiten de Projects y del selector de nuevo chat; los chats y datos internos quedan en Detalle técnico. Las referencias de contexto proceden del handoff persistido: acreditan referencias incluidas, no lectura ni aplicación.

Pendiente de instrumentación: lecturas efectivas, uso de herramientas, costes y exportación OpenTelemetry/MLflow. Esta vista no declara disponer de esas señales.

## Comunicación de producto

Worker independiente: python -m backend.app.team_communicator. Sólo escribe en STATE/communication; lock, timeout 240 segundos, reintento mínimo 180 segundos y límite 24 llamadas por ejecución. Codex read-only, Apps/MCP apagados. Redacta nombre, propósito, tareas, entregas esperadas y capacidades una vez por versión del plan. Estados y contadores se calculan directamente desde el coordinador, sin nuevas llamadas al modelo. No narra cada comando.

Contrato con cobertura completa de tareas y relaciones, texto acotado y sin campos de estado o publicación. Un plan diferente invalida la explicación; la ausencia de texto muestra pendiente, nunca instrucciones técnicas. La validación estructural no certifica la semántica de cada frase: se presentan expectativas y se deriva aceptación del estado canónico. UI: Ahora, Producto, Resultados, Diseño y Atención. Chats y registro técnico opt-in. Sin evidencia de despliegue en el contrato, publicación permanece sin acreditar. OpenTelemetry/MLflow y lecturas/herramientas siguen pendientes.

En Batata, `nienfos-team-communicator.timer` invoca el servicio independiente cada 60 segundos después de finalizar. Código en `~/.local/share/nienfos-communicator`; salida privada en `STATE/communication`. No requiere reiniciar el backend. El timer no genera llamadas si la huella del plan no cambió; los fallos no detienen la ejecución.
