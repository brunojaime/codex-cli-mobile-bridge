# Resultado de colaboración: Gym a nienfos.app-spec/1.0.0

## Identidad

| Campo | Valor |
|---|---|
| Run | `20261116T195300Z-gym-contract-v1` |
| Estrategia | `consultation/v1` |
| Repositorio | `brunojaime/codex-cli-mobile-bridge` |
| Rama autorizada | `collaboration/20261116T195300Z-gym-contract-v1` |
| Input commit | `f39f9c590606ce9a2e3764e66d0be4844cc31e52` |
| Request digest | `8621ac1f0279e0d57755a827204c808665c18e1f36b07d9c1085ef13ad4e86cd` |
| Alcance | Preparación documental en DEV. Sin implementación, despliegue, reinicio ni producción. |

## Resultado

Se convirtió el relevamiento completo de Gym al contrato `nienfos.app-spec/1.0.0`. No se usó el ejemplo pequeño de dos historias como sustituto. El bundle queda en estado `draft` porque permanecen decisiones materiales abiertas, no porque falten historias o criterios.

## Entregables verificados en Google Drive

| Archivo | Enlace | Tamaño | SHA256 |
|---|---|---:|---|
| `GIM_APP_SPEC_1.0.0.bundle.json` | https://drive.google.com/file/d/1E6XDQO1BBNFn1mVKA-eVZKNbjBkyUTGI/view | 2.990.144 bytes | `51471d7efad5665dd11b10b6b1e772302c2158b76191783e8381272dc3332d0e` |
| `GIM_APP_SPEC_1.0.0.coverage.md` | https://drive.google.com/file/d/13Nu5lo07gd9J7DcfP_HyhIcfzEpH2VC0/view | 422.688 bytes | `0ebca181877871b1e357193d5701678d75b187523a2bf16fadac48a858177e47` |
| `GIM_APP_SPEC_1.0.0.md` | https://drive.google.com/file/d/10XowSykjV1STNJQgRLtTslmpbhIZYdSx/view | 12.632 bytes | `a7074e01fa6e11c6d6352847e6f4de3e49addfa7d375845880a4df730f3398f9` |

Carpeta verificada: https://drive.google.com/drive/folders/1mX3dNuNDnlDVk3tISFVd4FPOifc7E-Sf

La lectura posterior de la carpeta mostró los tres archivos nuevos y `relevamiento_app_gimnasio.docx`. El original no fue reemplazado.

## Fuentes efectivamente leídas

1. `docs/ai-collaboration/runs/20261116T195300Z-gym-contract-v1/request.json`, rama `collaboration/20261116T195300Z-gym-contract-v1`.
2. `TASK.md`, `SOURCE_INDEX.md` y `NIENFOS_APP_CONTRACT_1.0.0.md` del directorio de la ronda, leídos en el input commit `f39f9c590606ce9a2e3764e66d0be4844cc31e52`.
3. `codex-folder/NIENFOS_APP_CONTRACT_1.0.0.md`, Drive ID `1UQSbhuTmUFYdn7S-3ZwtN2TNvCrHEYtZ`, 3.255 líneas, SHA256 `4db911c655f6a102e456f35dbd9b65327f53097d37456fdd0f2ba970db843580`.
4. `codex-folder/gim_app/relevamiento_app_gimnasio.docx`, Drive ID `1Z4xhK9MdYlEaAhur3NTJ4KUdzuNtLmGc`, SHA256 `a608ac173109b3b6c59c81942aab0ef1aa0c7aa403461ce2a413f9941f9e749d`.
5. La carpeta `codex-folder/gim_app`. Al inicio contenía sólo el DOCX original.
6. Las referencias F01 a F13 se conservaron desde el DOCX. No se realizó investigación profunda ni revalidación web externa.

## Cobertura

| Elemento | Cantidad |
|---|---:|
| Módulos originales | 21 |
| Historias | 173 |
| Criterios de aceptación | 469 |
| P0 | 75 |
| P1 | 61 |
| P2 | 37 |
| Historias con condición de activación | 69 |
| Roles exactos del catálogo | 49 |
| Entidades tipadas | 172 |
| Máquinas de estado | 10 |
| Operaciones | 173 |
| Pantallas funcionales con ocho estados | 175 |
| Recorridos por rol | 15 |
| APIs cerradas con JSON Schema | 579 |
| Checks DEV | 469 |
| Unidades de trabajo | 52 |

