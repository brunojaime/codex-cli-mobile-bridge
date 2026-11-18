> Estado de implementación actualizado: ver [coordinador y pruebas](work-coordinator.md). Las secciones históricas siguientes describen la propuesta y pueden incluir capacidades posteriores al primer piloto.

# Agente proactivo de proyectos — propuesta

Actualizado el 5 de noviembre de 2026 según la conversación. Diseño; no activa
servicios, modelos, notificaciones ni ejecuciones.

## Idea central

Un agente supervisor se despierta periódicamente, observa un proyecto con sus
herramientas, recuerda lo que vio y decide si corresponde hacer algo. Puede
investigar, formular una pregunta, proponer una mejora o guardar silencio.
El seguimiento de pedidos y publicaciones es una capacidad más, no el eje del
sistema ni un flujo obligatorio de estados para todo el trabajo.

La continuidad pertenece al servicio y su memoria durable. Cada despertar usa
una ejecución acotada del modelo; no necesita un proceso de inferencia permanente.
Puede haber un mismo supervisor lógico para muchos proyectos, con memoria y
política separadas por proyecto.

## Ciclo de observación y decisión

1. Un programador durable selecciona un proyecto cuyo próximo despertar venció.
   Un evento relevante también puede adelantar una revisión.
2. El agente recibe objetivos, contexto resumido, observaciones previas,
   propuestas abiertas, respuestas del usuario y actividad de ejecutores.
3. Consulta herramientas de lectura según lo que necesita averiguar: archivos,
   chats autorizados, relevamientos, WhatsApp, GitHub, publicaciones, feedback,
   Calendar o comprobaciones de la aplicación disponibles.
4. Razona qué merece atención. Puede profundizar una investigación acotada antes
   de decidir; no depende exclusivamente de detectores predeterminados.
5. Devuelve una decisión estructurada: silencio, continuar investigación,
   preguntar, proponer o seguir una ejecución ya autorizada. Incluye fundamento,
   referencias, cambios respecto de la revisión anterior y próxima revisión.
6. El coordinador persiste memoria, valida límites y permisos y entrega sólo las
   decisiones útiles a la bandeja. Una salida del modelo no ejecuta código por sí sola.

El agente debe poder descubrir oportunidades aunque no exista un pedido previo.
Ejemplos: una parte de la aplicación confusa, problemas recurrentes, trabajo
repetido que se podría automatizar, falta de cobertura de un recorrido importante
o una oportunidad que surge de combinar conversaciones y estado del proyecto.
Son hipótesis hasta contar con evidencia; no inventar usuarios ni métricas.

## Silencio como resultado normal

Si nada merece atención, no se crea una notificación ni un chat. Se guarda una
bitácora interna consultable: qué revisó, qué no pudo consultar y cuándo volverá.
No hay resumen diario obligatorio ni cuota de sugerencias.

Una propuesta abierta no vuelve a notificarse en cada despertar. Recordar
posposiciones, descartes y motivos; volver sobre el tema sólo con novedades
materiales o un recordatorio acordado. Un fallo aislado de una fuente se registra;
una pérdida persistente de observación puede merecer un aviso operativo agrupado.

Propuesta inicial configurable: despertar cada hora por proyecto, con revisiones
más espaciadas cuando no hay actividad. Tras un evento importante, adelantar la
revisión; tras una posposición, respetarla. Mantener alguna exploración periódica
aunque no haya eventos para descubrir mejoras nuevas. Son valores de diseño,
no frecuencias ya habilitadas. Limitar herramientas, duración y gasto por despertar.

## Memoria por proyecto

Conservar objetivos y prioridades, contexto de producto, fuentes autorizadas,
observaciones con evidencia, incertidumbres, decisiones del usuario, propuestas
abiertas y descartadas, investigaciones pendientes y ejecuciones en curso.

Cada despertar puede ser efímero. La memoria no debe depender de un chat infinito:
resumen compacto más referencias recuperables. Las fuentes externas son evidencia,
no autorizaciones. Mostrar antigüedad de la información y fuentes inaccesibles.

## Propuesta y ejecución desde el teléfono

Una propuesta dice qué encontró, por qué conviene actuar, qué resultado busca y
qué ejecución recomienda. Puede pedir una decisión si el alcance es ambiguo.
Acciones: ejecutar propuesta, ajustar alcance, responder, posponer o descartar.

Al elegir ejecutar, el backend congela la versión de la propuesta, alcance,
workspace, presupuesto y autorizaciones aplicables. El agente prepara prompts y
contexto autosuficiente para el ejecutor. El usuario puede responder en lenguaje
natural; no necesita redactar el encargo técnico.

El supervisor elige y justifica una modalidad, dentro de la política del proyecto:

| Modalidad | Cuándo conviene | Ejemplo orientativo |
| --- | --- | --- |
| Generator solo | Investigación o tarea pequeña con cierre claro | Un encargo acotado |
| Generator + Reviewer | Cambio que merece comprobación independiente | Hasta 3 turnos de Generator y 2 de Reviewer |
| Plan con varias tandas | Trabajo con etapas y decisiones intermedias | Investigar; implementar y revisar; corregir si hace falta |

