# Aplicación de control Behringer XR18 - Plan de validación y testeo

## Objetivo

Construir una aplicación móvil capaz de controlar una consola Behringer XR18/X-Air
por Wi-Fi o Ethernet, con un camino claro hacia una superficie de control similar
a la app oficial X AIR: faders, mutes, buses, mezclas de monitoreo, EQ, dinámica,
FX, escenas, ruteo y feedback de estado.

Este documento define cómo validar la idea antes y durante la implementación. La
XR18 es hardware real: el proyecto no queda probado hasta que funcione contra una
consola física en condiciones de red parecidas a las de uso real.

## Proyecto destino

La implementación no debe hacerse dentro de este repositorio. Debe crearse un
proyecto GitHub nuevo, como hijo de la carpeta local de proyectos:

```text
/home/batata/Projects/<nuevo-proyecto-xr18>
```

Este repositorio actual solo contiene el plan y la documentación de referencia.
El proyecto nuevo debe incluir su propio `README.md`, estructura Flutter,
configuración Android, tests y flujo de release APK.

Nombre sugerido para el nuevo proyecto:

```text
xr18-mobile-control
```

El proyecto debe nacer con integración nativa del wrapper reutilizable de Codex
Developer Feedback. No debe copiar código del template dentro de la app: debe
depender del paquete Flutter reutilizable y quedar preparado para heredar futuras
mejoras actualizando el `ref`/tag de esa dependencia.

Valores sugeridos:

```text
sourceApp: xr18-mobile-control
sourceDisplayName: XR18 Mobile Control
```

## Decisión de discovery y conexión

El MVP debe tener un botón visible de búsqueda, por ejemplo `Buscar XR18`, pero
esa búsqueda no debe interpretarse como búsqueda de redes Wi-Fi cercanas.

Comportamiento esperado:

- El usuario conecta el teléfono al Wi-Fi correcto desde Android Settings.
- Ese Wi-Fi puede ser el access point interno de la XR18 o un router externo.
- La app busca consolas XR18/X-Air dentro de la red actual.
- Si discovery no encuentra la consola, la app ofrece conexión por IP manual.
- La conexión por IP manual es obligatoria en el MVP porque es el fallback más
  confiable en routers con broadcast limitado o discovery bloqueado.

Fuera de alcance del MVP:

- Escanear redes Wi-Fi cercanas desde la app.
- Cambiar la red Wi-Fi del teléfono desde la app.
- Pedir permisos Android de ubicación solo para listar redes Wi-Fi.

## Supuestos actuales

- Consola objetivo: Behringer XR18, familia X-Air.
- Transporte de control: mensajes compatibles con OSC sobre UDP.
- Puerto de control típico de la consola: UDP `10024`.
- La app y la consola deben estar en la misma red IP.
- La app debe funcionar con el access point interno de la XR18, con router Wi-Fi
  externo y con la XR18 conectada por Ethernet al router.
- La app debe mantener abierto un socket UDP estable para que las respuestas
  vuelvan al mismo puerto de origen.
- La app debe enviar `/xremote` periódicamente mientras esté conectada para
  mantener activos los updates remotos.
- El protocolo debe tratarse como una interfaz práctica pero no como un SDK
  público estable; todo comportamiento importante se valida en firmware real.

## Fuera de alcance del primer prototipo

- Reemplazar por completo la app oficial X AIR desde el día uno.
- Soportar todos los modelos X-Air antes de estabilizar XR18.
- Actualizar firmware o modificar firmware.
- Control por internet público.
- Transporte de audio. La app controla parámetros; no transmite audio.
- Control de REAPER/Linux o grabación multipista. Eso queda para una fase
  separada.

## Integración Codex Developer Feedback

La app debe incorporar desde el inicio el paquete reutilizable:

```yaml
dependencies:
  codex_developer_feedback_template:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_developer_feedback_template
      ref: codex-developer-feedback-template-v0.2.1
```

