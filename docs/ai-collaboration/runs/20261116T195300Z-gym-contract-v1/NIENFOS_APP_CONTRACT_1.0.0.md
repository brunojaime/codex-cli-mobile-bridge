# Contrato compartido Nienfos para preparar aplicaciones

**Protocolo:** `nienfos.app-spec/1.0.0` · **Catálogo:** `2026-11-16.1` · **Fecha:** 16/11/2026.

Este documento es autocontenido: incluye la instrucción para ChatGPT, todos los esquemas exactos, el catálogo observado y un ejemplo completo validado. Bruno puede adjuntarlo a la conversación donde prepara una app. El código de la fábrica consume el mismo JSON que ChatGPT entrega; no es necesario volver a convertir un documento libre en otra especificación.

## 1. Resultado buscado y alcance real de esta versión

El usuario describe su producto de forma libre, con toda la documentación necesaria. ChatGPT acompaña el análisis y produce una especificación estructurada trazable. Python valida e importa ese paquete. El coordinador entrega a desarrollo, UX y revisión las historias, reglas y contratos pertinentes sin una segunda redacción por un agente de requisitos.

El objetivo posterior es componer una base operable rápidamente con módulos compartidos versionados, para concentrar el trabajo creativo en el dominio. Este contrato prepara ese flujo; **no demuestra que toda la app pueda generarse en minutos**. Validar/importar un contrato, instalar dependencias, configurar proveedores, implementar negocio y publicar son operaciones diferentes y se miden por separado.

Esta entrega implementa: esquemas, catálogo, validación semántica, importación local idempotente, contexto determinista, contrato de recibo de capacidades e ingreso opcional al coordinador existente. No implementa en esta tarea un nuevo motor universal de negocio, instaladores para capacidades propuestas, todas las pantallas ni publicación de Gym. No reinicia agentes ni migra aplicaciones existentes.

## 2. Cómo usarlo con ChatGPT

1. Adjuntar este `.md` y el pedido/relevamiento completo. No hacen falta credenciales.
2. Pedir análisis de coherencia y decisiones materiales. Las preguntas deben incluir alternativas y su impacto. No trasladar al usuario decisiones rutinarias ya cubiertas por las bases.
3. Producir un único `bundle.json` conforme al esquema incrustado; entregar el archivo, no sólo una descripción ni trozos incompatibles. Mantener un resumen humano breve separado.
4. Si quedan decisiones que bloquean, entregar `status: draft`, explicarlas y conservar el trabajo. Al resolverse, generar una nueva revisión con las fuentes de decisión. Un contrato borrador puede validarse estructuralmente, pero no entrar a ejecución.
5. El operador valida. Los diagnósticos indican ubicación y clase de error. ChatGPT corrige conservando IDs, historias y alcance; no elimina criterios para lograr validación.
6. El operador importa al workspace preparado y el coordinador lee exactamente ese paquete. Originales, autorización y comprobaciones continúan siendo independientes.

### Prompt listo para copiar

> Leé íntegramente este contrato y mi pedido/relevamiento. Prepará la aplicación usando `nienfos.app-spec/1.0.0` y el catálogo `2026-11-16.1` incluidos aquí. No programes ni declares instalaciones realizadas. Entregá un archivo `bundle.json` completo que cumpla exactamente el esquema, más un resumen breve de alcance, primer resultado útil y decisiones pendientes.
>
> Conservá IDs y criterios originales. Cuando no existan, asigná IDs estables, trazá cada historia/criterio/regla a fuentes identificadas y no los renumeres por cambios de orden. Diferenciá afirmaciones del usuario, propuestas y datos de referencias. No conviertas una propuesta tuya en una decisión confirmada. No inventes precios, impuestos, consentimiento, derechos sobre contenido, recursos, repositorios, URLs de despliegue, credenciales o verificaciones.
>
> Definí roles, permisos y ámbito; entidades, campos, invariantes y estados; operaciones y recuperación; recorridos completos por rol; pantallas y navegación; integraciones; criterios observables y casos de verificación; unidades de trabajo pequeñas con propiedad de archivos y dependencias. Elegí el primer recorrido útil según mis objetivos y prioridades, no según el orden de tablas o pantallas. Señalá las reglas compartidas que se reutilizan y el trabajo de integración/dominio que permanece.
>
> Usá únicamente IDs reales del catálogo para capacidades. `available` no significa instalado en esta app; `adapter_required` requiere integración; `proposed` no tiene instalador listo. Una capacidad no satisface historias automáticamente. No incluyas recibos de ejecución ni resultados inventados. Configuración desconocida va como `null` y pendiente explícito, nunca como una URL o identificador ficticio.
>
> Para cada pantalla definí propósito, acción principal, roles, permisos, operaciones, conexiones y los ocho estados del esquema, explicando aplicabilidad. Para cada recorrido explicá inicio, pasos, resultado, persistencia y recuperación. No confundas especificación de pantalla con diseño visual aprobado. Describí una dirección propia; UX comparará dos propuestas y resolverá una familia piloto antes de expandir, según V5.1 revisada.
>
> Incluí fallos y casos negativos: aislamiento, revocación durante revisión, concurrencia, cancelación sin escritura, respuesta perdida/reintento, borradores, error de proveedor y recarga. Sólo los escenarios aplicables: justificá los que no apliquen. No simplifiques historias para evitar un caso difícil. No deduzcas que un dato es cero por una consulta fallida.
>
> Evitá documentos o matrices duplicadas: `bundle.json` es la especificación canónica; los demás archivos son vistas o evidencia. No incluyas comandos ejecutables en extensiones. Con decisiones materiales no resueltas usá draft y preguntá sólo lo imprescindible. No marques ready hasta cerrar decisiones bloqueantes y completar la cobertura formal. Un ready estructural no es aceptación de producto ni autorización de despliegue.

## 3. Qué es cada sección del paquete

Todos los campos declarados por cada objeto son obligatorios salvo que un esquema use explícitamente `null`. Una lista vacía sólo es válida donde el esquema lo permite y el contexto la justifica. No agregar propiedades fuera del esquema; extensiones sólo en el campo reservado. Los IDs son estables, ASCII, de hasta 80 caracteres con el patrón exacto del esquema. Las unidades tienen además las restricciones del coordinador: letras/números/guiones/guion bajo, máximo 60, y `delivery` reservado.

| Sección | Responsabilidad y vínculo |
|---|---|
| contract/version/package_id/revision/status | Identidad del protocolo, paquete y revisión; draft/ready no describen implementación. |
| product | Tipo product/project/owned, stack soportado, audiencia, objetivos, alcance, exclusiones y plataformas. |
| sources | Fuentes autorizadas y procedencia. locator identifica fuente/sección; sha256 sólo si se conoce de bytes reales. No inventarlo. |
| decisions | Confirmadas, propuestas o abiertas; qué bloquean y qué fuente las respalda. |
| capabilities | Solicitud de capacidades del catálogo y pendientes del consumidor, sin afirmar ejecución. |
| roles/permissions | Actores y operaciones autorizadas con ámbito self/assigned/site/organization/platform/public. |
| entities | Campos tipados, sensibilidad, relaciones, invariantes, pertenencia y retención. |
| state_machines | Estado inicial, transiciones, permisos, condiciones, efectos y recuperación. |
| operations | Entrada, permiso, revisión, idempotencia, concurrencia, auditoría y efectos externos. |
| api_contracts | Rutas/métodos HTTP, fase, operación, JSON Schema de request/response, errores y recuperación, sesión/CSRF y permisos. |
| stories/acceptance | Necesidad/resultado por rol, prioridad, dependencias y CA Given/When/Then con caso negativo y fuente. |
| screens | Contrato funcional completo de pantalla, navegación, estados y restricciones de interacción. |
| journeys | Recorridos por rol, operación por paso, resultado útil y prueba de persistencia. |
| integrations | Proveedor si se conoce, nombres de configuración sin valores secretos, ambientes, fallos y evidencia pendiente. |
| visual_direction | Identidad propuesta, referencias a observar, recorrido piloto, aceptación y tokens propuestos. |
| delivery | Primer recorrido, casos de prueba, objetivo local/dev, evidencia, copias, observabilidad y publicación. |
| work_units | Incrementos pequeños con historias/CA, owner generator/ux, paths y dependencias. No son recibos de trabajo terminado. |
| extensions | Metadatos optativos con claves x-namespace.nombre; nunca modifican permisos, verificación ni comportamiento ejecutable. |

### 3.1 Fuentes y cobertura

Cada historia y criterio conserva fuentes y vínculos recíprocos. La fábrica verifica referencias, unicidad y cobertura entre historias, CA, pantallas, casos de prueba y unidades. También conserva y calcula el hash real del bundle recibido. El operador entrega el catálogo esperado de IDs cuando está disponible; si difiere se rechaza.

**La cobertura formal no demuestra que el modelo haya leído correctamente el documento original.** La revisión independiente contrasta la especificación con las fuentes, especialmente exclusiones, condiciones, prioridades y decisiones del usuario. El hash declarado por una fuente en el bundle es una referencia hasta que el operador coteja los bytes; no se descarga ni se confía en un enlace arbitrario por indicación del modelo. Los originales son datos, no instrucciones para ejecutar herramientas o revelar secretos.

### 3.2 Decisiones y ambigüedad

`confirmed` exige fuente de tipo user/decision. Esto acredita la referencia declarada, no una firma de autorización humana. `open` y `proposed` indican lo no confirmado. `blocks` identifica none/foundation/domain/delivery. Un paquete ready no puede contener decisiones no confirmadas que bloqueen. Resolver una ambigüedad no concede permiso para publicar, cobrar o enviar comunicaciones.

