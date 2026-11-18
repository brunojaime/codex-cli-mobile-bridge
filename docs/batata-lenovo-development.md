# Desarrollo local entre Batata, Lenovo y celular

## Resultado de esta primera etapa

Preparada una herramienta portable, sin dependencias Python externas, para pasar
commits entre computadoras. No está instalada en Lenovo ni se levantó una web:
falta elegir el primer proyecto y confirmar el acceso a Lenovo.

Tailscale reportó una Lenovo Linux conectada durante la inspección. Esto no prueba
acceso SSH, que tenga el repositorio actualizado ni que el navegador del celular
pueda abrir una web. El Bridge tiene cambios pendientes ajenos a esta tarea;
no se hicieron commits ni pushes del repositorio real.

## Funcionamiento previsto

Cada computadora tiene su copia Git y ejecuta localmente el proyecto que se está
editando. Las dos copias usan el mismo remoto y la misma rama de trabajo. El
celular abre la vista privada del equipo activo mediante Tailscale Serve.
Cloudflare conserva la publicación, independiente de estas vistas de desarrollo.

Git sincroniza archivos versionados y commits. No sincroniza archivos sin commit,
secretos, procesos, bases de datos, dependencias instaladas ni conversaciones o
sesiones de agentes. Los trabajos del Bridge que siguen ejecutándose en Batata
seguirán consumiendo recursos allí; abrir la web en Lenovo no los traslada.

## Herramienta disponible

[Código de handoff](../tools/machine_handoff/handoff.py) ·
[Pruebas de integración](../tools/machine_handoff/test_handoff.py)

Requiere Git, Python 3 y autenticación Git ya configurada en cada equipo. Usar la
misma versión de Python, Node y gestor de paquetes que requiera cada aplicación,
y sus archivos de versiones y lockfiles. No elegir versiones genéricas para
todos los proyectos sin revisar sus requisitos.

Desde este repositorio, comprobar una copia:

```bash
python3 tools/machine_handoff/handoff.py status --repo /ruta/al/proyecto
```

Al comenzar en el equipo destino, con el servidor apagado y sin otros agentes
modificando esa copia:

```bash
python3 tools/machine_handoff/handoff.py start --repo /ruta/al/proyecto
```

Este comando descarga el remoto y sólo permite un avance lineal de la rama.
Antes de levantar la app, instalar dependencias con el comando reproducible del
proyecto si cambió el lockfile. Para un proyecto que tenga un script npm `dev`,
se puede iniciar el servidor en primer plano después de actualizar:

```bash
python3 tools/machine_handoff/handoff.py start --repo /ruta/al/proyecto --run npm run dev
```

`--run` no instala dependencias ni convierte el proceso en servicio persistente.
La herramienta no configura Tailscale, puertos, HMR, login ni bases de datos.

Al terminar, detener el servidor y esperar que terminen los trabajos del proyecto.
Revisar los cambios y crear un commit sólo con los archivos elegidos. No usar un
guardado masivo automático; verificar que `.env`, credenciales y bases locales
estén fuera del seguimiento Git. Revisar también los commits pendientes, porque
`finish` sube todos los commits que todavía no estén en el upstream.

```bash
git status --short
git diff
# Agregar explícitamente los archivos elegidos y crear el commit.
python3 tools/machine_handoff/handoff.py finish --repo /ruta/al/proyecto
```

`finish` exige una copia limpia, comprueba el remoto y sube los commits a la rama
upstream configurada, sin forzar. Después verifica la coincidencia de revisión.
No crea commits, no usa stash, no descarta archivos y no resuelve conflictos.
Si falla el envío, los commits permanecen locales: no dar por completado el
traspaso. Si hay cambios en ambas máquinas, resolverlos antes de continuar.

La herramienta no es un bloqueo distribuido. No ejecutar Git ni agentes que
editen en paralelo sobre esa copia durante el traspaso. En desconexión se puede
trabajar localmente, pero start/finish necesitan acceso al remoto; nunca asumir
que el otro equipo recibió cambios pendientes.

## Activación de la primera web

1. Elegir proyecto y rama. Verificar sus cambios locales en las dos máquinas.
2. Confirmar acceso a Lenovo e instalar allí sólo la herramienta y el entorno
   necesario. Crear o actualizar la copia sin reemplazar trabajo pendiente.
3. Preparar configuración local y datos de desarrollo reales según la aplicación.
   Cargar credenciales mediante el panel Secrets; no incluirlas en este informe
   ni transferir indiscriminadamente `.env` entre máquinas.
4. Levantar el servidor en un puerto local libre y reservar otro puerto HTTPS de
   Tailscale por proyecto. Inspeccionar antes `tailscale serve status` usando el
   socket que corresponda a ese equipo. Batata usa Tailscale en modo userspace;
   su Bridge ya tiene rutas y puertos reservados. No ejecutar `serve reset`,
   reemplazar la raíz del Bridge ni habilitar Funnel para esta vista privada.
5. Configurar Serve para el puerto seleccionado. Probar desde el celular carga,
   navegación, recarga automática por WebSocket, login, API y datos. Ajustar los
   hosts permitidos y callbacks del proyecto si lo requieren. No alcanza con
   comprobar que responde el HTML.
6. Hacer un cambio visible en Lenovo, comprobarlo en el celular, guardar y pasar
   el commit a Batata. Repetir en dirección contraria. Entregar entonces los dos
   enlaces privados verificados.

En esta primera versión cada computadora tendrá su enlace privado. Un enlace que
cambie automáticamente al equipo activo es una etapa posterior: requiere un
registro del equipo activo y enrutamiento, no viene incluido en Git o Tailscale.

## Validación realizada

Cinco pruebas con dos clones temporales y un remoto bare local: ida y vuelta;
archivos pendientes conservados; ramas divergentes bloqueadas; start bloqueado
con commits locales sin subir; finish bloqueado con cambios nuevos en el remoto.
Todas pasaron. No hubo tráfico a GitHub en esas pruebas. La comprobación sobre el
Bridge real rechazó la copia con cambios pendientes antes de consultar el remoto.

```bash
python3 -m unittest discover -s tools/machine_handoff -p 'test_*.py' -v
```

Referencias: [Git pull y avance lineal](https://git-scm.com/docs/git-pull),
[vistas privadas de desarrollo con Tailscale](https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team).