Reglas:

- Usar dependencia Git con `ref` explícito.
- No usar dependencia local `path:` salvo para pruebas locales temporales.
- No duplicar lógica de captura de screenshot, cola, audio, selección, batch ni
  envío al Bridge.
- La app solo configura el wrapper: `enabled`, `sourceApp`,
  `sourceDisplayName`, `bridgeUrl`, `navigatorKey` y `scaffoldMessengerKey`.
- `bridgeUrl` debe venir de configuración o `dart-define`, no hardcodeado para
  un entorno único.
- Futuras actualizaciones del wrapper deben entrar cambiando el tag/ref de la
  dependencia y reconstruyendo la app.

Configuración esperada:

```text
CODEX_FEEDBACK_SOURCE_APP=xr18-mobile-control
CODEX_FEEDBACK_SOURCE_NAME=XR18 Mobile Control
CODEX_FEEDBACK_BRIDGE_URL=<url-del-codex-mobile-bridge>
```

Validación mínima:

- `flutter pub get` resuelve la dependencia.
- `flutter analyze` no reporta errores.
- `flutter test` incluye un test que confirma que el root de la app está envuelto
  por `DeveloperFeedbackTemplate` o `CodexDeveloperFeedbackTemplate`.
- El README explica cómo habilitar/deshabilitar feedback y cómo pasar
  `bridgeUrl`.
- Queda documentado que el Bridge debe mapear:

```text
sourceApp: xr18-mobile-control
workspace: /home/batata/Projects/xr18-mobile-control
```

## Hardware y software necesarios

- Behringer XR18 con firmware conocido.
- Teléfono o tablet para la app nueva.
- Notebook en la misma red para capturas y herramientas de debug.
- Router Wi-Fi externo, preferentemente dual-band, con aislamiento de clientes
  desactivado.
- Cable Ethernet desde XR18 al router para el setup recomendado en vivo.
- Segundo teléfono/tablet opcional con la app oficial X AIR para comparar.
- Herramienta OSC opcional:
  - `XAir_Command` de X-Air Utilities.
  - `oscsend`/`oscdump` de `liblo-utils`.
  - Harness UDP/OSC propio para pruebas.
- Wireshark o `tcpdump` para validar paquetes UDP.

## Formas de conexión a validar

### Modo A: access point interno de la XR18

Usar este modo como baseline y fallback.

Checklist:

- XR18 configurada en modo access point.
- Teléfono conectado directamente a la red Wi-Fi de la XR18.
- App puede descubrir la consola o conectar por IP manual.
- App puede leer identidad/estado de la consola.
- App puede mover un fader de prueba y recibir feedback.
- App se recupera después de bloquear/desbloquear la pantalla del teléfono.

Riesgo:

- El access point interno suele ser la opción menos robusta para vivo. Debe
  funcionar, pero el setup recomendado debe ser con router externo.

### Modo B: XR18 por Ethernet a router externo

Este debe ser el setup recomendado para uso real.

Checklist:

- XR18 conectada al router por Ethernet.
- Teléfono conectado al Wi-Fi del router.
- Router con aislamiento de clientes desactivado.
- XR18 con lease DHCP estable o IP fija.
- App puede descubrir la consola o conectar por IP manual.
- App permanece conectada al menos 60 minutos.
- No hay pérdidas visibles de control durante uso normal.

Criterio de aceptación:

- Este modo debe estar estable antes de invertir fuerte en UI avanzada.

### Modo C: XR18 como cliente Wi-Fi de un router externo

Usar si no hay Ethernet disponible.

Checklist:

- XR18 conectada como cliente a una red Wi-Fi existente.
- Teléfono conectado a la misma red.
- App conecta y controla parámetros básicos.
- App reconecta después de apagar y prender la consola.
- App muestra estado claro de desconectado/reconectando cuando cae el Wi-Fi.

Riesgo:

- La confiabilidad depende mucho de las condiciones de radiofrecuencia.

