# Backlog y supervisor de proyectos

Implementación inicial del 5 de noviembre de 2026. El código está preparado para
pilotos; esto no certifica que un backend instalado, un APK o aplicaciones
consumidoras estén ejecutando esta versión. Ningún proyecto se habilita solo.

## Entradas

Las tres entradas escriben en la misma cola durable:

- **Chat/app Bridge:** menú «Backlog y Tu noche», «Agregar tarea» o
  `/backlog Cambiar el título…` en el chat del proyecto. El comando guarda el
  pedido sin llamar al modelo. Los borradores no confirmados conservan identidad
  en el dispositivo para reintentar sin duplicar. Esta primera pantalla admite
  texto; capturas y audio se cargan por Feedback o WhatsApp. Un comando backlog
  con adjuntos en el compositor conserva el borrador y explica esa alternativa.
- **WhatsApp / Info Codex:** selector «Backlog · Ejecutar después». Se preservan
  proyecto, mensajes agrupados y adjuntos; el comprobante se envía después de
  guardar. No abre un chat al capturar el pedido. Requiere desplegar esta versión
  del adaptador y del backend juntos.
- **Codex Bridge Feedback:** «Cuándo ejecutar → Añadir al backlog». Se conservan
  capturas y observaciones; el audio se transcribe al ingresar. Se confirma con
  `backlogId`; las colas originales sólo se retiran tras ese comprobante. Los SDK
  centrales Flutter/web tienen cambios fuente sin publicar: los consumidores del
  release aprobado anterior todavía no reciben esta opción. No se modificó su
  descriptor aprobado ni se copiaron SDK a otros proyectos.

**Codex Folder no es una entrada ni tiene watcher para este sistema.** Puede ser
material de consulta cuando el usuario lo solicita dentro de un encargo.

## Ejecución

Cada encargo se reclama de forma persistente. El siguiente toma el resultado y
el commit del anterior, vuelve a inspeccionar el estado actual y ejecuta el ciclo
Generator/Reviewer completo. Terminar un job de Generator no libera la cola.
El coordinador también consulta los jobs: no necesita que el celular permanezca
abierto para que continúen los turnos.

Al concluir se exige árbol limpio, comandos de validación, commit nuevo, push
sin force a la rama DEV autorizada, confirmación del hash remoto, despliegue por
el procedimiento configurado y comprobación HTTP del mismo hash. Un resultado
sin commit nuevo no se considera una implementación completada. El proceso de
entrega corre fuera del bloqueo del registro: se pueden cargar pedidos mientras
publica. Un fallo visible retiene los encargos siguientes de ese proyecto hasta
reintentar o retirar el encargo fallido. Otros proyectos pueden avanzar. «Frenar» solicita cancelar los jobs conocidos y conserva la reserva hasta comprobar el cierre; no declara detenido un proceso desconocido ni interrumpe una publicación ya iniciada. «Pausar nuevos» deja terminar el ciclo actual.

El piloto limita a un ciclo de trabajo global por registro de coordinación. Hay
reservas por proyecto y archivos de admisión compartidos entre procesos; los
chats normales no inician otro escritor en un proyecto reservado. Un arranque
interrumpido se reconcilia con su sesión, sin reenviar a ciegas. Si no puede
comprobarse, queda `uncertain` para inspección operativa; no hay recuperación
forzada automática que pueda duplicar un escritor desconocido. Reintentar un
encargo fallido abre una sesión nueva conservando la identidad del encargo.

## Noche y calibración

La cola de pedidos explícitos funciona todo el día. El supervisor autónomo usa
por defecto **22:30–08:00, America/Argentina/Buenos_Aires**. Se despierta con el
scheduler cada 15 segundos, usando sleep del proceso sin llamadas al modelo.

Con política habilitada, la auditoría nocturna comprueba Git y DEV como máximo
una vez por hora aunque no haya tareas. Si la versión está atrasada, ejecuta
validación/push/publicación DEV del commit existente sin llamar a un agente. No
mezcla cambios locales previos sin commit: informa el bloqueo para revisarlos.

La exploración de mejoras es opcional (`autonomous` + `focus` autorizado), con
hasta dos observaciones por noche, separadas una hora. El análisis usa herramientas
de lectura; puede dormir en silencio, plantear una pregunta con opciones o poner
un encargo dentro del foco autorizado en la cola. Una política cambiada o una
respuesta recibida fuera de esa noche no autoriza nueva ejecución autónoma.