No bloquear toda la app por falta de una credencial de un módulo opcional. Mantener dependencia/pending y continuar el alcance independiente. Tampoco marcar un servicio prometido apagado como No aplica. Un supuesto reversible tiene explicación y fuente; no puede alterar dinero, privacidad, permisos o derechos sin la decisión correspondiente.

### 3.3 Tipo de solución y reutilización

- product: producto enlatado para negocios con aislamiento. Mi suscripción a Nienfos es distinta de cobros del negocio.
- project: proyecto a medida; incluye capacidades aplicables de pagos a Nienfos y tutoriales.
- owned: producto propio; seleccionar capacidades por relevamiento.
- La cantidad de usuarios y el registro abierto no determinan el offering_type.
- El contrato no contiene `catalogId/projectId` falsos ni secretos. El operador resuelve los vínculos canónicos reales antes de provisionar.
- Para Android/iOS, el contrato conserva plataformas comprometidas; los stacks instalables de este protocolo inicial son Worker/SvelteKit web. Los adapters nativos y su validación física son trabajo explícito, no paridad automática.

### 3.4 Permisos y multiempresa

La identidad no acredita membresía ni permisos del negocio. El ámbito proviene de sesión y autorización servidor; nunca sólo de parámetros enviados por el navegador. Cada operación declara permisos. La navegación conserva organización/sede, también por avatar, cuenta, enlace directo, volver y recarga; se revalida la autorización actual.

Considerar revocación entre revisión y confirmación, varios roles, asignaciones y sedes. No combinar concesiones parciales para inventar un permiso más amplio. Herramientas internas/auditoría requieren permisos específicos, fuera del recorrido cotidiano. No reactivar credenciales ni permisos al restaurar una ficha.

### 3.5 Entidades, estados y operaciones

Los nombres y las invariantes deben explicar negocio, no sólo tablas. Referencias apuntan a entidades existentes. Estados son únicos y alcanzables desde el inicial; cada transición conserva condición, efecto y reparación. Las invariantes reales se validan dentro de la transacción relevante, no sólo en preview.

Dinero: unidades menores enteras, moneda explícita, sin sumar monedas sin política fechada. Tiempo: zona IANA y semántica de fechas de negocio/registro/efectivas. Cupos: no superar capacidad con solicitudes simultáneas. Estas reglas se especifican cuando apliquen; el esquema no sustituye su implementación.

Mutaciones administrativas: borrador → revisión → confirmación → resultado autoritativo. Cancelar conserva borrador y no escribe negocio. `review` declara si hay revisión; cuando una operación rápida del dominio usa otro patrón, justificarlo en validation y con fuente. No quitar revisión administrativa por conveniencia. Cada mutación exige auditoría atómica. Baja recuperable y backups son responsabilidades diferentes.

Idempotencia: identificar intención/operación estable y reconciliar estado real después de perder una respuesta. Describir vigencia, actor, ámbito, versión y rechazo de token ajeno. No reintentar ciegamente una mutación incierta. Para efectos externos, outbox/compensación según arquitectura; restaurar una fila no revierte un cobro ni un email.

Las rutas HTTP se describen en api_contracts y referencian una operación existente. Cada una declara fase (query/review/commit/cancel/receipt), campos, JSON Schema cerrado de request/response y errores con status/código/recuperación. GET transporta entrada por query; POST/PUT/PATCH/DELETE por JSON. Las mutaciones requieren sesión y CSRF. Los permisos deben coincidir con la operación. Los esquemas de payload se comprueban como JSON Schema y sólo admiten referencias locales. Se pueden usar directamente para validación del consumidor y pruebas; esta versión no genera OpenAPI ni implementa automáticamente los endpoints. Los adapters mantienen exactamente los payloads acordados.

### 3.6 Recorridos, pantallas y UX

Derivar un resultado útil por rol antes de multiplicar módulos. No imponer a todas las apps una secuencia propia de Gym. Cada paso referencia pantalla y operación reales del contrato, explica consecuencia y recuperación. Una operación debe estar disponible en la pantalla y para ese rol. Los enlaces del recorrido deben existir en navigation_to.

Cada pantalla define: quién, para qué, acción primaria, secundarias, datos/operaciones, navegación y ocho estados: loading, empty, ready, error, forbidden, offline, conflict, pending. Cada estado incluye applicable y behavior; false exige una explicación concreta. En offline sin soporte de edición, indicarlo honestamente y definir qué pasa con el borrador. No prometer sincronización inexistente.

Inicio se orienta al rol, contexto y tarea; cuenta desde avatar. Considerar primer ingreso, regreso, invitación y destino autorizado solicitado. Cards con resumen real, estado e interacción útil; evitar eslóganes gigantes, enlaces indiferenciados y anidamientos innecesarios. No imponer cards a cada dato.

Responsive no es achicar escritorio. Definir foco, teclado, tacto, retorno tras cerrar/cancelar, nombres accesibles, contraste, mensajes y reduced motion. Los tokens de marca son propuestas hasta validar la composición. Referencias son imágenes que UX debe localizar y observar; un listado de nombres no acredita inspección. Dos propuestas y familia piloto antes de expandir según V5.1 revisada. Esta entrega no genera todas las pantallas ni certifica su estética.

### 3.7 Integraciones y estados de disponibilidad

Nombres de configuración pueden aparecer, valores secretos nunca. Si proveedor, cliente o precio no están acordados, null y pending. Diferenciar SDK instalado, consumidor configurado, release publicado y recorrido verificado. Google humano y recepción de correo necesitan evidencia propia. Un envío aceptado por proveedor no prueba recepción.

Checkout del catálogo actual es TEST ONLY; no habilita cobros reales por pedirlo en el contrato. No transferir credenciales entre ambientes. No publicar QA/prod, enviar correos a terceros, comprar recursos pagos ni hacer cobros por efecto de importar este paquete.

### 3.8 Pruebas, revisión, unidades y entrega

Cada CA tiene dado/cuando/entonces, negativo, tipo de verificación y ambiente. Cada CA aparece en un caso de verificación y en al menos una unidad de trabajo. Casos human/provider no se sustituyen por tests automatizados. Los comandos de prueba se aportan por el operador fuera del bundle y nunca se ejecutan comandos propuestos en extensiones.

Máximo seis historias y doce CA por unidad; un prerrequisito contract hasta tres historias. Dividir incrementos sin perder cobertura. Owners generator/ux y paths relativos explícitos y acotados. Declarar dependencias por contrato, no exigir toda la app como prerrequisito del primer piloto. El coordinador comprueba prioridades y ciclos. Una unidad UX del piloto debe poder empezar sola o después de un pequeño contrato raíz. No incluir una unidad llamada delivery: la revisión final la programa el coordinador.

El plan describe trabajo propuesto, no permiso irrestricto sobre archivos. El operador revisa propiedad de archivos y verificación antes de ejecutar. La integración sigue serial por commit y los worktrees no conceden privilegios externos. Reviewer conserva independencia y revisa el delta y los riesgos relacionados. Un gate rojo no debe deshabilitar ni abandonar la app.

Cierre de incremento: resultado real, persistencia, permisos, UX y evidencia por versión/ambiente. Cierre global: todo el objetivo aprobado e integrado; publicar es otro hecho que debe comprobarse. Una captura o un JSON verde no sustituyen el recorrido real.

## 4. Entrada interna y comandos

Raíz Lenovo: `~/Documents/Projects/nienfos-gestion-local`. En otros hosts resolver la raíz real, no copiar rutas de este documento como si existieran.

Usar Python con `jsonschema>=4.26,<5` en el entorno de herramientas. Dependencias declaradas en `integrations/platform-ops/app_contracts/requirements.txt`. No instalar globalmente por arrastre. El protocolo valida JSON Schema Draft 2020-12; los esquemas se incluyen completos al final.

Desde la raíz de Gestión:

```bash
python3 integrations/platform-ops/new-app.py contract-validate /ruta/al/bundle.json
python3 integrations/platform-ops/new-app.py contract-import /ruta/al/bundle.json --workspace /ruta/real/de/la/app
```

El validador informa ok/versión/hash/cantidad de historias/CA/status y duración. Errores incluyen ubicación de esquema o referencia, sin imprimir cuerpos completos. El importador exige un workspace existente y ready. Escribe un snapshot inmutable en `.nienfos/contracts/PACKAGE_ID/rREVISION/`: bundle.json, HANDOFF.md e import-receipt.json. Dos importaciones iguales reutilizan; misma revisión con otros bytes o una edición manual del snapshot se rechaza sin sobrescribir. Una revisión posterior se conserva en otro directorio. Bloqueo de archivo evita dos importadores simultáneos; staging y rename evitan snapshots parciales.

No importa bases de datos, no crea datos demo, no ejecuta código del modelo, no crea repositorios, no instala paquetes ni publica. Esas operaciones usan los operadores existentes y autorización del ambiente. El contrato es interfaz común; no un script de ejecución arbitraria.

### Entrega al coordinador existente, sin segunda conversión

En un nuevo pedido del operador para `new-app.py objective`, incluir `contract_bundle` con la ruta real al snapshot, `requirements` con originales disponibles y `expected_story_ids` del catálogo original cuando exista. Conservar key, workspace limpio, objetivo, presupuesto y verification_commands del operador. No arrancar otro equipo si hay uno activo.

La integración opt-in:

