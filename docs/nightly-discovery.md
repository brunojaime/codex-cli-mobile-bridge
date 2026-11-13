# Búsqueda autónoma nocturna

El servicio de usuario `codex-nightly-discovery.service` investiga los proyectos
seleccionados entre 22:30 y 08:00 de Argentina. Se configura en
`.data/nightly-discovery/config.json` y conserva su registro idempotente en
`.data/nightly-discovery/state.sqlite3`. El archivo contiene `enabled`,
`bridge_url` y `projects` (nombre y `workspace_path` de cada proyecto).

La búsqueda usa las rutas existentes del Bridge para crear un chat con un solo
Generator y un turno, sandbox de lectura y las mismas restricciones de herramientas
que los relevamientos. No requiere reiniciar el backend ni tener un despliegue DEV
configurado. Hace una revisión por proyecto y noche, con un solo análisis propio
en curso y un límite de 30 minutos por análisis. Los modelos se heredan del Bridge.
Si no hay una mejora útil, registra ese resultado; no inventa tareas.

Las oportunidades con evidencia van al backlog del coordinador principal con una
identidad estable. La publicación se rige por la política existente de cada
proyecto. Sin procedimiento DEV, el encargo queda guardado y explicado como
pendiente de preparación. No se configura un despliegue ficticio para habilitar
la búsqueda. El resultado completo del análisis permanece en su chat.

El supervisor consulta `automatic_execution` antes de admitir una nueva revisión.
También evita duplicar proyectos cuyo supervisor nativo ya tiene `autonomous=true`.
Una respuesta de envío perdida no se reintenta a ciegas; se consulta el chat y, si
no puede acreditarse el arranque, se marca `uncertain`. La entrega al backlog sí
es reintentable porque su clave y contenido se conservan antes de enviarlos.

Estado visible y sin secretos:
`reports/nightly-discovery-20261107/estado.json`. Los estados `running` y
`completed` corresponden a análisis, no a mejoras implementadas o publicadas.

Operación:

```sh
systemctl --user status codex-nightly-discovery.service
systemctl --user stop codex-nightly-discovery.service
systemctl --user start codex-nightly-discovery.service
```

Para desactivar permanentemente, cambiar `enabled` a `false` o ejecutar
`systemctl --user disable --now codex-nightly-discovery.service`.
No se debe arrancar otra instancia con otro archivo de estado para los mismos
proyectos. El bloqueo del estado impide instancias simultáneas sobre ese registro.