## Validación de protocolo

### Alcance UDP básico

1. Poner notebook y XR18 en la misma red.
2. Confirmar la IP de la XR18 desde la tabla DHCP del router o desde la consola.
3. Desde la notebook, validar alcance IP:

```bash
ping <ip-xr18>
```

4. Confirmar tráfico UDP durante el uso de la app oficial:

```bash
sudo tcpdump -i any host <ip-xr18> and udp port 10024
```

Resultado esperado:

- Hay paquetes UDP entre el cliente y la XR18 en el puerto `10024`.
- Las respuestas vuelven al puerto de origen del cliente.

### Identidad OSC y sesión remota

Objetivos de validación:

- Enviar una consulta de identidad/estado.
- Recibir una respuesta válida.
- Activar modo de updates remotos.
- Mantener la sesión viva con `/xremote`.

Notas de implementación:

- La app debe abrir un socket UDP y reutilizarlo para todo el tráfico de control.
- No conviene enviar desde un puerto y escuchar en otro, salvo que se implemente
  explícitamente un bridge de protocolo.
- Enviar `/xremote` con un timer mientras la sesión esté activa. Un intervalo
  práctico es cada 8 segundos.
- Detener el timer cuando la app se desconecta o entra en estado inactivo total.

Criterio de aceptación:

- La app conecta, identifica la consola, mantiene updates remotos y recibe
  cambios hechos desde la consola física o desde la app oficial.

### Prueba mínima segura de control

Usar un canal sin señal, muteado o ruteado de forma segura antes de probar con
audio real.

Secuencia:

1. Guardar/exportar la escena actual antes de probar.
2. Elegir el canal `01`.
3. Confirmar que el canal está muteado o no puede generar un pico de audio.
4. Leer el valor actual del fader del canal.
5. Setear el fader del canal `01` a un valor conocido, por ejemplo `0.50`.
6. Confirmar que la app oficial X AIR muestra el mismo valor.
7. Mover el fader desde la app oficial.
8. Confirmar que la app nueva recibe el cambio.
9. Restaurar el valor original.

Dirección OSC típica para el fader principal del canal 1:

```text
/ch/01/mix/fader
```

Rango típico normalizado:

```text
0.0 a 1.0
```

Criterio de aceptación:

- El valor enviado por la app nueva aparece en X AIR.
- El valor cambiado desde X AIR aparece en la app nueva.
- No se modifican canales, buses ni ruteos inesperados.

## Inventario de funcionalidades

Las funcionalidades deben validarse e implementarse por fases.

### Fase 1: conexión y mixer básico

- Conexión por IP manual.
- Botón `Buscar XR18` para discovery en la red actual.
- Mensaje claro si el teléfono no está en la misma red que la consola.
- Fallback obligatorio por IP manual.
- Identidad/estado de consola.
- Keepalive con `/xremote`.
- Nombres de canales.
- Faders de canales.
- Mute de canales.
- Fader Main LR.
- Mute Main LR.
- Sincronización básica de estado.
- Reconexión después de pérdida de Wi-Fi.

Criterio de salida:

- El usuario puede conectar a la XR18 y controlar faders/mutes principales de
  forma confiable.

### Fase 2: buses y mezclas de monitoreo

- Selección de bus 1-6.
- Nivel de envío por canal hacia el bus seleccionado.
- Mute de envío donde aplique.
- Faders master de buses.
- Nombres de buses.
- Visualización y edición de pre/post send.
- Separación clara entre Main LR y mezcla de bus.

Criterio de salida:

- Un músico puede controlar su mezcla de monitoreo sin tocar accidentalmente la
  mezcla principal.

### Fase 3: detalle de canal

- Ganancia/trim donde aplique.
- Estado de phantom power con toggle protegido.
- Polaridad.
- Pan/balance.
- Low cut.
- Gate.
- Compresor.
- EQ de 4 bandas.
- Estado de link de canales.
- Etiquetas de fuente de entrada.

