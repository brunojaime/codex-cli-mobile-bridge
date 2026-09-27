# Codex Developer Feedback Web

Paquete web compartido para RD, Chrem y Nienfos Gestión exclusivamente en dev. Se consume como tarball versionado
para que CI no dependa de rutas a otros proyectos ni de una rama flotante.

- Botón flotante con ícono de bug y contador de pendientes.
- Editor a tamaño original (1 píxel CSS por píxel capturado), sin reducir la pantalla. Barra flotante arrastrable con dedo/mouse o flechas del teclado, plegable; lápiz, rectángulo, flecha, deshacer y borrar.
- Admite mouse, dedo y stylus; conserva trazos al cambiar tamaño y al volver desde el comentario.
- Guarda el PNG anotado y metadata de trazos con las coordenadas originales.
- Guarda capturas y recorridos localmente en IndexedDB, sin límite fijo de cantidad y sujeto al espacio disponible del dispositivo y envía el lote sólo al pulsar Enviar.
- Descubre perfiles desde `GET /feedback-workflow-presets`.
- Envía el contrato `codex.developerFeedbackBatch` a `POST /feedback-batches/start-session`.
- No publica automáticamente: `releaseWhenComplete=false` y ambiente explícito.
- Recorrido guiado con voz: micrófono sólo tras pulsar Grabar y aceptar el permiso, capturas cada segundo, omitiendo imágenes consecutivas iguales, al navegar e interactuar, y manuales. Hasta 2 minutos / 120 capturas; se detiene antes si alcanza el presupuesto de almacenamiento.
- La app sigue operable durante el recorrido. Barra movible, detener/cancelar, revisión por tiempo y reproducción de voz. Se detiene al ocultar la pestaña. Las navegaciones que recargan todo el documento requieren finalizar el recorrido.
- El recorrido se guarda como un elemento local `codex.liveFeedback.guidedTrace`; al enviar, cada frame se adjunta como una imagen y el audio completo sólo una vez. No es un archivo MP4.
- Cancelar, detener o desmontar el componente libera el micrófono.
- El dispositivo necesita acceso por Tailscale al Bridge HTTPS.
- No usa credenciales del producto ni incluye parámetros de URL, cookies o tokens en el feedback.
- `data-feedback-private` excluye elementos; contraseñas y OTP se vacían en la copia capturada.
- Revisar cada captura antes de enviarla. Las imágenes externas sin CORS pueden no aparecer.
- Usa la [configuración oficial de html2canvas](https://html2canvas.hertzen.com/configuration)
  para capturar el viewport y excluir elementos privados.

```js
import { mountFeedback } from '@codex/developer-feedback-web';
const unmount = mountFeedback({
  sourceApp: 'rd-gestion-hse',
  sourceDisplayName: 'RD Gestión HSE',
  environment: 'dev',
  allowedOrigins: ['https://rd-dev.nienfos.com'],
  bridgeUrl: 'https://batata-default-string.tail0302c4.ts.net',
});
```

El montaje falla cerrado fuera del origen exacto autorizado y del ambiente dev.
Las apps importan el módulo dinámicamente sólo en ese origen. El permiso de acceso
al Bridge depende de Tailscale; el filtro del cliente controla visibilidad, no es autenticación.
Los workspaces deben estar registrados con el mismo nombre que `sourceApp`.

`npm test` valida aislamiento, almacenamiento, contrato y errores HTTP.
El test Playwright de `test/browser.mjs` comprueba el widget real con transporte
simulado: no inicia ejecuciones de Codex ni envía información de negocio.

Desde 0.4.0: durante el recorrido, Dibujar activa una capa transparente de tamaño original con lápiz, rectángulo y flecha. Navegar guarda las marcas y permite seguir usando la app; la voz no se detiene. Las marcas se incluyen en las imágenes enviadas. Los límites de duración y almacenamiento continúan vigentes; no es video continuo ni MP4.

Desde 0.5.0: la cola migra automáticamente desde localStorage a IndexedDB sin eliminar el origen hasta confirmar el guardado. Nuevo recorrido permite agregar sucesivas grabaciones desde la cola. Guardar no envía nada; los fallos de almacenamiento conservan el borrador abierto. Cada recorrido mantiene su propio audio y secuencia.