Los números son ejemplos, no presupuestos ya autorizados. El agente propone un
máximo, motivo y criterio de cierre; el usuario o una política previa lo limita.
Turnos por agente y cantidad de tandas son conceptos distintos.

Después de cada tanda se inspecciona el resultado real y se decide terminar,
continuar dentro del plan autorizado o preguntar si cambió el alcance. No consumir
el presupuesto por obligación, ampliar límites automáticamente ni encadenar
planes sin fin. Ante falta de progreso, detener y explicar el bloqueo.

El agente que observa no implementa durante una revisión ordinaria. Después de
la ejecución, vuelve a observar el proyecto e incorpora resultados y aprendizajes.
Publicaciones y contactos externos respetan la autorización correspondiente;
un permiso para implementar no incluye por sí solo esas acciones.

## Qué podemos reutilizar y qué falta

- [WhatsApp Intake](whatsapp-agentic-intake.md) y
  [relevamientos](relevamientos/automaticos/PROPUESTA.md) aportan contexto y fuentes.
  Sus políticas vigentes se conservan. No se verificó su operación en este turno.
- [Kanban](../backend/app/application/services/sdd_workbench_kanban_service.py)
  aporta una proyección determinística y evidencia; el supervisor agrega criterio
  abierto, memoria de decisiones y observación de proyectos sin la app abierta.
- [Actualizaciones](../backend/app/application/services/app_update_service.py) y
  [feedback](../backend/app/application/services/feedback_queue_service.py)
  aportan información para consultas concretas, sin imponer un único flujo.
- [Generator/Reviewer](generator-reviewer-launch.md) ya recibe prompts y límites
  independientes por agente. Su lanzador actual habilita ambos agentes y permite
  un lanzamiento por mensaje humano: no ofrece todavía el plan de varias tandas
  ni la modalidad Generator solo mediante ese mismo contrato.
- Calendar tiene herramientas en este chat; falta comprobar o implementar acceso
  desde el servicio autónomo. Un conector de sesión no garantiza ese acceso.

Agregar un servicio de supervisor, persistencia de memoria y despertares,
contrato estructurado de decisiones, bandeja de propuestas y coordinador de planes.
Reutilizar el motor de agentes para ejecutar en lugar de crear otro motor.
El supervisor necesita un perfil propio con herramientas y permisos acotados;
el analizador de relevamientos actual deshabilita conectores y no lo reemplaza.

Para varias tandas, crear una entidad de plan con aprobación ligada a la versión
concreta de la propuesta y claves de ejecución por paso. No inventar mensajes
humanos para eludir el contrato actual. Adaptar el backend para ejecutar estos
planes explícitamente, manteniendo la ruta de lanzamiento manual existente.

## Operación y primera entrega

El programador guarda próxima revisión y recupera pendientes tras reinicios.
Evitar dos despertares simultáneos del mismo proyecto y una segunda escritura
sobre un workspace ocupado. Registrar envíos antes de ejecutarlos y conciliar
resultados inciertos antes de reintentar. Separar presupuesto de observación y
ejecución, con máximos por proyecto y globales y opción de pausar.

Primera entrega: piloto con dos proyectos, supervisor con herramientas de lectura,
memoria durable, despertares y decisiones silencio/pregunta/propuesta; bandeja
que permita ejecutar Generator solo o un ciclo Generator/Reviewer con presupuesto
explícito. Las varias tandas son la ampliación siguiente del mismo diseño.

Validar que: el agente descubre un caso útil fuera de reglas fijas; permanece en
silencio cuando corresponde; no repite propuestas; recuerda respuestas y
posposiciones; se recupera de reinicios; respeta herramientas y presupuestos;
la aprobación ejecuta exactamente la propuesta vista una sola vez; y una ejecución
terminada vuelve a alimentar la memoria del supervisor. Medir utilidad de las
propuestas, ruido, costo y progreso logrado, sin premiar cantidad de avisos.

## Avance: maqueta del frontend

Se implementó una vista de prueba local con campana, aviso simulado, detalle,
ejecución simulada, rechazo y observaciones persistentes en el dispositivo.
Ver [recorrido, capturas y validación](../reports/proactive-notification-mock/README.md).
Todavía no activa el supervisor, push ni encargos reales a agentes.

## Avance: flujo real de propuestas

El 5 de noviembre se implementaron persistencia de propuestas en backend,
lectura, versiones, decisiones y ejecución idempotente con Generator/Reviewer.
La campana consume esta bandeja real; la maqueta queda separada.
Ver [contrato y estado de implementación](agent-proposals.md). Requiere despliegue
y APK actualizado; el supervisor y el transporte push con la app cerrada siguen
siendo etapas posteriores.

## Operación nocturna: avanzar sin depender de otro mensaje