Criterio de salida:

- Un operador puede ajustar los parámetros comunes de procesamiento de canal y
  ver los cambios reflejados en X AIR.

### Fase 4: FX y retornos

- Niveles de envío a FX.
- Faders de retornos FX.
- Mute de retornos FX.
- Tipo/nombre de slot FX.
- Parámetros principales de FX.
- Bypass donde aplique.

Criterio de salida:

- Flujos básicos de reverb/delay pueden controlarse sin abrir la app oficial.

### Fase 5: escenas, snapshots y presets

- Leer lista de escenas/snapshots donde el protocolo lo permita.
- Guardar estado actual.
- Cargar escena seleccionada con confirmación.
- Exportar/importar backup de escena si el soporte está confirmado.
- Proteger operaciones destructivas con confirmación explícita.

Criterio de salida:

- El operador puede recuperar estados de show con confirmación clara del destino.

### Fase 6: ruteo y ajustes avanzados

- Ruteo de entradas.
- Ruteo USB donde aplique.
- Aux/returns.
- DCA/mute groups.
- Configuración de fuente de medidores.
- Visualización de red.
- Visualización de firmware/versión.

Criterio de salida:

- Los flujos avanzados están disponibles, pero toda operación riesgosa queda
  protegida y testeada primero en consola fuera de vivo.

## Validación de experiencia de app

### Estados obligatorios

- No conectada.
- Buscando.
- Entrada manual de IP.
- Conectando.
- Conectada.
- Reconectando.
- Error de conexión.
- Consola ocupada o sin respuesta.
- Modo lectura/seguridad.

### Guardas de seguridad obligatorias

- Confirmación antes de cargar escenas.
- Confirmación antes de cambiar ruteo.
- Confirmación antes de cambiar phantom power.
- Contexto visible de bus/main mix todo el tiempo.
- Modo músico opcional bloqueado a un solo bus.
- Modo operador opcional con control completo.
- Acción de pánico para desconectar sin enviar más cambios.

### Feedback obligatorio

- Los faders deben moverse localmente de inmediato, pero reconciliarse con la
  respuesta real de la consola.
- Si la consola rechaza o no confirma un cambio, la UI debe volver a mostrar el
  valor real de la consola.
- Los medidores deben diferenciarse visualmente de la posición de fader.
- La salud de conexión debe ser visible sin tapar controles críticos.

## Matriz de pruebas

| Área | Prueba | Resultado esperado |
| --- | --- | --- |
| Descubrimiento | `Buscar XR18` encuentra consola en LAN actual | Aparece consola con nombre/IP |
| Discovery bloqueado | Router no permite broadcast/discovery | App permite IP manual |
| Red incorrecta | Teléfono en otro Wi-Fi | App explica que debe estar en la misma red |
| IP manual | Usuario ingresa IP de XR18 | App conecta sin discovery |
| Sesión UDP | App envía y recibe en mismo socket | Respuestas recibidas de forma confiable |
| Keepalive | `/xremote` enviado periódicamente | Updates remotos continúan activos |
| Fader write | Mover fader de canal 1 | XR18 y X AIR reflejan el valor |
| Fader readback | Mover fader en X AIR | App nueva actualiza el valor |
| Mute write | Toggle de mute | XR18 y X AIR reflejan el mute |
| Sends a bus | Ajustar envío canal -> bus 1 | Cambia el bus correcto |
| Contexto main/bus | Cambiar entre LR y bus | No hay control cruzado accidental |
| Reconexión | Apagar/prender Wi-Fi | App reconecta y refresca estado |
| Multi-cliente | X AIR y app nueva conectadas | Estado coherente en ambas |
| Bloqueo pantalla | Bloquear 2 minutos | App restaura sesión limpiamente |
| IP incorrecta | Conectar a IP inválida | Error claro, sin crash |
| Red débil | Prueba en borde de cobertura | App degrada sin bloquearse |
| Duración | Sesión de 60 minutos | Sin loops, fugas ni desconexiones repetidas |
| Escena | Cargar escena de prueba | Confirmación y refresh de estado |
| Seguridad | Phantom/ruteo | Confirmación explícita |