El presupuesto inicial es de seis arranques por ventana, tres turnos de Generator
y dos de Reviewer por encargo. Son límites de actividad, no una medición monetaria
ni una garantía de gasto exacto de tokens. El proveedor conserva sus límites de
ejecución. Un ciclo que excede 45 minutos se señala y conserva su reserva hasta
comprobar cierre: el watchdog todavía no cancela procesos desconocidos.

`Tu noche` resume avances DEV, bloqueos y decisiones. Muestra un avance por
proyecto, hasta tres proyectos y un recorrido desplegable; las opciones elegidas
entran en la misma cola. Rechazar descarta la propuesta; las observaciones se guardan sin ejecutar y se incorporan al encargo cuando se elige una opción. La actividad reciente del worker se informa por separado
de la fecha de consulta. Es una primera versión para calibrar frecuencia, foco,
utilidad y coste. No genera videos automáticamente. La bandeja de decisiones
se refresca con la app abierta; esta versión no añade push remoto de las preguntas
nocturnas con la aplicación cerrada.

## Configuración operativa

En instalaciones con dos backends, `WORK_HUB_URL` dirige las entradas del Bridge normal al coordinador DEV. La app y WhatsApp ven la misma cola; los lotes de Feedback en modo backlog llegan completos al mismo receptor. No se reenvían cookies ni credenciales del cliente. Un reinicio devuelve 503 y conserva la identidad del envío para reintentar.

API disponible en raíz y `/api/v1`:

| Método y ruta | Uso |
| --- | --- |
| `GET /work` | Cola, noche, decisiones, actividad del worker |
| `POST /work/backlog` | Recepción idempotente con source y source_key |
| `PUT /work/policy` | Procedimiento DEV y límites por proyecto |
| `POST /work/backlog/{id}/control` | cancel/retry/stop con revisión vigente |
| `POST /work/questions/{id}/choose` | Elegir opción y guardar encargo |
| `POST /work/questions/{id}/respond` | Rechazar o guardar observaciones |

Ejemplo de política, para adaptar a un **worktree DEV aislado registrado**:

```json
{
  "workspace_path": "/ruta/registrada/al/proyecto-dev",
  "enabled": true,
  "dev_branch": "dev/night",
  "remote": "origin",
  "dev_url": "https://dev-del-proyecto.example/version.json",
  "validate": [["npm", "test"], ["npm", "run", "build"]],
  "deploy": ["./scripts/deploy-dev.sh"],
  "dev_isolated": true,
  "reconcile_dev": true,
  "autonomous": true,
  "focus": "Resolver backlog y mejorar accesibilidad de pantallas existentes",
  "max_tasks_per_day": 6,
  "max_observations_per_night": 2
}
```

El endpoint de versión debe servir `{"environment":"dev","commit":"HASH"}`.
Los comandos son argv configurados por el operador, nunca instrucciones de una
tarea o respuesta de un modelo. Su infraestructura y credenciales deben estar
limitadas a DEV; declarar `dev_isolated` no crea esa separación. El coordinador
no tiene procedimientos de promoción a QA/producción.

No hay configuración inventada para Peluquería ni Cebando Tradición. Para
habilitarlos se debe registrar su worktree, procedimiento y comprobante DEV reales.
La cola se conserva aunque falte esa configuración. No hay un despliegue ni APK
nuevo producido por esta implementación.

## Primera prueba

Se ejecuta automáticamente en `tests/test_work_coordinator.py` el caso
`test_two_tasks_publish_in_sequence_with_real_git_and_dev`:

1. Proyecto descartable, rama `dev/lab`, remoto Git bare y servicio HTTP aislados.
2. Encargo del chat: cambiar título. Encargo de WhatsApp: agregar descripción.
3. Agentes controlados en el test; ciclos completos, commits/push/DEV reales.
4. El segundo recibe el hash anterior y ambos completan sólo con DEV confirmado.

No se enviaron mensajes de WhatsApp ni se llamaron modelos externos para este
piloto. La captura de `Tu noche` usa el widget real y datos sintéticos explícitos.
Ver [evidencia y capturas](../reports/work-coordinator-pilot/informe.html).

La primera prueba con agentes reales debe repetir esos dos cambios en un DEV
público descartable, cargando el segundo mientras el primero trabaja. Después se
puede habilitar un proyecto real y calibrar una noche completa. Aún no se certifican
recepción push física, duración nocturna real ni despliegues de consumidores.