Requisito incorporado el 5 de noviembre: el usuario debe poder cerrar el día y
descansar sin despertarse para reactivar proyectos. El supervisor debe elegir y
encadenar trabajo útil durante la noche, revisar resultados y cambiar de proyecto
si se bloquea. La actividad y las decisiones quedan explicadas al día siguiente.
No se busca ocupar todos los minutos ni consumir tokens por estar despierto.

### Ventana y continuidad

Propuesta inicial: 22:30–08:00 en `America/Argentina/Buenos_Aires`, configurable
dentro del inicio aproximado 22–23 solicitado. La ventana cruza medianoche; una
misma jornada nocturna conserva identidad, presupuesto y registro al cambiar
la fecha. No depender de que el chat ni el teléfono permanezcan abiertos.

Un servicio persistente mantiene próximos despertares y trabajos. Esperar hasta
el próximo evento o vencimiento lo hace el sistema operativo, sin invocar al
modelo. El último turno del chat no queda esperando como mecanismo de operación.
La máquina y el motor de ejecución deben estar disponibles; una caída se conserva
como interrupción y se recupera sin duplicar encargos.

### Elegir trabajo útil

Un registro de proyectos habilitados guarda objetivos, prioridades del usuario,
pedidos y tareas pendientes, evidencia reciente, bloqueos, criterios de cierre,
autorizaciones y presupuesto. No incluir proyectos archivados o pausados por
inferencia. La asociación de chats, relevamientos y código tiene que ser confiable.

Al iniciar la noche, preparar una cola breve de candidatos:

1. Continuar trabajo previamente autorizado que quedó incompleto, si no está
   ejecutándose ya y su alcance sigue siendo válido.
2. Resolver pedidos aprobados, fallos reproducibles o bloqueos técnicos para
   los que existe autorización y una salida verificable.
3. Hacer mejoras de calidad dentro de categorías habilitadas para ese proyecto.
4. Explorar oportunidades con una investigación acotada cuando falta trabajo
   ejecutable conocido; lo que requiere una decisión queda como propuesta.

Elegir con impacto esperado, prioridad del usuario, evidencia, urgencia, esfuerzo,
dependencias y posibilidad de terminar un avance útil esa noche. Evitar que un
proyecto monopolice recursos por acumular tareas pequeñas; justificar la selección
y reservar oportunidades para otros proyectos habilitados. No alternar por reloj
si continuar una tarea importante sigue siendo la mejor decisión.

Cada encargo describe resultado esperado, cómo comprobarlo, alcance y límites.
No seleccionar genéricamente «seguir mejorando» sin concretar qué vale la pena.
La ausencia de una tarea conocida no obliga a inventar un problema.

### Autonomía que no requiera levantarse a aprobar

Además de propuestas con botón Ejecutar, agregar una política permanente por
proyecto: qué trabajo puede investigar, preparar o ejecutar solo durante la noche,
con qué límites y qué debe reservar para una decisión humana. Reutilizar las
autorizaciones válidas que ya existan; no exigir otra aprobación cada noche.

Ejemplos de categorías que podrían habilitarse: completar tareas acordadas,
corregir fallos reproducibles, pruebas de recorridos importantes y mejoras locales
de usabilidad. La habilitación concreta y el alcance deben quedar registrados;
estos ejemplos no activan categorías ni conceden permisos por sí mismos.

Las publicaciones en DEV y el push a GitHub tienen autorización permanente según
el requisito de cierre incorporado más abajo. Otros destinos, cambios de producto
ambiguos y comunicaciones externas siguen su autorización aplicable.
Si falta una decisión, guardar una pregunta con recomendación
y pasar a otro trabajo permitido. No despertar al usuario para destrabar una tarea
ordinaria. Respetar instrucciones específicas del proyecto y descartes anteriores.

La aceptación manual y la ejecución por política son orígenes diferentes de
autorización. Agregar al backend el segundo camino con política/versiones y auditoría;
no llamar al endpoint de decisión simulando un toque humano, ni inventar mensajes
de origen. La ruta actual de propuestas por sí sola no habilita esta autonomía.

### Ciclo nocturno

Observar cambios relevantes → elegir próximo avance → ejecutar con presupuesto
→ revisar resultados → actualizar memoria → continuar, elegir otro proyecto o dormir.

El supervisor elige Generator solo, un ciclo Generator/Reviewer o un plan acotado
de etapas según el trabajo. Después de cada etapa evalúa el resultado: no es una
cantidad fija de rondas que deban consumirse. Una revisión que sólo repite pedidos
sin progreso agota su límite y deriva un bloqueo; no renueva su propio presupuesto.

Comenzar con un único encargo de escritura simultáneo como configuración propuesta.
El límite global y el bloqueo por workspace deben cubrir también los otros caminos
de ejecución para evitar carreras con trabajos manuales. La comprobación de ocupado
que ya tiene la bandeja es una base, no esa garantía global todavía.

