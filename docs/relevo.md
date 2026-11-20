# Relevo entre equipos (Lenovo → Batata → Lenovo)

Pasa el trabajo en curso a otro equipo cuando Bruno avisa que se va a quedar
sin internet. No detecta conectividad: se dispara a mano.

## Cómo se usa

- Desde cualquier chat en Lenovo: **"pasate a batata"**. El agente ejecuta `relevo ir batata`.
- Para volver: **"volvemos a lenovo"** → `relevo volver batata`.
- Terminal: `relevo ir batata [--proyecto RUTA] [--simular]`, `relevo volver batata`,
  `relevo traer batata`, `relevo estado`.

## Qué hace `relevo ir batata` (unos 40 s por proyecto, más el cierre de chats activos: hasta 3 min)

1. Elige los proyectos con chats de las últimas 12 h en los Bridges locales (8000 y 8001),
   o los que se pasen con `--proyecto`.
2. Omite los repos que no son privados en GitHub (el WIP nunca va a un repo público).
3. Después del cierre del paso 4, captura TODO el WIP (commits, cambios sin commit y archivos nuevos no ignorados) con un
   índice temporal. No cambia rama, índice ni archivos locales. Excluye secretos
   (`.env*`, `.dev.vars`, claves, `.private/`), archivos de más de 50 MB y repos anidados.
4. **Cierre ordenado** de los agentes activos de esos proyectos (nunca del chat que disparó), todos en paralelo:
   - por **steering real** (`/jobs/{id}/steer`) si el proveedor lo admite (hoy Codex app-server; Claude cuando
     se publique el steering del otro chat);
   - si no, el mismo mensaje de cierre queda **encolado como siguiente turno** de ese chat, sin cortar el turno actual.
   El agente termina su paso, no empieza nada nuevo, no ejecuta `relevo` y deja un bloque `RELEVO_CIERRE`
   (objetivo, hecho, pendiente, próximo paso), que viaja al chat de Batata. Sólo si pasan 180 s (`--esperar`)
   se cancela. El informe dice por chat el camino seguido. El WIP se captura **después** del cierre.
5. Sube primero todas las ramas `relevo/lenovo-AAAAMMDD-HHMMSS` a GitHub y verifica
   el hash con `ls-remote`. Desde ese momento la Lenovo puede quedarse sin internet.
6. En el Bridge de Batata (PROD, puerto 8000), un chat de **preparación** con acceso completo
   clona el repo (o crea un worktree `<repo>-relevo` si Batata ya lo tenía, sin tocar su
   checkout) y confirma el hash con `RELEVO_LISTO`.
7. Abre un **chat de continuación** con la carpeta real como workspace. Le pasa un resumen
   determinista de los chats (sin llamar a un modelo), los servicios que corrían, y los
   nombres (sin valores) de secretos y variables. El agente responde qué secretos faltan.

La repetición sin cambios no hace nada: responde "ya está en batata".

## Vuelta

`relevo volver batata` le pide al chat de continuación que suba su WIP a
`relevo/batata-*`. Espera que aparezca en GitHub y lo trae a la Lenovo como rama aparte,
con hash verificado y resumen de cambios. Nunca hace merge ni toca el árbol local.

## Equipos

Se configuran en `config/relevo-hosts.json`: bridges, `projects_root`, proxy SOCKS de
Tailscale y `landing_workspace`. La Mac ya tiene su entrada (`enabled: false`): sólo falta
completar su URL de Bridge y la carpeta de proyectos.

## Límites

- Requiere internet en la Lenovo en el momento del disparo, al menos para el paso 5.
- Los secretos no viajan. Batata informa los faltantes por nombre y se cargan desde el panel
  Secrets. En un worktree de un repo que Batata ya tenía, se copian localmente desde su checkout.
- Los servicios no se levantan solos: se listan y el agente de Batata los levanta si Bruno lo pide.
- Proyectos sin remoto GitHub o con remoto público se omiten y se informan.
- La preparación usa `sandbox_mode=danger-full-access` sólo en ese mensaje acotado y en el
  pedido de vuelta. Los chats normales de Batata conservan su sandbox.
- Estado local: `~/.local/state/relevo/relevos.json`.