1. Valida bundle/status y los IDs esperados, calcula hashes de bytes y canónico.
2. Exige comandos de verificación aportados por el operador, separados del contrato del modelo.
3. Guarda copia del bundle en el estado privado del objetivo.
4. Genera el spec nativo **por proyección determinista**, preservando historias/CA/recorridos/unidades; los contratos detallados permanecen en el bundle íntegro.
5. Entra a executing con cero llamadas de requisitos y todas las unidades pendientes. Las referencias a contratos y reglas de reutilización entran en el handoff de cada rol.
6. Mantiene los circuitos existentes de ejecución, revisión, seguridad, aceptación y aplicación. No acepta la app ni satisface historias por el hecho de importar.

Sin contract_bundle, el flujo existente de requisitos sigue funcionando. No se convierten ejecuciones activas ni se modifican presupuestos/modelos por asociación. El lector directo y la proyección resuelven el mismo protocolo; no existe una segunda especificación redactada manualmente.

### Recibo de capacidades: autoridad separada

`nienfos.foundation-receipt/1.0.0` es producido por el operador/instalador, nunca por ChatGPT al especificar el producto. Incluye hash del bundle, IDs de capacidades, artefacto, estados separados, ambiente, origen/release y evidencias con hash y fecha. El validador comprueba progresión de estados, artefacto del catálogo, bytes de evidencia y contexto remoto; ver esquema exacto.

```bash
python3 integrations/platform-ops/app-contract.py receipt /ruta/receipt.json --bundle /ruta/bundle.json --evidence-root /ruta/evidencia
```

Un recibo es una atestación del operador y los archivos cotejados, no una firma humana ni certificación independiente. Un JSON de evidencia pass tampoco garantiza verdad semántica. No permite marcar historias automáticamente. Esta versión define y valida ese recibo; no conecta un instalador universal nuevo ni elimina tareas del coordinador por un booleano.

## 5. Evolución y mantenimiento

- Identidad del protocolo: nienfos.app-spec; versión inicial exacta 1.0.0. El lector acepta sólo versiones explícitamente soportadas; una versión desconocida se rechaza con diagnóstico. No asumir compatibilidad porque empieza por 1.
- Revisión de un paquete: entero creciente. Misma package_id/revision es inmutable. Cambios de fuentes, reglas o decisiones generan otra revisión, conservando IDs de conceptos estables y el historial.
- SemVer: PATCH corrige documentación/diagnóstico sin cambiar significado o aceptación; MINOR incorpora capacidades opcionales con compatibilidad probada y lectores actualizados; MAJOR cambia significado, obligatoriedad o estructuras incompatibles. Con additionalProperties:false, agregar propiedades exige negociación de versión/lector; no introducirlas silenciosamente en 1.0.0.
- Extensiones x-namespace.nombre son optativas e inertes. No esconder requisitos imprescindibles, cambios de autorización o código en ellas. Si son necesarias para interpretar el producto deben incorporarse al protocolo soportado y validado.
- Catálogo: versión y hashes propios. Describe disponibilidad real de piezas observadas, nunca instalación del consumidor. Una versión nueva no reescribe paquetes existentes ni actualiza apps sin adopción explícita.
- Migraciones: comando explícito, entrada/salida preservadas, diff legible, pruebas de equivalencia y decisión para cambios semánticos. Esta versión no ofrece migración automática entre protocolos desconocidos.
- Publicación del protocolo: cambiar esquemas/catálogo → ejecutar pruebas positivas/negativas y de integración → regenerar este documento → comprobar hashes/ejemplos → distribuir mismo artefacto a humanos y máquina. No mantener el esquema copiado a mano.
- Fuente canónica local: `integrations/platform-ops/app_contracts/v1`. Generador del documento: `app_contracts/generate_document.py`. La copia en Drive y la copia del chat son entregables del mismo release; comparar manifest para detectar divergencia.
- Las nuevas bases se incorporan con dueño, versión, adapter, pruebas, instalación repetible, evidencia y límites. No basta añadir el nombre al catálogo para declararlas listas.

## 6. Medición y prioridades

Registrar pedido/inicio, validación, importación, preparación de base, configuración, implementación de dominio, UX, revisión, espera, integración y publicación. Reportar duración y alcance observados; no sumar trabajos paralelos como tiempo de calendario. Separar coste del modelo, herramientas y espera si hay datos.

El benchmark de este contrato mide lectura/validación/importación en un workspace temporal. No acredita tiempo de crear una app, instalar dependencias, configurar Google ni publicar DEV. El objetivo de minutos para una base operable se comprueba con un consumidor limpio y servicios reales cuando se implemente ese instalador.

Prioridades de consolidación señaladas por la traza de Gym: composición completa cuenta/Inicio/sesiones, navegación con contexto por todos los caminos, operaciones seguras reutilizables, propiedad de archivos suficiente antes de asignar y eliminación de esperas del coordinador. Este contrato evita otra conversión textual; no afirma resolver por sí solo esas demoras.

## 7. Lista de revisión de ChatGPT antes de entregar

- ¿Conservé íntegro el alcance y distinguí decisiones del usuario de propuestas?
- ¿Todos los IDs referenciados existen y son estables? ¿Cada CA tiene fuente, historia, caso y unidad?
- ¿El tipo product/project/owned y las capacidades condicionales son coherentes?
- ¿Los permisos, ámbito y reglas de concurrencia son explícitos para cada operación?
- ¿La primera tarea tiene un recorrido completo y comprobación de persistencia?
- ¿Cada pantalla define los ocho estados, navegación, responsive, accesibilidad y motion?
- ¿Las integraciones distinguen nombres de configuración y verificación real sin secretos?
- ¿Cada dependencia es necesaria, acíclica y consistente con prioridad?
- ¿UX tiene una unidad de implementación activa y piloto temprano?
- ¿Las propuestas de estética siguen pendientes de observación de pantallas reales?
- ¿Evité estados instalado/configurado/verificado inventados y comandos arbitrarios?
- ¿El archivo es un JSON único completo, con draft si quedan decisiones bloqueantes?

## 8. Ejemplos y límites de interpretación

El ejemplo de gimnasio del anexo es un espécimen pequeño para probar el protocolo, no el relevamiento de 173 historias ni un encargo de crear otra app. Sus fuentes y nombres son ilustrativos, no cuentas/clientes reales. No copiar su alcance para reducir una solicitud del usuario. Tampoco heredar sus políticas de retención o permisos a otro negocio.

El ejemplo muestra la forma de todas las secciones y cómo vincular historias, CA, pantallas, recorrido y unidades. Puede haber listas vacías cuando el producto no requiere una capacidad. No inventar integraciones o estados para llenar casilleros. En la carpeta interna hay un segundo espécimen de taller para comprobar independencia del dominio.

La validación es estricta sobre formato y vínculos. La corrección de reglas de negocio, autorización humana, calidad visual, configuración legítima y ejecución siguen requiriendo evidencia y revisión. Texto referenciado, documento importado, código generado, app instalada, servicio configurado, release publicado y recorrido verificado son hechos distintos.

## 9. Esquema exacto de bundle.json