Ante un bloqueo, el supervisor distingue entre un fallo técnico que puede resolver,
una decisión humana pendiente, falta de acceso y agotamiento de recursos. Sólo el
primer caso admite un intento acotado dentro del alcance; los demás permiten
cambiar de tarea o dormir hasta que algo relevante cambie.

### Presupuesto y sueño

Limitar por noche, proyecto y encargo: turnos, llamadas de análisis, duración y
costo cuando exista medición confiable. Reservar presupuesto para revisar y cerrar
el trabajo; no gastarlo todo implementando. Los valores se configuran antes de
activar la operación, sin inventar que ya hay un límite económico en funcionamiento.

Antes de llamar al modelo, consultar señales baratas: hay trabajo en curso, apareció
información nueva, venció una revisión o cambió un bloqueo. Recuperar sólo contexto
relevante y usar resúmenes con referencias, sin releer todos los repositorios a cada
despertar. La exploración sin eventos tiene su propio presupuesto y frecuencia.

Si hay un ejecutor activo, seguir su actividad y puntos de control sin iniciar
otra escritura sobre el mismo workspace; evaluar su resultado antes de encadenar
el siguiente encargo. Si todos los trabajos posibles
están bloqueados, no hay una oportunidad defendible o falta presupuesto, guardar
motivo y próxima revisión y dormir. Una espera de 30–60 minutos es un ejemplo
configurable, no un valor ya activo. Reabrir por un cambio o vencimiento justificado,
no para pedir repetidamente al modelo que mire lo mismo.

Sin datos confiables de consumo, usar topes verificables de turnos/llamadas y
declarar esa limitación. No prometer un tope monetario exacto que no se pueda medir.

### Cierre de la noche y confianza

Cerca de las 08:00, no iniciar un encargo que no quepa en el tiempo y presupuesto
restantes. El cierre debe ser ordenado, sin matar procesos de escritura a la hora
en punto. Si se permite terminar una etapa iniciada fuera de la ventana, ese margen
debe estar definido y ser visible; no se extiende la noche indefinidamente.

La app muestra proyecto actual, tarea, último avance comprobado, si está trabajando,
esperando, bloqueado o dormido, próxima revisión y presupuesto disponible. Una señal
de vida del proceso no equivale a progreso: detectar estancamientos y registrar el
motivo real para que «activo» no sea una falsa tranquilidad.

Guardar un cierre nocturno aun si no hubo cambios: qué mejoró y cómo se comprobó,
qué quedó preparado, por qué se detuvo y las decisiones concretas pendientes. Separar
implementado, revisado y publicado cuando aplique. El informe puede estar en la app
sin emitir una notificación si no aporta una novedad útil. Durante la noche, silencio
para propuestas ordinarias; cualquier excepción debe configurarse explícitamente.

### Primera entrega nocturna y aceptación

Integrar un servicio durable con horario, catálogo de proyectos, memoria y cola;
una política de ejecución autónoma por proyecto; presupuestos; coordinación del
motor y recuperación; estado operativo y cierre de la noche. Reutilizar la bandeja
y el motor existentes. Un proceso que sólo genera notificaciones no cumple.

Validar en dos proyectos seleccionados para el piloto, primero con ejecuciones
controladas y luego con una noche real dentro de un presupuesto acordado:

- Continúa una tarea autorizada sin necesitar otro mensaje humano.
- Revisa un resultado y elige justificadamente el siguiente avance.
- Si un proyecto se bloquea, trabaja en otro autorizado sin insistir ni avisar
  repetidamente al usuario.
- Dormir no genera llamadas al modelo; una espera o reinicio no duplica trabajos.
- Respeta proyectos pausados, límites, horarios y exclusión de escrituras.
- Si nada útil puede avanzar, explica por qué y permanece en espera.
- A la mañana existe un cierre con evidencia de resultados y consumo conocido.

Éxito: avances útiles y verificables sin intervención nocturna del usuario.
La cantidad de mensajes, horas de modelo o tokens consumidos no es una medida de éxito.

Estado actual: este apartado amplía el diseño. No se implementó ni activó todavía
el servicio nocturno, su política autónoma ni su programación.

## Supervisión del trabajo y página de mañana

Ampliación del 5 de noviembre: el usuario necesita entender el resultado con poco
texto, ver el camino y elegir entre próximos pasos concretos. El resumen es un
módulo de producto con datos y acciones, no una transcripción comprimida del chat.

### Organización recomendada de supervisores

Un coordinador global mantiene horario, presupuesto, prioridades, disponibilidad
de proyectos y exclusión de ejecuciones. Cada proyecto tiene su propio contexto
de supervisión y memoria. Es una separación de responsabilidades y estado; no
implica mantener un modelo distinto ejecutándose continuamente por proyecto.

El supervisor del proyecto se invoca cuando hay algo que interpretar: un resultado,
hallazgo del Reviewer, bloqueo, cambio relevante o revisión programada. Comprende
el objetivo, sigue Generator/Reviewer, identifica qué falta y decide la continuación
permitida. El coordinador global decide dónde conviene asignar recursos después.
Comenzar con esta estructura lógica y un ejecutor de escritura simultáneo; ampliar
concurrencia sólo cuando haya evidencia de que mejora los avances y el costo.