Cada CA está presente en `acceptance`, en un check DEV y en una unidad de trabajo. `coverage.md` conserva el texto original, condición, dependencias, relaciones condicionales, criterio activo, pantalla, operación, API, check y unidad.

## IAM05 y decisión sin MFA

El DOCX original exigía segundo factor para cuentas privilegiadas. Esa procedencia se conserva en `coverage.md` y `extensions.x-nienfos.iam05-override`.

La regla activa aplica la decisión posterior de Bruno: no exigir segundo factor, MFA ni TOTP. Se conservan sesión vigente, CSRF, permisos y ámbito revalidados en servidor, confirmación explícita, recuperación de un solo uso, revocación de sesiones, auditoría y aprobación financiera independiente.

## Capacidades compartidas

El bundle distingue sin afirmar instalación:

- `available`: `identity.account`, `locale.fields`.
- `adapter_required`: `admin.reviewed-records`, `tenant.context`, `ui.shell`, `notifications.push`, `mail.transactional`, `payments.checkout`, `operations.release`.
- `proposed`: `files.private`, `jobs.general`, `offline.general`.

`payments.subscription` no se usa para cuotas del gimnasio. El checkout permanece condicional y TEST ONLY.

## Estado y decisiones abiertas

El contrato funcional permanece `draft`. Las decisiones materiales abiertas incluyen modelo de oferta, stack, catálogo de servicios, políticas de membresía y reservas, país y fiscalidad, proveedores, hardware de acceso, offline, datos sensibles, plataformas, escala, migración, retención, derechos de contenido y objetivos de recuperación.

La evidencia visual V5.1 posterior no fue adjuntada. Se preservó la dirección visual y el requisito de observar dos propuestas y una familia piloto, pero no se certifica estética ni se acreditan imágenes no vistas.

## Validaciones locales realizadas

1. JSON Schema exacto del contrato: 0 errores.
2. Consistencia cruzada: 0 incidencias en IDs, referencias, ciclos, permisos, entidades, estados, reciprocidad historia/CA/pantalla, navegación, fases API, esquemas cerrados, cobertura de checks y unidades, límites de unidad, DEV-only e IAM05.
3. Cada request y response fue comprobado como JSON Schema Draft 2020-12.

Estas comprobaciones no sustituyen el validador oficial de la fábrica Python. No se declara un PASS oficial.

## Límite del canal GitHub

El conector GitHub disponible permite crear archivos desde contenido UTF-8 inline, pero no acepta una referencia de archivo local para `create_blob`, `create_file` o `create_tree`. El bundle completo tiene 2.990.144 bytes y el registro de cobertura 422.688 bytes. No se publicó una versión truncada, un puntero disfrazado de JSON ni un hash sin verificar.

Por esta limitación:

- Este `result.md` sí se persiste y se verifica en la rama autorizada.
- `bundle.json`, `coverage.md` y `result.json` no se declaran entregados en GitHub.
- No se publica `result.json` con `status: completed` y `producer: chatgpt`, porque afirmaría artefactos inexistentes en esa rama.
- Codex debe exportar desde los archivos completos de Drive o las copias descargables, verificar sus SHA256 y publicar `bundle.json`, `coverage.md` y, al final, `result.json` con `producer: codex-export`.

La interfaz de esta consulta tampoco expone una URL canónica por chat. El destino suministrado fue `https://chatgpt.com/g/g-p-6aea4404bac4819180e6443dc3f2a5d4/project`; no se presenta como una URL de conversación descubierta.

## Acciones verificables para Codex

1. Descargar los tres archivos de Drive y comprobar los SHA256 de la tabla.
2. Copiar sin transformar `GIM_APP_SPEC_1.0.0.bundle.json` a `docs/ai-collaboration/runs/20261116T195300Z-gym-contract-v1/bundle.json`.
3. Copiar sin transformar `GIM_APP_SPEC_1.0.0.coverage.md` a `docs/ai-collaboration/runs/20261116T195300Z-gym-contract-v1/coverage.md`.
4. Ejecutar el validador oficial y devolver errores concretos por ruta JSON. No asumir PASS a partir de esta consulta.
5. Publicar `result.json` al final con `producer: codex-export`, hashes reales de los archivos GitHub y el estado que corresponda tras verificar el validador.
6. Mantener todo en `collaboration/20261116T195300Z-gym-contract-v1`. No tocar otras ramas ni el producto.