## Procedimiento de prueba en campo

### Antes de probar

1. Anotar versión de firmware de la consola.
2. Guardar/exportar la escena actual.
3. Documentar o fotografiar ruteos críticos.
4. Conectar XR18 al router recomendado por Ethernet.
5. Conectar teléfono y notebook a la misma red.
6. Confirmar que la app oficial X AIR funciona primero.
7. Iniciar captura de paquetes desde la notebook.

### Smoke test

1. Abrir la app nueva.
2. Conectar por IP manual.
3. Confirmar identidad de la consola.
4. Confirmar keepalive `/xremote`.
5. Leer nombres de canales.
6. Mover un fader de canal muteado.
7. Alternar mute de un canal seguro.
8. Mover un envío a bus seguro.
9. Desconectar y reconectar.
10. Restaurar valores originales.

### Test de estabilidad

1. Mantener la app conectada 60 minutos.
2. Mover faders cada 5 minutos.
3. Mandar la app a background y traerla a foreground.
4. Bloquear y desbloquear el teléfono.
5. Caminar hasta el borde de cobertura esperada.
6. Confirmar que no hay tormenta de comandos al reconectar.
7. Confirmar que el estado final de consola coincide con la app.

### Test multi-cliente

1. Conectar app oficial X AIR.
2. Conectar app nueva.
3. Mover fader en X AIR.
4. Confirmar update en app nueva.
5. Mover fader en app nueva.
6. Confirmar update en X AIR.
7. Repetir con sends a bus y mutes.

Criterio de aceptación:

- Ambos clientes permanecen coherentes.
- La app nueva no asume que su estado local es autoritativo sin confirmación de
  la consola.

## Estrategia de tests automatizados

### Unit tests

- Encoding de mensajes OSC.
- Decoding de mensajes OSC.
- Builders de direcciones para canales, buses, FX y Main LR.
- Normalización y clamp de valores.
- Debounce/throttle durante arrastre de faders.
- Máquina de estados de reconexión.
- Timer de keepalive.

### Integración sin hardware

- Servidor UDP falso que simule XR18.
- Respuestas simuladas de `/xremote`.
- Cambios simulados de fader/mute.
- Timeout/sin respuesta.
- Paquete OSC malformado.
- Reconexión después de cerrar socket.

### Hardware-in-the-loop

- XR18 real conectada al router.
- Harness enviando comandos conocidos.
- App corriendo contra la consola.
- Captura de paquetes comparada contra direcciones OSC esperadas.
- Estado final de consola comparado contra valores esperados.

## Modelo de datos recomendado

La app debe separar estado de mixer y estado de UI.

Conceptos sugeridos:

- `MixerConnection`: IP, puerto, socket, estado, último response time.
- `MixerIdentity`: modelo, firmware, nombre, dirección.
- `ChannelStrip`: id, nombre, color, fader, mute, pan, resumen de procesamiento.
- `BusStrip`: id, nombre, fader, mute.
- `SendLevel`: channel id, bus id, level, modo pre/post.
- `MainMix`: fader LR, mute LR.
- `SceneSummary`: id/nombre/fecha si está disponible.
- `PendingChange`: address, valor deseado, timestamp, política de retry/rollback.

Reglas:

- Las escrituras de UI crean cambios pendientes.
- Las respuestas de consola actualizan el estado canónico.
- Los cambios pendientes expiran si no se confirman.
- El estado canónico gana sobre UI local vieja.

## Objetivos de performance