Durante un trabajo, un monitor barato observa estado, actividad, hitos y fallos.
No esperar ciegamente hasta el final ni releer toda la conversación cada pocos
segundos. Si falta actividad, comprobar primero si el proceso está esperando una
herramienta o está bloqueado; recién entonces llamar al supervisor si hace falta.

Al recibir un hallazgo del Reviewer, el supervisor puede preparar una corrección
precisa para el próximo turno, comprobar si ya se resolvió o cerrar el objetivo.
La continuación respeta los turnos y el alcance autorizados. No lanzar otro chat
sobre archivos que se están modificando ni convertir la supervisión en una revisión
adicional automática de todos los turnos. Las intervenciones durante una ejecución
usan puntos de control y mecanismos de control soportados por el motor.

### Página «Tu noche», primero en Codex Bridge

Integrarla primero en Bridge, junto a propuestas y chats, para reutilizar estado,
evidencias y acciones. Mantener el contrato de datos independiente de la pantalla
para poder mostrarlo también en Gestión más adelante, sin duplicar el coordinador.

La primera vista debe poder comprenderse en aproximadamente un minuto:

- Franja superior: noche y horario, actualización del informe, si sigue trabajando
  y balance breve: avances comprobados, proyectos bloqueados y decisiones pendientes.
- Hasta tres tarjetas prioritarias visibles: proyecto, qué cambió, estado real,
  evidencia visual si corresponde y próximo paso recomendado.
- «Ver todos los proyectos» para el resto, sin expandir todo de entrada.
- «Necesita tu decisión» prioriza las opciones que permiten destrabar trabajo.

Presupuesto editorial propuesto: no más de 120–150 palabras en el resumen textual
de entrada, sin contar nombres, botones y etiquetas. Cada tarjeta dedica como
máximo dos frases a resultado y próximo paso. No rellenar con saludos, cronología
de herramientas, cantidades de tokens o detalles de implementación.

Separar «Qué cambió», «Cómo se comprobó» y «Qué sigue». No mostrar verde de éxito
si sólo existe un cambio de código sin comprobación. Si no hubo avances, expresar
el motivo y la decisión útil pendiente, sin presentar actividad como resultado.

### Evidencia visual y camino recorrido

Para cambios visibles, mostrar capturas reales de antes y después, con el mismo
recorrido, tamaño de pantalla y datos de prueba comparables. Una leyenda corta
señala qué mirar. No fabricar imágenes de una mejora no ejecutada ni mostrar
datos privados o secretos en las capturas.

Para cambios que no se ven, usar una prueba comprensible: «el borrador se conserva
al reconectar», junto al resultado y su evidencia técnica expandible. No inventar
un antes/después visual de un cambio de backend.

«Ver recorrido» expande de tres a cinco hitos con evidencia: qué encontró, qué
intentó, qué cambió a partir de la revisión y dónde terminó. El registro completo
y los chats quedan a un nivel más profundo. No convertir cada turno del modelo
o comando en un hito de la página principal.

Remotion es una opción a evaluar para una explicación visual posterior, no una
dependencia de este módulo. Primero capturas, comparación y recorrido breve.
No se solicitó producir un video en este turno: no cargar la skill de video,
encolar trabajos, invocar modelos audiovisuales ni renderizar automáticamente.
Si se pide expresamente un video, seguir el flujo compartido de videos y validar
la función real antes de grabar. La página debe entenderse sin ver un video.

### Decisiones que se convierten en el próximo encargo

Cada decisión presenta de dos a tres opciones sustantivas, una recomendada con
motivo breve. Evitar reducir todas las decisiones a «Ejecutar / Frenar» o formular
preguntas abiertas que obliguen al usuario a redactar otro prompt técnico.

Ejemplo ficticio: ante un problema de reconexión, ofrecer «Completar la recuperación
del borrador» o «Investigar primero el modo sin conexión», con resultado esperado,
diferencia de alcance y presupuesto máximo de cada alternativa. Permitir posponer
la decisión o escribir una observación sin obligar a elegir una ejecución.

Las opciones son planes concretos y versionados, con instrucciones, límites,
dependencias y criterios de cierre. Al elegir, registrar selección y autorización,
devolver un recibo claro y entregar el encargo al supervisor para ejecutarlo o
encolarlo. Un reintento no genera dos encargos. No exigir un segundo mensaje humano
que repita la opción ya elegida.

Si el usuario abre la página a las 07:00 y el trabajo sigue activo, mostrar qué está
ocurriendo y dónde se aplicaría su decisión. Encolar el nuevo paso detrás del trabajo
actual o aplicar el cambio en un punto seguro; no introducir otra escritura en paralelo.
Si cambió el contexto y la alternativa dejó de ser válida, actualizar la propuesta
y explicar el cambio antes de ejecutar otro alcance.

