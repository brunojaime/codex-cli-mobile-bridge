# Bridge: errores y publicación automática DEV

El usuario eligió el 07/11/2026 corregir errores, probar y publicar en DEV. No autoriza funciones nuevas ni promoción a producción. La ejecución pertenece al coordinador DEV, con rama y checkout separados. La búsqueda nocturna entrega allí los hallazgos de este proyecto.

La publicación verifica Git remoto, pruebas dirigidas y un plan con hashes previos/posteriores por archivo. Se preservan cambios no relacionados del runtime. No sobrescribir un runtime que cambió después de validar. La versión servida se captura al arrancar el proceso; no se acredita una publicación sólo escribiendo un manifiesto.

Esperar a que terminen TODOS los trabajos, sesiones y mensajes aceptados antes de reiniciar DEV. Usar el drain existente y soltarlo tras activar. No reiniciar producción ni cambiar URLs, datos o credenciales. La activación corre fuera del cgroup del backend para no morir con él y verifica salud, revisión y comportamiento HTTP real después.

El primer defecto: una autoridad file:// malformada debe devolver 422 desde ambos endpoints del visor, incluyendo relative_to. Las referencias válidas, formatos soportados y límites de acceso conservan sus pruebas. Los cambios móviles/Android requieren el procedimiento de release propio; este adaptador publica backend DEV y debe dejar explícita cualquier entrega móvil pendiente.

Para futuros errores agregar la prueba de regresión correspondiente; el operador repite la suite del visor y de revisión publicada. Registrar el resultado en un commit y dejar limpio el checkout. La publicación la ejecuta el coordinador, no el agente.