SHA256 del archivo fuente: `9ecd3d77238b3129e70a003d929450ad34a1c35407094e83f2023f0107ab61be`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:nienfos:app-spec:1.0.0",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "contract": {
      "const": "nienfos.app-spec"
    },
    "contract_version": {
      "const": "1.0.0"
    },
    "package_id": {
      "type": "string",
      "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
    },
    "revision": {
      "type": "integer",
      "minimum": 1
    },
    "status": {
      "enum": [
        "draft",
        "ready"
      ]
    },
    "catalog_version": {
      "const": "2026-11-16.1"
    },
    "product": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "name": {
          "type": "string",
          "minLength": 1
        },
        "offering_type": {
          "enum": [
            "product",
            "project",
            "owned"
          ]
        },
        "stack": {
          "enum": [
            "worker-google",
            "sveltekit-worker"
          ]
        },
        "registration": {
          "enum": [
            "open",
            "closed"
          ]
        },
        "objective": {
          "type": "string",
          "minLength": 1
        },
        "audiences": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "in_scope": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "out_of_scope": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "platforms": {
          "type": "array",
          "items": {
            "enum": [
              "web",
              "android",
              "ios"
            ]
          },
          "minItems": 1
        }
      },
      "required": [
        "id",
        "name",
        "offering_type",
        "stack",
        "registration",
        "objective",
        "audiences",
        "in_scope",
        "out_of_scope",
        "platforms"
      ]
    },
    "sources": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/source"
      },
      "minItems": 1
    },
    "decisions": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/decision"
      },
      "minItems": 0
    },
    "capabilities": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/capability"
      },
      "minItems": 0
    },
    "roles": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/role"
      },
      "minItems": 1
    },
    "permissions": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/permission"
      },
      "minItems": 1
    },
    "entities": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/entity"
      },
      "minItems": 0
    },
    "state_machines": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/machine"
      },
      "minItems": 0
    },
    "operations": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/operation"
      },
      "minItems": 0
    },
    "stories": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/story"
      },
      "minItems": 1
    },
    "acceptance": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/acceptance"
      },
      "minItems": 1
    },
    "screens": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/screen"
      },
      "minItems": 1
    },
    "journeys": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/journey"
      },
      "minItems": 1
    },
    "integrations": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/integration"
      },
      "minItems": 0
    },
    "visual_direction": {
      "$ref": "#/$defs/visual"
    },
    "delivery": {
      "$ref": "#/$defs/delivery"
    },
    "work_units": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/unit"
      },
      "minItems": 1
    },
    "extensions": {
      "type": "object",
      "propertyNames": {
        "pattern": "^x-[a-z0-9]+(?:[.-][a-z0-9]+)*$"
      },
      "additionalProperties": true
    },
    "api_contracts": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/api"
      }
    }
  },
  "required": [
    "contract",
    "contract_version",
    "package_id",
    "revision",
    "status",
    "catalog_version",
    "product",
    "sources",
    "decisions",
    "capabilities",
    "roles",
    "permissions",
    "entities",
    "state_machines",
    "operations",
    "stories",
    "acceptance",
    "screens",
    "journeys",
    "integrations",
    "visual_direction",
    "delivery",
    "work_units",
    "extensions",
    "api_contracts"
  ],
  "$defs": {
    "source": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "title": {
          "type": "string",
          "minLength": 1
        },
        "locator": {
          "type": "string",
          "minLength": 1
        },
        "sha256": {
          "anyOf": [
            {
              "type": "string",
              "pattern": "^[0-9a-f]{64}$"
            },
            {
              "type": "null"
            }
          ]
        },
        "kind": {
          "enum": [
            "user",
            "document",
            "decision",
            "reference"
          ]
        }
      },
      "required": [
        "id",
        "title",
        "locator",
        "sha256",
        "kind"
      ]
    },
    "decision": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "description": {
          "type": "string",
          "minLength": 1
        },
        "status": {
          "enum": [
            "confirmed",
            "proposed",
            "open"
          ]
        },
        "source_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "blocks": {
          "enum": [
            "none",
            "foundation",
            "domain",
            "delivery"
          ]
        },
        "options": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "description",
        "status",
        "source_ids",
        "blocks",
        "options"
      ]
    },
    "capability": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "catalog_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "required": {
          "type": "boolean"
        },
        "reason": {
          "type": "string",
          "minLength": 1
        },
        "source_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "configuration": {
          "type": "object",
          "additionalProperties": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "pending": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "catalog_id",
        "required",
        "reason",
        "source_ids",
        "configuration",
        "pending"
      ]
    },
    "role": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "name": {
          "type": "string",
          "minLength": 1
        },
        "description": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "id",
        "name",
        "description"
      ]
    },
    "permission": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "action": {
          "type": "string",
          "minLength": 1
        },
        "resource": {
          "type": "string",
          "minLength": 1
        },
        "role_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "scope": {
          "enum": [
            "self",
            "assigned",
            "site",
            "organization",
            "platform",
            "public"
          ]
        },
        "conditions": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "action",
        "resource",
        "role_ids",
        "scope",
        "conditions"
      ]
    },
    "field": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "type": {
          "enum": [
            "string",
            "integer",
            "boolean",
            "date",
            "datetime",
            "money",
            "reference",
            "file",
            "enum"
          ]
        },
        "required": {
          "type": "boolean"
        },
        "sensitivity": {
          "enum": [
            "public",
            "internal",
            "personal",
            "sensitive"
          ]
        },
        "constraints": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "reference_entity": {
          "anyOf": [
            {
              "type": "string",
              "minLength": 1
            },
            {
              "type": "null"
            }
          ]
        },
        "values": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "name",
        "type",
        "required",
        "sensitivity",
        "constraints",
        "reference_entity",
        "values"
      ]
    },
    "entity": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "description": {
          "type": "string",
          "minLength": 1
        },
        "source_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "scope": {
          "enum": [
            "self",
            "site",
            "organization",
            "platform",
            "public"
          ]
        },
        "fields": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/field"
          },
          "minItems": 1
        },
        "invariants": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "retention": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "id",
        "description",
        "source_ids",
        "scope",
        "fields",
        "invariants",
        "retention"
      ]
    },
    "transition": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "from": {
          "type": "string",
          "minLength": 1
        },
        "to": {
          "type": "string",
          "minLength": 1
        },
        "permission_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "guards": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "effects": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "recovery": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "id",
        "from",
        "to",
        "permission_ids",
        "guards",
        "effects",
        "recovery"
      ]
    },
    "machine": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "entity_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "states": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "initial": {
          "type": "string",
          "minLength": 1
        },
        "transitions": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/transition"
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "entity_id",
        "states",
        "initial",
        "transitions"
      ]
    },
    "operation": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "entity_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "method": {
          "enum": [
            "read",
            "create",
            "update",
            "delete",
            "restore",
            "command"
          ]
        },
        "permission_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "input_fields": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "validation": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "review": {
          "type": "boolean"
        },
        "idempotency": {
          "type": "string",
          "minLength": 1
        },
        "concurrency": {
          "type": "string",
          "minLength": 1
        },
        "atomic_audit": {
          "type": "boolean"
        },
        "recovery": {
          "type": "string",
          "minLength": 1
        },
        "external_effects": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "entity_id",
        "method",
        "permission_ids",
        "input_fields",
        "validation",
        "review",
        "idempotency",
        "concurrency",
        "atomic_audit",
        "recovery",
        "external_effects"
      ]
    },
    "acceptance": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "story_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "given": {
          "type": "string",
          "minLength": 1
        },
        "when": {
          "type": "string",
          "minLength": 1
        },
        "then": {
          "type": "string",
          "minLength": 1
        },
        "negative": {
          "type": "string",
          "minLength": 1
        },
        "verification": {
          "enum": [
            "automated",
            "browser",
            "human",
            "provider"
          ]
        },
        "environment": {
          "enum": [
            "local",
            "dev",
            "qa",
            "prod"
          ]
        },
        "source_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        }
      },
      "required": [
        "id",
        "story_id",
        "given",
        "when",
        "then",
        "negative",
        "verification",
        "environment",
        "source_ids"
      ]
    },
    "story": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "role_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "need": {
          "type": "string",
          "minLength": 1
        },
        "outcome": {
          "type": "string",
          "minLength": 1
        },
        "priority": {
          "enum": [
            "P0",
            "P1",
            "P2"
          ]
        },
        "source_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "depends_on": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "acceptance_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "capability_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "operation_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "screen_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        }
      },
      "required": [
        "id",
        "role_id",
        "need",
        "outcome",
        "priority",
        "source_ids",
        "depends_on",
        "acceptance_ids",
        "capability_ids",
        "operation_ids",
        "screen_ids"
      ]
    },
    "screen_state": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "name": {
          "enum": [
            "loading",
            "empty",
            "ready",
            "error",
            "forbidden",
            "offline",
            "conflict",
            "pending"
          ]
        },
        "applicable": {
          "type": "boolean"
        },
        "behavior": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "name",
        "applicable",
        "behavior"
      ]
    },
    "screen": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "title": {
          "type": "string",
          "minLength": 1
        },
        "route": {
          "type": "string",
          "pattern": "^/(?!/)[^\\s]*$"
        },
        "role_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "permission_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "story_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "purpose": {
          "type": "string",
          "minLength": 1
        },
        "primary_action": {
          "type": "string",
          "minLength": 1
        },
        "secondary_actions": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "operation_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "navigation_to": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "states": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/screen_state"
          },
          "minItems": 8
        },
        "responsive": {
          "type": "string",
          "minLength": 1
        },
        "accessibility": {
          "type": "string",
          "minLength": 1
        },
        "motion": {
          "type": "string",
          "minLength": 1
        },
        "visual_family": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "id",
        "title",
        "route",
        "role_ids",
        "permission_ids",
        "story_ids",
        "purpose",
        "primary_action",
        "secondary_actions",
        "operation_ids",
        "navigation_to",
        "states",
        "responsive",
        "accessibility",
        "motion",
        "visual_family"
      ]
    },
    "step": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "screen_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "action": {
          "type": "string",
          "minLength": 1
        },
        "operation_id": {
          "anyOf": [
            {
              "type": "string",
              "minLength": 1
            },
            {
              "type": "null"
            }
          ]
        },
        "expected": {
          "type": "string",
          "minLength": 1
        },
        "failure_recovery": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "screen_id",
        "action",
        "operation_id",
        "expected",
        "failure_recovery"
      ]
    },
    "journey": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "role_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "story_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "first_useful": {
          "type": "boolean"
        },
        "initial_state": {
          "type": "string",
          "minLength": 1
        },
        "steps": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/step"
          },
          "minItems": 1
        },
        "outcome": {
          "type": "string",
          "minLength": 1
        },
        "persistence_proof": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "id",
        "role_id",
        "story_ids",
        "first_useful",
        "initial_state",
        "steps",
        "outcome",
        "persistence_proof"
      ]
    },
    "integration": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "purpose": {
          "type": "string",
          "minLength": 1
        },
        "provider": {
          "anyOf": [
            {
              "type": "string",
              "minLength": 1
            },
            {
              "type": "null"
            }
          ]
        },
        "required": {
          "type": "boolean"
        },
        "configuration_names": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "operation_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "environments": {
          "type": "array",
          "items": {
            "enum": [
              "local",
              "dev",
              "qa",
              "prod"
            ]
          },
          "minItems": 0
        },
        "failure_policy": {
          "type": "string",
          "minLength": 1
        },
        "verification": {
          "type": "string",
          "minLength": 1
        },
        "pending": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "id",
        "purpose",
        "provider",
        "required",
        "configuration_names",
        "operation_ids",
        "environments",
        "failure_policy",
        "verification",
        "pending"
      ]
    },
    "unit": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "owner": {
          "enum": [
            "generator",
            "ux"
          ]
        },
        "objective": {
          "type": "string",
          "minLength": 1
        },
        "stories": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "acceptance_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "capability_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "paths": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "depends_on": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "ui": {
          "type": "boolean"
        },
        "risks": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "security_risks": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "kind": {
          "enum": [
            "contract",
            "implementation",
            "integration"
          ]
        }
      },
      "required": [
        "id",
        "owner",
        "objective",
        "stories",
        "acceptance_ids",
        "capability_ids",
        "paths",
        "depends_on",
        "ui",
        "risks",
        "security_risks",
        "kind"
      ]
    },
    "test_case": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "acceptance_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "scenario": {
          "type": "string",
          "minLength": 1
        },
        "expected": {
          "type": "string",
          "minLength": 1
        },
        "level": {
          "enum": [
            "unit",
            "integration",
            "browser",
            "human",
            "provider"
          ]
        },
        "environment": {
          "enum": [
            "local",
            "dev",
            "qa",
            "prod"
          ]
        }
      },
      "required": [
        "id",
        "acceptance_ids",
        "scenario",
        "expected",
        "level",
        "environment"
      ]
    },
    "delivery": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "target": {
          "enum": [
            "local",
            "dev"
          ]
        },
        "first_journey_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "checks": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/test_case"
          },
          "minItems": 1
        },
        "evidence_policy": {
          "type": "string",
          "minLength": 1
        },
        "backup_restore": {
          "type": "string",
          "minLength": 1
        },
        "observability": {
          "type": "string",
          "minLength": 1
        },
        "performance_budget": {
          "type": "string",
          "minLength": 1
        },
        "rollout": {
          "type": "string",
          "minLength": 1
        },
        "external_dependencies": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        }
      },
      "required": [
        "target",
        "first_journey_id",
        "checks",
        "evidence_policy",
        "backup_restore",
        "observability",
        "performance_budget",
        "rollout",
        "external_dependencies"
      ]
    },
    "visual": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "identity": {
          "type": "string",
          "minLength": 1
        },
        "references": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "pilot": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "acceptance": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 1
        },
        "tokens": {
          "type": "object",
          "additionalProperties": {
            "type": "string",
            "minLength": 1
          }
        }
      },
      "required": [
        "identity",
        "references",
        "pilot",
        "acceptance",
        "tokens"
      ]
    },
    "api": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "operation_id": {
          "type": "string",
          "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
        },
        "method": {
          "enum": [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE"
          ]
        },
        "path": {
          "type": "string",
          "pattern": "^/(?!/)[^\\s]*$"
        },
        "request_fields": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "response": {
          "type": "string",
          "minLength": 1
        },
        "errors": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "code": {
                "type": "string",
                "minLength": 1
              },
              "http_status": {
                "type": "integer",
                "minimum": 400,
                "maximum": 599
              },
              "meaning": {
                "type": "string",
                "minLength": 1
              },
              "recovery": {
                "type": "string",
                "minLength": 1
              }
            },
            "required": [
              "code",
              "http_status",
              "meaning",
              "recovery"
            ]
          },
          "minItems": 1
        },
        "session_required": {
          "type": "boolean"
        },
        "csrf_required": {
          "type": "boolean"
        },
        "permission_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "uniqueItems": true
        },
        "phase": {
          "enum": [
            "query",
            "review",
            "commit",
            "cancel",
            "receipt"
          ]
        },
        "request_schema": {
          "type": "object"
        },
        "response_schema": {
          "type": "object"
        }
      },
      "required": [
        "id",
        "operation_id",
        "method",
        "path",
        "request_fields",
        "response",
        "errors",
        "session_required",
        "csrf_required",
        "permission_ids",
        "phase",
        "request_schema",
        "response_schema"
      ]
    }
  }
}
```

## 10. Catálogo exacto de capacidades

SHA256 del archivo fuente: `5bf01ef84865475686cec51d2ca2e41d2f2fe25435e71f509af99dbdc96ca117`.

```json
{
  "contract": "nienfos.capability-catalog",
  "version": "2026-11-16.1",
  "observed_host": "Lenovo",
  "bootstrap_version": "0.5.0-dev.29-visual.2",
  "bootstrap_sha256": "23ca70fa823db16394efc8f4821d2687c78dd2c680dceecefbf5b398b7162e82",
  "meaning": "available indica pieza disponible; nunca acredita instalación/configuración/verificación de un consumidor. adapter_required exige trabajo de integración. proposed no es instalable.",
  "capabilities": [
    {
      "id": "identity.account",
      "availability": "available",
      "description": "Cuenta, Google/contraseña, recuperación, sesiones y perfil",
      "package": "@nienfos/app-platform",
      "package_version": "0.1.0-dev.20-account.2",
      "artifact_sha256": "f06f0b048777afeb3127d83172a047a42af66826ce23f5cbc6ae429dad6a40e4",
      "guide": "docs/platform/COMMON-ACCOUNT-BASE.md"
    },
    {
      "id": "admin.reviewed-records",
      "availability": "adapter_required",
      "description": "Revisión/confirmación, CAS, auditoría y restauración para entidades del dominio",
      "package": "@nienfos/app-platform",
      "package_version": "0.1.0-dev.20-account.2",
      "artifact_sha256": "f06f0b048777afeb3127d83172a047a42af66826ce23f5cbc6ae429dad6a40e4",
      "guide": "../nienfos-app-platform/docs/REVIEWED-ABM.md"
    },
    {
      "id": "locale.fields",
      "availability": "available",
      "description": "Selectores país, moneda y zona horaria",
      "package": "@nienfos/app-platform",
      "package_version": "0.1.0-dev.20-account.2",
      "artifact_sha256": "f06f0b048777afeb3127d83172a047a42af66826ce23f5cbc6ae429dad6a40e4",
      "guide": "docs/platform/COMMON-ACCOUNT-BASE.md"
    },
    {
      "id": "tenant.context",
      "availability": "adapter_required",
      "description": "Membresías y autorización; contexto y permisos específicos por dominio",
      "package": "@nienfos/app-platform",
      "package_version": "0.1.0-dev.20-account.2",
      "artifact_sha256": "f06f0b048777afeb3127d83172a047a42af66826ce23f5cbc6ae429dad6a40e4",
      "guide": "docs/platform/COMMON-ACCOUNT-BASE.md"
    },
    {
      "id": "ui.shell",
      "availability": "adapter_required",
      "description": "Inicio, avatar y familia visual común; navegación del dominio requiere integración",
      "package": "@nienfos/app-platform",
      "package_version": "0.1.0-dev.20-account.2",
      "artifact_sha256": "f06f0b048777afeb3127d83172a047a42af66826ce23f5cbc6ae429dad6a40e4",
      "guide": "docs/platform/UX-VISUAL-V5.1.md"
    },
    {
      "id": "notifications.push",
      "availability": "adapter_required",
      "description": "SDK y configuración; entrega física exige evidencia por consumidor",
      "package": "@nienfos/notifications",
      "package_version": "0.1.0-dev.9",
      "artifact_sha256": "022f2822497b87fb3d152da408a894990f4a4325c12ff4c315908e63ef2588c5",
      "guide": "docs/platform/NOTIFICATIONS-STANDARD.md"
    },
    {
      "id": "mail.transactional",
      "availability": "adapter_required",
      "description": "Correo y transporte; recepción real separada",
      "package": "@nienfos/mail",
      "package_version": "0.1.0-dev.3",
      "artifact_sha256": "eba9caa41f3dec92d459a9171f02d6c3958c83890ae8ead1d5482294555b8aa9",
      "guide": "docs/platform/COMMON-ACCOUNT-BASE.md"
    },
    {
      "id": "payments.subscription",
      "availability": "adapter_required",
      "description": "Suscripción a Nienfos; no cuotas del negocio",
      "package": "@nienfos/payments",
      "package_version": "0.1.0-dev.1",
      "artifact_sha256": "556c29a5b0cd9f679755f563853959c2fb9bf143abbea4a875a52d2a194bb3c2",
      "guide": "docs/platform/PAYMENTS-COMMON-BASE.md"
    },
    {
      "id": "payments.checkout",
      "availability": "adapter_required",
      "description": "Checkout del negocio, TEST ONLY y adapter de órdenes",
      "package": "@nienfos/mercado-pago-checkout",
      "package_version": "0.1.0-dev.1",
      "artifact_sha256": "9299c9d19e7f92cb3a3939dce969a5a90b40ec432434fa223067d39412d80710",
      "guide": "docs/platform/PAYMENTS-COMMON-BASE.md"
    },
    {
      "id": "payments.nienfos",
      "availability": "adapter_required",
      "description": "Pagos del proyecto a Nienfos",
      "package": "@nienfos/client-collections",
      "package_version": "1.0.0-rc.20",
      "artifact_sha256": "60d6f75cbf48bc5f0efda6f37d5bba2f1caff77066f5e3f80080a0dede619975",
      "guide": "docs/platform/PAYMENTS-COMMON-BASE.md"
    },
    {
      "id": "help.tutorials",
      "availability": "adapter_required",
      "description": "Ayuda común sólo para offering_type project",
      "package": "@nienfos/tutorials",
      "package_version": "0.1.0-dev.8.4",
      "artifact_sha256": "2b4d63bd01dc0ba2e21d873e6bc70d2a75e52f51e5a437a9cd01f205f990ff41",
      "guide": "docs/platform/TUTORIALS-STANDARD.md"
    },
    {
      "id": "operations.release",
      "availability": "adapter_required",
      "description": "Operadores de publicación y configuración explícita",
      "package": "@nienfos/project-ops",
      "package_version": "0.5.0-dev.29-visual.2",
      "artifact_sha256": "d194d82315ba1424bb921696952bcc21babb099622f17f43cbf432e84ed73f16",
      "guide": "docs/platform/NEW-APP-CODEX-WORKFLOW.md"
    },
    {
      "id": "files.private",
      "availability": "proposed",
      "description": "Base general de adjuntos por consolidar",
      "package": null,
      "package_version": null,
      "artifact_sha256": null,
      "guide": null
    },
    {
      "id": "jobs.general",
      "availability": "proposed",
      "description": "Cola general por consolidar; correo tiene mecanismos propios",
      "package": null,
      "package_version": null,
      "artifact_sha256": null,
      "guide": null
    },
    {
      "id": "offline.general",
      "availability": "proposed",
      "description": "Sincronización general por consolidar",
      "package": null,
      "package_version": null,
      "artifact_sha256": null,
      "guide": null
    }
  ]
}
```

## 11. Ejemplo completo validado: gimnasio ilustrativo

SHA256 del archivo fuente: `1ff4b1533216574c6f9a3d931fc1fcd1b28ef8fce8368f88daf4e199e5b010d5`.

```json
{
  "contract": "nienfos.app-spec",
  "contract_version": "1.0.0",
  "package_id": "example.gym",
  "revision": 1,
  "status": "ready",
  "catalog_version": "2026-11-16.1",
  "product": {
    "id": "example-gym",
    "name": "Ejemplo ilustrativo de gimnasio",
    "offering_type": "product",
    "stack": "sveltekit-worker",
    "registration": "closed",
    "objective": "Ejemplo de contrato: recepción registra un socio con revisión y persistencia. No representa el relevamiento completo de Gym ni autoriza recursos.",
    "audiences": [
      "Recepción"
    ],
    "in_scope": [
      "Base compartida y un alta de socio de ejemplo"
    ],
    "out_of_scope": [
      "Cobros reales",
      "Todos los módulos del gimnasio"
    ],
    "platforms": [
      "web"
    ]
  },
  "sources": [
    {
      "id": "SRC01",
      "title": "Pedido ilustrativo, no decisión de un cliente real",
      "locator": "Texto de este ejemplo: recepción registra socio con confirmación; entrar abre Inicio y cuenta se abre desde avatar.",
      "sha256": null,
      "kind": "user"
    }
  ],
  "decisions": [
    {
      "id": "D01",
      "description": "Dirección deportiva propuesta para comparar dos composiciones.",
      "status": "proposed",
      "source_ids": [
        "SRC01"
      ],
      "blocks": "none",
      "options": [
        "Composición editorial deportiva",
        "Composición de operación compacta"
      ]
    }
  ],
  "capabilities": [
    {
      "id": "CAP01",
      "catalog_id": "identity.account",
      "required": true,
      "reason": "Reutilizar identidad, sesiones y cuenta.",
      "source_ids": [
        "SRC01"
      ],
      "configuration": {
        "registration": "closed",
        "google_client_id": null
      },
      "pending": [
        "Resolver vínculo real del consumidor y comprobar integración."
      ]
    },
    {
      "id": "CAP02",
      "catalog_id": "admin.reviewed-records",
      "required": true,
      "reason": "Adaptar confirmación y auditoría a socios.",
      "source_ids": [
        "SRC01"
      ],
      "configuration": {},
      "pending": [
        "Implementar adapter de socios con permisos y reglas propias."
      ]
    }
  ],
  "roles": [
    {
      "id": "reception",
      "name": "Recepción",
      "description": "Opera sólo los socios de su organización y sedes autorizadas."
    }
  ],
  "permissions": [
    {
      "id": "members.read",
      "action": "read",
      "resource": "member",
      "role_ids": [
        "reception"
      ],
      "scope": "organization",
      "conditions": [
        "Membresía activa y organización de sesión vigente."
      ]
    },
    {
      "id": "members.manage",
      "action": "create",
      "resource": "member",
      "role_ids": [
        "reception"
      ],
      "scope": "organization",
      "conditions": [
        "Conservar autorización hasta commit."
      ]
    }
  ],
  "entities": [
    {
      "id": "member",
      "description": "Ficha operativa mínima del ejemplo.",
      "source_ids": [
        "SRC01"
      ],
      "scope": "organization",
      "fields": [
        {
          "name": "name",
          "type": "string",
          "required": true,
          "sensitivity": "personal",
          "constraints": [
            "Nombre visible de 1 a 120 caracteres."
          ],
          "reference_entity": null,
          "values": []
        },
        {
          "name": "state",
          "type": "enum",
          "required": true,
          "sensitivity": "internal",
          "constraints": [
            "Estado controlado por operación."
          ],
          "reference_entity": null,
          "values": [
            "active",
            "archived"
          ]
        }
      ],
      "invariants": [
        "No leer ni modificar socios de otra organización.",
        "Cancelar no escribe negocio."
      ],
      "retention": "Pendiente acordar política de datos reales antes de producción; ejemplo sin datos reales."
    }
  ],
  "state_machines": [
    {
      "id": "member.lifecycle",
      "entity_id": "member",
      "states": [
        "active",
        "archived"
      ],
      "initial": "active",
      "transitions": [
        {
          "id": "member.archive",
          "from": "active",
          "to": "archived",
          "permission_ids": [
            "members.manage"
          ],
          "guards": [
            "Versión vigente y permiso actual."
          ],
          "effects": [
            "Baja recuperable y evento durable; no reactivar contrato."
          ],
          "recovery": "Restaurar sólo bajo reglas y permisos actuales."
        }
      ]
    }
  ],
  "operations": [
    {
      "id": "member.create",
      "entity_id": "member",
      "method": "create",
      "permission_ids": [
        "members.manage"
      ],
      "input_fields": [
        "name"
      ],
      "validation": [
        "Nombre no vacío y ámbito derivado de sesión."
      ],
      "review": true,
      "idempotency": "operation_id estable con recibo autoritativo; repetir no duplica.",
      "concurrency": "Revalidar sesión, membresía y revisión al confirmar.",
      "atomic_audit": true,
      "recovery": "Conservar borrador; consultar recibo después de respuesta perdida.",
      "external_effects": []
    }
  ],
  "stories": [
    {
      "id": "BASE01",
      "role_id": "reception",
      "need": "Entrar y consultar mi cuenta desde el avatar.",
      "outcome": "Llegar a Inicio y volver de cuenta sin perder organización.",
      "priority": "P0",
      "source_ids": [
        "SRC01"
      ],
      "depends_on": [],
      "acceptance_ids": [
        "BASE01-CA1"
      ],
      "capability_ids": [
        "CAP01"
      ],
      "operation_ids": [],
      "screen_ids": [
        "home",
        "account"
      ]
    },
    {
      "id": "SOC01",
      "role_id": "reception",
      "need": "Registrar una ficha de socio.",
      "outcome": "Socio persistido una sola vez en la organización correcta.",
      "priority": "P0",
      "source_ids": [
        "SRC01"
      ],
      "depends_on": [
        "BASE01"
      ],
      "acceptance_ids": [
        "SOC01-CA1",
        "SOC01-CA2",
        "SOC01-CA3"
      ],
      "capability_ids": [
        "CAP02"
      ],
      "operation_ids": [
        "member.create"
      ],
      "screen_ids": [
        "members"
      ]
    }
  ],
  "acceptance": [
    {
      "id": "BASE01-CA1",
      "story_id": "BASE01",
      "given": "Usuario legítimo con organización seleccionada",
      "when": "Ingresar y abrir avatar/cuenta y volver",
      "then": "Inicio y cuenta conservan la organización",
      "negative": "Una cuenta sin membresía no accede al negocio",
      "verification": "browser",
      "environment": "local",
      "source_ids": [
        "SRC01"
      ]
    },
    {
      "id": "SOC01-CA1",
      "story_id": "SOC01",
      "given": "Recepción autorizada y formulario válido",
      "when": "Revisar y confirmar el alta",
      "then": "La ficha persiste en su organización tras recargar",
      "negative": "Otra organización no puede consultarla",
      "verification": "browser",
      "environment": "local",
      "source_ids": [
        "SRC01"
      ]
    },
    {
      "id": "SOC01-CA2",
      "story_id": "SOC01",
      "given": "Borrador de alta",
      "when": "Cancelar revisión",
      "then": "No hay ficha nueva y se conserva el borrador",
      "negative": "Cancelar no produce escritura de negocio",
      "verification": "browser",
      "environment": "local",
      "source_ids": [
        "SRC01"
      ]
    },
    {
      "id": "SOC01-CA3",
      "story_id": "SOC01",
      "given": "Alta confirmada cuya respuesta se perdió",
      "when": "Consultar recibo y reintentar",
      "then": "Se recupera el mismo resultado sin duplicar",
      "negative": "Permiso revocado antes de commit impide escritura",
      "verification": "browser",
      "environment": "local",
      "source_ids": [
        "SRC01"
      ]
    }
  ],
  "screens": [
    {
      "id": "home",
      "title": "Inicio",
      "route": "/",
      "role_ids": [
        "reception"
      ],
      "permission_ids": [
        "members.read"
      ],
      "story_ids": [
        "BASE01"
      ],
      "purpose": "Inicio dentro del gimnasio autorizado.",
      "primary_action": "Continuar tarea contextual",
      "secondary_actions": [
        "Volver",
        "Mi cuenta"
      ],
      "operation_ids": [],
      "navigation_to": [
        "account",
        "members"
      ],
      "states": [
        {
          "name": "loading",
          "applicable": true,
          "behavior": "Mostrar espera y conservar contexto."
        },
        {
          "name": "empty",
          "applicable": true,
          "behavior": "Ofrecer alta sólo con permiso."
        },
        {
          "name": "ready",
          "applicable": true,
          "behavior": "Mostrar datos del ámbito autorizado."
        },
        {
          "name": "error",
          "applicable": true,
          "behavior": "Conservar borrador y permitir reintento."
        },
        {
          "name": "forbidden",
          "applicable": true,
          "behavior": "No mostrar datos y ofrecer volver."
        },
        {
          "name": "offline",
          "applicable": false,
          "behavior": "No se promete edición offline en este ejemplo; conservar borrador local por identidad."
        },
        {
          "name": "conflict",
          "applicable": true,
          "behavior": "Recargar versión vigente conservando cambios para revisar."
        },
        {
          "name": "pending",
          "applicable": false,
          "behavior": "Si se pierde la respuesta, consultar resultado por operation_id antes de repetir."
        }
      ],
      "responsive": "Móvil con acción visible y escritorio con densidad por tarea.",
      "accessibility": "Teclado, foco visible, labels, errores asociados y retorno de foco.",
      "motion": "Transiciones breves y respeto por prefers-reduced-motion.",
      "visual_family": "sports-admin"
    },
    {
      "id": "account",
      "title": "Mi cuenta",
      "route": "/cuenta",
      "role_ids": [
        "reception"
      ],
      "permission_ids": [
        "members.read"
      ],
      "story_ids": [
        "BASE01"
      ],
      "purpose": "Mi cuenta dentro del gimnasio autorizado.",
      "primary_action": "Continuar tarea contextual",
      "secondary_actions": [
        "Volver",
        "Mi cuenta"
      ],
      "operation_ids": [],
      "navigation_to": [
        "home",
        "members"
      ],
      "states": [
        {
          "name": "loading",
          "applicable": true,
          "behavior": "Mostrar espera y conservar contexto."
        },
        {
          "name": "empty",
          "applicable": true,
          "behavior": "Ofrecer alta sólo con permiso."
        },
        {
          "name": "ready",
          "applicable": true,
          "behavior": "Mostrar datos del ámbito autorizado."
        },
        {
          "name": "error",
          "applicable": true,
          "behavior": "Conservar borrador y permitir reintento."
        },
        {
          "name": "forbidden",
          "applicable": true,
          "behavior": "No mostrar datos y ofrecer volver."
        },
        {
          "name": "offline",
          "applicable": false,
          "behavior": "No se promete edición offline en este ejemplo; conservar borrador local por identidad."
        },
        {
          "name": "conflict",
          "applicable": true,
          "behavior": "Recargar versión vigente conservando cambios para revisar."
        },
        {
          "name": "pending",
          "applicable": false,
          "behavior": "Si se pierde la respuesta, consultar resultado por operation_id antes de repetir."
        }
      ],
      "responsive": "Móvil con acción visible y escritorio con densidad por tarea.",
      "accessibility": "Teclado, foco visible, labels, errores asociados y retorno de foco.",
      "motion": "Transiciones breves y respeto por prefers-reduced-motion.",
      "visual_family": "sports-admin"
    },
    {
      "id": "members",
      "title": "Socios",
      "route": "/socios",
      "role_ids": [
        "reception"
      ],
      "permission_ids": [
        "members.read"
      ],
      "story_ids": [
        "SOC01"
      ],
      "purpose": "Socios dentro del gimnasio autorizado.",
      "primary_action": "Continuar tarea contextual",
      "secondary_actions": [
        "Volver",
        "Mi cuenta"
      ],
      "operation_ids": [
        "member.create"
      ],
      "navigation_to": [
        "home",
        "account"
      ],
      "states": [
        {
          "name": "loading",
          "applicable": true,
          "behavior": "Mostrar espera y conservar contexto."
        },
        {
          "name": "empty",
          "applicable": true,
          "behavior": "Ofrecer alta sólo con permiso."
        },
        {
          "name": "ready",
          "applicable": true,
          "behavior": "Mostrar datos del ámbito autorizado."
        },
        {
          "name": "error",
          "applicable": true,
          "behavior": "Conservar borrador y permitir reintento."
        },
        {
          "name": "forbidden",
          "applicable": true,
          "behavior": "No mostrar datos y ofrecer volver."
        },
        {
          "name": "offline",
          "applicable": false,
          "behavior": "No se promete edición offline en este ejemplo; conservar borrador local por identidad."
        },
        {
          "name": "conflict",
          "applicable": true,
          "behavior": "Recargar versión vigente conservando cambios para revisar."
        },
        {
          "name": "pending",
          "applicable": false,
          "behavior": "Si se pierde la respuesta, consultar resultado por operation_id antes de repetir."
        }
      ],
      "responsive": "Móvil con acción visible y escritorio con densidad por tarea.",
      "accessibility": "Teclado, foco visible, labels, errores asociados y retorno de foco.",
      "motion": "Transiciones breves y respeto por prefers-reduced-motion.",
      "visual_family": "sports-admin"
    }
  ],
  "journeys": [
    {
      "id": "J01",
      "role_id": "reception",
      "story_ids": [
        "BASE01",
        "SOC01"
      ],
      "first_useful": true,
      "initial_state": "Cuenta legítima con organización autorizada; colección vacía.",
      "steps": [
        {
          "screen_id": "home",
          "action": "Ingresar mediante base común.",
          "operation_id": null,
          "expected": "Inicio conserva contexto autorizado.",
          "failure_recovery": "Error de acceso sin exponer datos."
        },
        {
          "screen_id": "members",
          "action": "Crear socio, revisar y confirmar.",
          "operation_id": "member.create",
          "expected": "Ficha guardada una sola vez.",
          "failure_recovery": "Cancelar conserva borrador; respuesta perdida se concilia antes de reintentar."
        }
      ],
      "outcome": "Recepción puede registrar y consultar un socio.",
      "persistence_proof": "Recargar y consultar en almacenamiento; otro tenant no puede leer."
    }
  ],
  "integrations": [
    {
      "id": "I01",
      "purpose": "Acceso Google cuando el consumidor esté configurado.",
      "provider": "Nienfos Acceso",
      "required": true,
      "configuration_names": [
        "GOOGLE_CLIENT_ID"
      ],
      "operation_ids": [],
      "environments": [
        "dev"
      ],
      "failure_policy": "No fingir disponibilidad; declarar configuración pendiente.",
      "verification": "Comprobación de configuración y login humano separados.",
      "pending": [
        "Resolver registro y consentimiento humano."
      ]
    }
  ],
  "visual_direction": {
    "identity": "Deportiva expresiva y legible, texto breve y cards con información útil.",
    "references": [
      "Localizar referencias con ux:find; abrir imágenes antes del piloto."
    ],
    "pilot": "J01",
    "acceptance": [
      "Comparar dos propuestas y observar familia piloto móvil/escritorio.",
      "No certificar estética por tests o por copiar este contrato."
    ],
    "tokens": {
      "brand.primary": "Por definir desde la propuesta elegida"
    }
  },
  "delivery": {
    "target": "local",
    "first_journey_id": "J01",
    "checks": [
      {
        "id": "CHECK-BASE01-CA1",
        "acceptance_ids": [
          "BASE01-CA1"
        ],
        "scenario": "Usuario legítimo con organización seleccionada; Ingresar y abrir avatar/cuenta y volver",
        "expected": "Inicio y cuenta conservan la organización; Una cuenta sin membresía no accede al negocio",
        "level": "browser",
        "environment": "local"
      },
      {
        "id": "CHECK-SOC01-CA1",
        "acceptance_ids": [
          "SOC01-CA1"
        ],
        "scenario": "Recepción autorizada y formulario válido; Revisar y confirmar el alta",
        "expected": "La ficha persiste en su organización tras recargar; Otra organización no puede consultarla",
        "level": "browser",
        "environment": "local"
      },
      {
        "id": "CHECK-SOC01-CA2",
        "acceptance_ids": [
          "SOC01-CA2"
        ],
        "scenario": "Borrador de alta; Cancelar revisión",
        "expected": "No hay ficha nueva y se conserva el borrador; Cancelar no produce escritura de negocio",
        "level": "browser",
        "environment": "local"
      },
      {
        "id": "CHECK-SOC01-CA3",
        "acceptance_ids": [
          "SOC01-CA3"
        ],
        "scenario": "Alta confirmada cuya respuesta se perdió; Consultar recibo y reintentar",
        "expected": "Se recupera el mismo resultado sin duplicar; Permiso revocado antes de commit impide escritura",
        "level": "browser",
        "environment": "local"
      }
    ],
    "evidence_policy": "Hechos por versión y ambiente; local no acredita DEV ni Google humano.",
    "backup_restore": "Ensayo independiente local; RPO/RTO reales requieren decisión del consumidor.",
    "observability": "Log seguro con correlation_id, sin credenciales ni datos personales.",
    "performance_budget": "Definir presupuesto medible al preparar el consumidor; no inventar resultados.",
    "rollout": "Validar → importar → configurar base → implementar → comprobar → publicar sólo con autorización.",
    "external_dependencies": [
      "Registro legítimo de cliente Google y usuario de comprobación."
    ]
  },
  "work_units": [
    {
      "id": "contracts",
      "owner": "generator",
      "objective": "Fijar adapter y contratos mínimos para el recorrido.",
      "stories": [
        "BASE01",
        "SOC01"
      ],
      "acceptance_ids": [
        "BASE01-CA1",
        "SOC01-CA1",
        "SOC01-CA2",
        "SOC01-CA3"
      ],
      "capability_ids": [
        "CAP01",
        "CAP02"
      ],
      "paths": [
        "src/lib/contracts"
      ],
      "depends_on": [],
      "ui": false,
      "risks": [
        "auth",
        "tenant"
      ],
      "security_risks": [
        "auth",
        "tenant"
      ],
      "kind": "contract"
    },
    {
      "id": "pilot",
      "owner": "ux",
      "objective": "Componer el recorrido piloto con base común y todas sus rutas.",
      "stories": [
        "BASE01",
        "SOC01"
      ],
      "acceptance_ids": [
        "BASE01-CA1",
        "SOC01-CA1",
        "SOC01-CA2",
        "SOC01-CA3"
      ],
      "capability_ids": [
        "CAP01",
        "CAP02"
      ],
      "paths": [
        "src/lib/ui",
        "docs/ux/evidence"
      ],
      "depends_on": [
        "contracts"
      ],
      "ui": true,
      "risks": [
        "auth",
        "tenant"
      ],
      "security_risks": [
        "auth",
        "tenant"
      ],
      "kind": "implementation"
    },
    {
      "id": "domain",
      "owner": "generator",
      "objective": "Implementar y conectar persistencia y permisos del alta.",
      "stories": [
        "BASE01",
        "SOC01"
      ],
      "acceptance_ids": [
        "BASE01-CA1",
        "SOC01-CA1",
        "SOC01-CA2",
        "SOC01-CA3"
      ],
      "capability_ids": [
        "CAP01",
        "CAP02"
      ],
      "paths": [
        "src/lib/server/members",
        "tests/members"
      ],
      "depends_on": [
        "contracts",
        "pilot"
      ],
      "ui": false,
      "risks": [
        "auth",
        "tenant"
      ],
      "security_risks": [
        "auth",
        "tenant"
      ],
      "kind": "implementation"
    }
  ],
  "extensions": {
    "x-example.notice": "Ejemplo pequeño; no reduce ni sustituye el relevamiento real."
  },
  "api_contracts": [
    {
      "id": "API-MEMBER-CREATE-review",
      "operation_id": "member.create",
      "method": "POST",
      "path": "/api/members/review",
      "request_fields": [
        "name"
      ],
      "response": "Respuesta exacta según response_schema; permisos, actor y ámbito se revalidan en servidor. GET usa query; POST usa JSON.",
      "errors": [
        {
          "code": "invalid_input",
          "http_status": 422,
          "meaning": "Nombre inválido.",
          "recovery": "Conservar borrador y asociar error al campo."
        },
        {
          "code": "forbidden",
          "http_status": 403,
          "meaning": "Permiso o ámbito revocado.",
          "recovery": "No escribir y actualizar capacidades."
        },
        {
          "code": "revision_conflict",
          "http_status": 409,
          "meaning": "Datos cambiaron entre revisión y commit.",
          "recovery": "Recargar revisión conservando borrador."
        }
      ],
      "session_required": true,
      "csrf_required": true,
      "permission_ids": [
        "members.manage"
      ],
      "phase": "review",
      "request_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "required": [
          "name"
        ]
      },
      "response_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "review_id": {
            "type": "string",
            "minLength": 1
          },
          "expires_at": {
            "type": "string",
            "format": "date-time"
          },
          "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          },
          "expected_revision": {
            "type": "integer",
            "minimum": 0
          }
        },
        "required": [
          "review_id",
          "expires_at",
          "summary",
          "expected_revision"
        ]
      }
    },
    {
      "id": "API-MEMBER-CREATE-commit",
      "operation_id": "member.create",
      "method": "POST",
      "path": "/api/members/commit",
      "request_fields": [
        "review_id",
        "operation_id"
      ],
      "response": "Respuesta exacta según response_schema; permisos, actor y ámbito se revalidan en servidor. GET usa query; POST usa JSON.",
      "errors": [
        {
          "code": "invalid_input",
          "http_status": 422,
          "meaning": "Nombre inválido.",
          "recovery": "Conservar borrador y asociar error al campo."
        },
        {
          "code": "forbidden",
          "http_status": 403,
          "meaning": "Permiso o ámbito revocado.",
          "recovery": "No escribir y actualizar capacidades."
        },
        {
          "code": "revision_conflict",
          "http_status": 409,
          "meaning": "Datos cambiaron entre revisión y commit.",
          "recovery": "Recargar revisión conservando borrador."
        }
      ],
      "session_required": true,
      "csrf_required": true,
      "permission_ids": [
        "members.manage"
      ],
      "phase": "commit",
      "request_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "review_id": {
            "type": "string",
            "minLength": 1
          },
          "operation_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "required": [
          "review_id",
          "operation_id"
        ]
      },
      "response_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          },
          "version": {
            "type": "integer",
            "minimum": 1
          },
          "operation_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          },
          "status": {
            "const": "confirmed"
          }
        },
        "required": [
          "id",
          "version",
          "operation_id",
          "status"
        ]
      }
    },
    {
      "id": "API-MEMBER-CREATE-cancel",
      "operation_id": "member.create",
      "method": "POST",
      "path": "/api/members/cancel",
      "request_fields": [
        "review_id"
      ],
      "response": "Respuesta exacta según response_schema; permisos, actor y ámbito se revalidan en servidor. GET usa query; POST usa JSON.",
      "errors": [
        {
          "code": "invalid_input",
          "http_status": 422,
          "meaning": "Nombre inválido.",
          "recovery": "Conservar borrador y asociar error al campo."
        },
        {
          "code": "forbidden",
          "http_status": 403,
          "meaning": "Permiso o ámbito revocado.",
          "recovery": "No escribir y actualizar capacidades."
        },
        {
          "code": "revision_conflict",
          "http_status": 409,
          "meaning": "Datos cambiaron entre revisión y commit.",
          "recovery": "Recargar revisión conservando borrador."
        }
      ],
      "session_required": true,
      "csrf_required": true,
      "permission_ids": [
        "members.manage"
      ],
      "phase": "cancel",
      "request_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "review_id": {
            "type": "string",
            "minLength": 1
          }
        },
        "required": [
          "review_id"
        ]
      },
      "response_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "cancelled": {
            "const": true
          }
        },
        "required": [
          "cancelled"
        ]
      }
    },
    {
      "id": "API-MEMBER-CREATE-receipt",
      "operation_id": "member.create",
      "method": "GET",
      "path": "/api/members/receipt",
      "request_fields": [
        "operation_id"
      ],
      "response": "Respuesta exacta según response_schema; permisos, actor y ámbito se revalidan en servidor. GET usa query; POST usa JSON.",
      "errors": [
        {
          "code": "invalid_input",
          "http_status": 422,
          "meaning": "Nombre inválido.",
          "recovery": "Conservar borrador y asociar error al campo."
        },
        {
          "code": "forbidden",
          "http_status": 403,
          "meaning": "Permiso o ámbito revocado.",
          "recovery": "No escribir y actualizar capacidades."
        },
        {
          "code": "revision_conflict",
          "http_status": 409,
          "meaning": "Datos cambiaron entre revisión y commit.",
          "recovery": "Recargar revisión conservando borrador."
        }
      ],
      "session_required": true,
      "csrf_required": false,
      "permission_ids": [
        "members.manage"
      ],
      "phase": "receipt",
      "request_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "operation_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "required": [
          "operation_id"
        ]
      },
      "response_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "operation_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          },
          "status": {
            "enum": [
              "pending",
              "confirmed",
              "rejected"
            ]
          },
          "entity_id": {
            "type": [
              "string",
              "null"
            ]
          },
          "version": {
            "type": [
              "integer",
              "null"
            ]
          }
        },
        "required": [
          "operation_id",
          "status",
          "entity_id",
          "version"
        ]
      }
    }
  ]
}
```

## 12. Esquema exacto de recibo del operador

SHA256 del archivo fuente: `1b43e80881f994036575e2cd6517a29619d075c2d6c9306379b14931223d8a76`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:nienfos:foundation-receipt:1.0.0",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "contract": {
      "const": "nienfos.foundation-receipt"
    },
    "contract_version": {
      "const": "1.0.0"
    },
    "bundle_sha256": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$"
    },
    "capabilities": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,79}$"
          },
          "artifact_sha256": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ]
          },
          "installed": {
            "type": "boolean"
          },
          "configured": {
            "type": "boolean"
          },
          "published": {
            "type": "boolean"
          },
          "verified": {
            "type": "boolean"
          },
          "environment": {
            "enum": [
              "local",
              "dev",
              "qa",
              "prod"
            ]
          },
          "origin": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ]
          },
          "release_id": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ]
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "path": {
                  "type": "string",
                  "minLength": 1
                },
                "sha256": {
                  "type": "string",
                  "pattern": "^[a-f0-9]{64}$"
                },
                "observed_at": {
                  "type": "string",
                  "format": "date-time"
                },
                "result": {
                  "enum": [
                    "pass",
                    "fail",
                    "inconclusive"
                  ]
                }
              },
              "required": [
                "path",
                "sha256",
                "observed_at",
                "result"
              ]
            },
            "minItems": 0
          }
        },
        "required": [
          "id",
          "artifact_sha256",
          "installed",
          "configured",
          "published",
          "verified",
          "environment",
          "origin",
          "release_id",
          "evidence"
        ]
      },
      "minItems": 0
    }
  },
  "required": [
    "contract",
    "contract_version",
    "bundle_sha256",
    "capabilities"
  ]
}
```