La página tiene actualización visible y distingue la foto de cierre nocturno del
estado actual. Elegir una opción queda reflejado como «En cola», «En curso» o
«Necesita revisión», con acceso al trabajo. No cerrar el ciclo mostrando sólo
«respuesta recibida» sin poder seguir qué pasó después.

### Contratos y aceptación de este módulo

El cierre nocturno conserva resultados estructurados por proyecto, estado,
evidencias, hitos y decisiones. Cada decisión contiene opciones con identidad y
versión, recomendación, costo conocido o límite operativo y referencia al plan.
La selección se liga al estado del proyecto que se mostró. El registro de eventos
es la fuente de verdad; el modelo puede redactar textos breves, sin inventar hechos.

La bandeja actual permite una propuesta y sus tres respuestas. Falta ampliar su
contrato para varias alternativas, selección idempotente y seguimiento de planes;
no afirmar que las opciones ya están ejecutables por haber dibujado sus botones.

Validar comprensión y acción con un recorrido corto: identificar un avance real,
ver la evidencia, entender un bloqueo y elegir el siguiente paso sin leer chats.
Probar muchos proyectos, cero avances, capturas faltantes, trabajos aún activos,
una opción vencida, doble toque y recuperación tras perder la confirmación.

Estado: se incorpora al diseño. No se implementó todavía la página «Tu noche»,
la selección de alternativas ni la supervisión nocturna.

## Cierre obligatorio: GitHub y DEV actualizados

Requisito y autorización del usuario incorporados el 5 de noviembre de 2026:
los avances terminados de los proyectos habilitados deben quedar pusheados en
GitHub y publicados en su ambiente DEV. El usuario debe poder abrir esos DEV por
la mañana y ver los cambios de la noche. No alcanza con dejar código local o un
informe. Esto es parte del encargo nocturno, sin volver a pedir aprobación por
cada push o publicación en DEV dentro del alcance autorizado.

La autorización comprende DEV exclusivamente. No habilita QA, producción ni
promociones automáticas hacia otros ambientes. La política identifica por proyecto
el repositorio, rama de trabajo/DEV, workflow o procedimiento de despliegue,
servicios implicados y destinos verificables. Antes de usar una ruta de publicación,
comprobar también los disparadores posteriores: un push que inicia producción no
se vuelve válido por haberse presentado como un despliegue de DEV.

### Responsabilidad del supervisor

Por cada avance, completar el circuito: implementar → comprobar → guardar un
commit identificable → confirmar push remoto → publicar en DEV → comprobar la
versión servida y el recorrido afectado. La publicación de DEV puede estar a cargo
de un ejecutor específico; el supervisor sigue siendo responsable de verificar
el cierre y atender los fallos dentro del presupuesto.

En cada proyecto, revisar también cambios válidos previamente terminados que
quedaron sin push o sin DEV, evitando volver a implementarlos. No incorporar
automáticamente archivos desconocidos o cambios sin revisar a un commit colectivo.
Los experimentos o trabajos incompletos se conservan en una rama de trabajo
adecuada y se identifican como pendientes; no se convierten en una versión DEV
rota sólo para afirmar que se publicó «lo último».

Si el cambio afecta frontend, backend y otros servicios, seguir el procedimiento
del proyecto para desplegar el conjunto compatible. Verificar configuración y
datos reales del DEV previsto; no sustituirlos por una maqueta ni tocar datos o
servicios de producción. Para apps nativas, registrar además el artefacto/canal DEV
correspondiente; publicar el APK no acredita que ya esté instalado en el teléfono.

Un workflow iniciado o en verde es evidencia del proceso, no suficiente por sí
solo para asegurar que la aplicación muestra el cambio. Conservar commit remoto,
identidad del despliegue o artefacto, destino DEV y comprobación del comportamiento.
Si la plataforma publica un artefacto derivado, registrar su relación con el commit
para poder demostrar qué versión quedó sirviendo cada servicio.

### Fallos y cierre de la noche

Reservar tiempo y presupuesto para subir, desplegar y comprobar; no dedicar toda
la ventana a generar cambios que luego quedan locales. Antes de terminar la noche,
conciliar la cartera completa de proyectos habilitados y señalar cualquier avance
sin push o DEV, incluso si su ejecutor terminó antes.

Si falla el push, una validación o la publicación, intentar una recuperación acotada
cuando corresponda y no marcar el proyecto como terminado. No eludir comprobaciones,
forzar una rama protegida ni sustituir producción por DEV. Mantener o recuperar la
última versión funcional de DEV cuando el procedimiento del proyecto lo permita.
Guardar el bloqueo concreto y el próximo paso si no puede completar el cierre.

La página «Tu noche» ofrece por proyecto una indicación breve: **GitHub actualizado**,
**DEV actualizado y comprobado**, **DEV pendiente** o **bloqueado**, con enlaces al
DEV y al cambio remoto. No exige leer logs para saber si se puede probar la mejora.
Las decisiones de continuación aparecen junto al estado real de entrega.