- El arrastre de fader debe sentirse inmediato en el dispositivo.
- Latencia objetivo de escritura: menos de 100 ms en red local sana.
- Feedback objetivo de estado: menos de 250 ms en red local sana.
- Detección de desconexión: menos de 5 segundos después de respuestas perdidas.
- Recuperación: menos de 10 segundos después de volver la red.
- Sin CPU alta sostenida en idle.
- Sin crecimiento ilimitado de cola de paquetes con red mala.

## Manejo de fallas

### Consola no encontrada

- Ofrecer entrada manual de IP.
- Mostrar última IP conocida.
- Indicar que teléfono y consola deben estar en la misma red.

### No llegan respuestas UDP

- Confirmar socket único para envío/recepción.
- Revisar VPN, firewall o comportamiento de red privada del teléfono.
- Revisar aislamiento de clientes en el router.
- Revisar captura de paquetes desde notebook.

### Valores no coinciden con X AIR

- Confirmar dirección OSC.
- Confirmar contexto main/bus seleccionado.
- Confirmar rango y tipo de valor.
- Confirmar si links de canales o mute groups cambian el comportamiento.

### Se cae la conexión

- Detener escrituras normales de control.
- Mantener UI visible pero marcarla como stale/desactualizada.
- Reconectar usando la última IP conocida.
- Refrescar estado visible completo después de reconectar.
- No reenviar arrastres viejos de fader a ciegas.

## Seguridad y uso en vivo

- Tratar la red de control de la XR18 como infraestructura local confiable.
- No exponer UDP `10024` a internet público.
- Preferir una red/router dedicado para shows.
- Desactivar aislamiento de clientes para los dispositivos de control.
- Usar credenciales Wi-Fi fuertes.
- No probar builds experimentales durante un show.
- Mantener siempre la app oficial X AIR como fallback.

## Criterios de aceptación del MVP

El primer MVP se acepta solamente si todo esto se cumple:

- App conecta a una XR18 real por IP manual.
- App tiene botón `Buscar XR18` para encontrar consolas en la red actual.
- App explica claramente que no busca redes Wi-Fi cercanas y que el teléfono
  debe conectarse primero al Wi-Fi correcto desde Android.
- App incorpora el wrapper `codex_developer_feedback_template` desde el root.
- App usa `sourceApp=xr18-mobile-control` y `sourceDisplayName=XR18 Mobile Control`.
- README documenta el `bridgeUrl` y la necesidad de mapear `sourceApp` al
  workspace en Codex Mobile Bridge.
- App mantiene updates remotos activos.
- App lee nombres de canales y estado inicial de fader/mute.
- App controla faders y mutes de canales.
- App controla fader y mute de Main LR.
- App controla niveles de envío a bus 1-6.
- App recibe cambios hechos desde la app oficial X AIR.
- App reconecta después de una interrupción de Wi-Fi.
- App muestra claramente contexto de Main LR vs bus de monitoreo.
- App tiene tests automatizados para OSC y estado de conexión.
- App pasa una prueba de estabilidad de 60 minutos con hardware real.

## Preguntas abiertas para resolver con hardware

- Versión exacta de firmware y diferencias de protocolo.
- Comportamiento de discovery en el router objetivo.
- Suscripción a medidores y frecuencia de update.
- Nivel de soporte necesario para escenas/snapshots.
- Cobertura de parámetros FX requerida por el flujo real.
- Cobertura de comandos de ruteo y confirmaciones necesarias.
- Límite práctico de multi-cliente con X AIR y app nueva conectadas.

## Referencias

- Página oficial Behringer XR18:
  https://www.behringer.com/en/products/0605-aad
- App oficial X AIR para iOS:
  https://apps.apple.com/us/app/x-air/id896725230
- App oficial X AIR para Android:
  https://play.google.com/store/apps/details?id=com.behringer.android.control.app.xair
- Referencia comunitaria de comandos X-Air OSC:
  https://behringer.world/wiki/doku.php?id=x-air_osc
- X-Air Utilities:
  https://sites.google.com/site/xairutilities/