### Cambio necesario respecto del código existente

El ejecutor actual de propuestas agrega una restricción general de no publicar.
Al implementar la política nocturna hay que adaptarlo para recibir autorización
explícita y acotada a los destinos DEV del proyecto, conservando la restricción
para los demás ambientes. Un texto en un prompt no reemplaza esa política ni la
validación del destino. Este documento registra la autorización; no modifica ni
activa por sí solo el ejecutor actual.

Validar push confirmado, despliegue DEV correspondiente al commit, coherencia entre
servicios, recuperación de publicación incierta, fallos visibles en el cierre y
ausencia de disparadores de QA/producción. La prueba del piloto incluye abrir el
DEV y comprobar el avance, no sólo producir una propuesta o un commit local.

Estado: requisito incorporado al diseño de la operación nocturna. En este turno
no se ejecutaron pushes, publicaciones ni cambios de ambiente.

## Backlog único por proyecto y ejecución continua

Ampliación del 5 de noviembre de 2026: el backlog es una cola de encargos del
usuario, compartida entre WhatsApp/Info Codex, el chat/app de Bridge y Codex Bridge Feedback. Codex Folder no es un disparador. Opera durante todo el día y también alimenta la jornada nocturna.
Agregar una tarea no debe abrir otro chat ni lanzar una escritura paralela.

### Significado de cargar al backlog

Seleccionar «Backlog» o enviar explícitamente una tarea a la cola significa:
«ejecutar este encargo automáticamente cuando corresponda el turno del proyecto».
No convertir cada entrada en una propuesta que vuelva a exigir aprobación. El
usuario pide continuidad sin frenos de confirmación repetidos. Se conservan el
alcance original, autor, adjuntos, proyecto y evidencia de esa instrucción.

Una sugerencia generada por el propio supervisor no tiene automáticamente esa
misma autorización: se incorpora como ejecutable sólo si entra en una política
autónoma vigente o el usuario la elige. La coherencia y las validaciones pertenecen
al trabajo; no son una excusa para dejar todos los encargos esperando otro mensaje.

### Entradas sencillas al mismo backlog

- **WhatsApp / Info Codex:** recibir texto, audio y adjuntos agrupados; resolver
  proyecto con el selector actual y agregar «Backlog» al modo de atención. Separar
  el destino de respuesta (WhatsApp/Bridge) de la modalidad (Conversar/Ejecutar/Backlog).
  El voto Backlog guarda un encargo durable y devuelve un acuse breve con proyecto,
  título y posición. No abre chat ni llama al ejecutor durante la captura.
- **App Bridge:** sección «Backlog» por proyecto con «Agregar tarea», texto,
  audio/adjuntos disponibles, orden y estado. Permitir ver, editar o retirar tareas
  aún no iniciadas. Cargar varias tareas no abre varias conversaciones.
- **Codex Bridge Feedback:** conservar captura, anotaciones y agrupación actuales;
  ofrecer «Ejecutar» o «Añadir al backlog» al enviar el lote. Varias observaciones
  de una misma revisión pueden formar un encargo, sin ejecutar media captura ni
  crear un trabajo por cada toque. La cola de borradores de Feedback y el backlog
  de ejecución son entidades distintas; confirmar la recepción durable antes de
  dar un lote por transferido y conservar pendientes ante fallos.
Codex Folder se consulta solamente cuando un encargo lo solicita; no se observa para crear tareas.

Todas las fuentes conservan una clave estable de origen para recuperar un reintento
sin duplicarlo. Deduplicar por identidad comprobable; los parecidos semánticos se
relacionan o proponen combinar, sin descartar un pedido distinto silenciosamente.
Sólo fuentes/remitentes autorizados pueden agregar encargos ejecutables. Un adjunto
o mensaje de terceros no amplía permisos ni habilita otro ambiente.

### Dos elecciones con comportamiento claro

«Ejecutar ahora» pide atención prioritaria. Si el proyecto está libre, arranca;
si está ocupado, se coloca como próximo encargo prioritario, avisando que está
en cola. No cancela el trabajo actual ni abre otra escritura por inferencia.

«Backlog» agrega al orden normal del proyecto. Si ya hay trabajo activo, espera
su cierre completo. Si está libre, el coordinador puede tomarlo en su siguiente
pasada; no significa «guardado pero pendiente de otra aprobación». La recepción
del pedido y el inicio de ejecución son pasos separados. Ofrecer posponer/pausar
explícitamente para quien quiera conservar una idea sin ejecutarla todavía.

### Un encargado toma el siguiente, no un chat por cada captura

Un coordinador durable reclama una sola tarea ejecutable por proyecto mediante
una reserva persistente con vencimiento/recuperación y revisión de estado. Los
ingresos manuales, WhatsApp, Feedback, el backlog y el supervisor deben compartir
esta exclusión; no basta con comprobar si había un job activo antes de arrancar.

El orden normal es el de ingreso. Respetar dependencias y prioridades expresas del
usuario. Una investigación del supervisor no debe desplazar indefinidamente una
cola de pedidos concretos. Si una entrada se bloquea, avanzar con una independiente
cuando sea válido, conservando el motivo visible y sin ejecutar sus dependientes.

Al comenzar una tarea, recuperar el objetivo del proyecto, decisiones recientes,
resultado de la ejecución anterior, código vigente y alcance pedido. Si ya está
resuelta, comprobarlo y registrar el resultado sin volver a implementar. Si tiene
dependencias, incorporar lo necesario dentro del alcance; preguntar sólo cuando
una decisión material no pueda inferirse, dejando esa entrada identificada y
continuando lo independiente. Las contradicciones no se resuelven inventando
requisitos: reconocer correcciones posteriores explícitas y conservar trazabilidad.

Una tarea iniciada congela su versión y sus adjuntos. Nuevas entradas quedan
detrás; no cambian a escondidas el encargo que ya está ejecutándose. Las ediciones
de tareas pendientes llevan versión. La selección y el kickoff usan esa versión
para que un cambio simultáneo no ejecute un alcance obsoleto.

El trabajo se muestra en un hilo operativo del proyecto, con cada tarea y resultado
identificables. La captura no crea conversaciones y la ejecución no abre chats en
paralelo del mismo proyecto. El motor recibe contexto compacto por encargo, con
presupuesto propio autorizado, sin arrastrar un historial ilimitado ni ampliar los
turnos de un trabajo agotado mediante continuaciones encubiertas.

### Cuándo se puede pasar al siguiente

El cierre incluye el ciclo completo de agentes, correcciones, validaciones,
commit/push confirmado y publicación DEV comprobada de todos los servicios afectados.
Que termine un mensaje de Generator, un job individual o el envío HTTP no acredita
ese cierre. Un fallo o cancelación tampoco equivale a éxito.

Después del cierre, el coordinador toma automáticamente la siguiente tarea lista.
Si falla una validación, se corrige dentro del alcance y presupuesto. Si no puede
cerrar, registra el bloqueo, evita publicar una versión rota y elige una entrada
independiente si existe. Reintentos, reinicios o confirmaciones perdidas nunca
deben arrancar dos ejecuciones del mismo encargo.

La cola de encargos autorizados funciona también fuera del horario nocturno. La
franja nocturna regula las revisiones autónomas y la exploración según su política;
no deja los pedidos del usuario inmóviles durante el día. Los límites de recursos
y los proyectos pausados siguen vigentes y deben ser visibles. Si no hay trabajo
útil, el servicio espera sin invocar modelos hasta una entrada, evento o vencimiento.

### Presentación y relación con «Tu noche»

Cada proyecto muestra «En curso», «Siguiente» y «En espera», con origen de cada tarea.
El acuse puede ser: «Peluquería · agregado al backlog, posición 3. Se tomará al
completar los anteriores». Estados internos permiten distinguir recibido,
preparando contexto, ejecutando, validando, publicando DEV, terminado y bloqueado,
sin obligar al usuario a leer ese detalle en la primera vista.

«Tu noche» resume lo que salió del backlog, las oportunidades autónomas atendidas,
qué quedó publicado en DEV y lo que sigue. Las alternativas que el usuario elige
desde el resumen se convierten en encargos de esta misma cola, evitando crear otro
camino de ejecución paralelo.

### Base verificada y trabajo pendiente

El selector actual de WhatsApp ofrece «WhatsApp · Charlar» y «Bridge · Ejecutar»;
no tiene todavía la opción Backlog. El adaptador interactivo actual sigue el
estado de un job: hay que reemplazar esa condición de continuidad por el cierre
del encargo completo, incluidos agentes y DEV.

Feedback conserva lotes, adjuntos, sesión/job y destino de release, pero no existe
todavía el modo de transferencia al backlog común. Un booleano de publicar al
terminar no identifica por sí solo DEV: el adaptador debe utilizar la política
explícita de destinos DEV y conservar las colas pendientes existentes.

Agregar el registro central de tareas, contrato de recepción/versiones, selección
atómica, exclusión compartida, cierre verificable y adaptadores de entrada. Primero
reutilizar los selectores y lotes existentes para WhatsApp, app y Feedback; sumar
únicamente esas tres entradas, sin mantener estados de ejecución divergentes.

Probar cargas durante una ejecución, lote de Feedback incompleto, reenvío del mismo
pedido, edición simultánea, varios productores, dos workers, reinicio entre reserva
y envío, job terminado con Reviewer activo, publicación DEV pendiente, bloqueo de
dependencias y recuperación. El caso central de aceptación es completar dos tareas
consecutivas, ambas validadas/pusheadas/en DEV, sin una segunda orden del usuario
y sin escrituras paralelas sobre el proyecto.

Estado: lógica incorporada al diseño. Todavía no se implementaron el backlog común,
sus opciones de ingreso ni el encadenamiento automático de encargos.
