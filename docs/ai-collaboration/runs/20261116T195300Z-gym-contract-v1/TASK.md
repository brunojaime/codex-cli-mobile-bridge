# Convertir el relevamiento de Gym al contrato compartido Nienfos 1.0.0

Origen: Bruno lo solicita desde Codex Bridge DEV en Lenovo. Usar ChatGPT Pro, sin investigación profunda. Esta tarea es preparación de contratos, no desarrollar ni reiniciar la app.

## Fuentes y destino exactos en Google Drive

- Carpeta raíz **codex-folder**: https://drive.google.com/drive/folders/11wixeZFVL4X-l71TYInIYl-lYanjek7a
- Contrato autocontenido nuevo en esa raíz, **NIENFOS_APP_CONTRACT_1.0.0.md**: https://drive.google.com/file/d/1UQSbhuTmUFYdn7S-3ZwtN2TNvCrHEYtZ/view
- Dominio del gimnasio en **codex-folder/gim_app**: https://drive.google.com/drive/folders/1mX3dNuNDnlDVk3tISFVd4FPOifc7E-Sf
- Documento original **relevamiento_app_gimnasio.docx**: https://docs.google.com/document/d/1Z4xhK9MdYlEaAhur3NTJ4KUdzuNtLmGc/edit

Leer íntegros el contrato nuevo y el relevamiento, y comprobar si existen otros documentos pertinentes en la subcarpeta gim_app. No explorar datos personales ni proyectos ajenos de la raíz. En la lectura verificada de Codex hay un relevamiento de 21 módulos, 173 historias y 469 CA; cotejar esos conteos con el original, no inventarlos para hacerlos coincidir. El SHA256 observado del .docx es a608ac173109b3b6c59c81942aab0ef1aa0c7aa403461ce2a413f9941f9e749d. El SHA256 del contrato .md es 4db911c655f6a102e456f35dbd9b65327f53097d37456fdd0f2ba970db843580.

## Objetivo

Convertir el dominio completo al formato nienfos.app-spec/1.0.0 usando exactamente los esquemas y catálogo incluidos en el .md. Ambos lados —ChatGPT y la fábrica Python— consumen el mismo contrato, sin otra redacción de requisitos. El ejemplo pequeño de gimnasio incrustado en el contrato NO es el alcance real; no copiarlo en lugar de las 173 historias.

Preservar IDs, criterios, prioridades, reglas y dependencias del original. Explicitar fuentes, decisiones, roles/permisos, entidades/invariantes/estados, operaciones, APIs con JSON Schema exacto de request y response, pantallas con ocho estados y navegación, recorridos por rol, integraciones, primer resultado útil, pruebas y unidades de trabajo. Las referencias cruzadas deben coincidir y cubrir todos los CA. No rellenar con frases genéricas, descartar módulos ni rebajar requisitos para validar.

Distinguir capacidades shared available/adapter_required/proposed del catálogo. No declarar que ya están instaladas/configuradas/publicadas/verificadas. Las reglas de negocio, por ejemplo cuotas de socios, no son la suscripción a Nienfos. Sin precios, proveedores, credenciales, derechos sobre ejercicios o evidencia inventados.

Aplicar la decisión vigente explícita de Bruno: no exigir segundo factor/MFA/TOTP. Conservar sesión, CSRF, permisos, aislamiento, confirmación, auditoría y aprobación financiera independiente. Si el original exigía MFA, conservar la procedencia de la regla original y registrar la decisión posterior, sin borrar silenciosamente la discrepancia.

Definir contratos funcionales de pantallas completos; no diseñar ni implementar todas las pantallas ahora. La dirección visual sigue V5.1 revisada: propuestas y familia piloto observadas en la ejecución UX posterior. Una especificación lista no certifica estética.

Si faltan decisiones materiales, devolver draft con preguntas y alternativas concretas. No inventar confirmaciones. Extensiones x-* sólo metadatos optativos: no esconder en ellas el dominio para eludir los contratos tipados. Si el protocolo no expresa un requisito, documentar la brecha y proponer evolución explícita, sin cambiar silenciosamente la versión.

## Entregables

1. GIM_APP_SPEC_1.0.0.bundle.json completo, sin truncamiento, conforme al esquema exacto.
2. GIM_APP_SPEC_1.0.0.md: resumen humano, mapa de fuentes, trazabilidad de originales, decisiones pendientes y cualquier brecha del protocolo.
3. Registro de cobertura con IDs originales de historias/CA, incluidos opcionales y sus condiciones, que permita contrastar 173 historias/469 CA. No sustituir CA por un resumen que pierda su significado.
4. Guardar esos resultados como archivos nuevos en codex-folder/gim_app, preservando el .docx y el contrato. Devolver sus enlaces y declarar qué escrituras se verificaron.
5. Si el conector no permite escribir Drive, entregar archivos descargables completos y explicitarlo; Codex hará la carga y verificación. No afirmar que un archivo quedó en Drive sin evidencia.

No desplegar, crear infraestructura, cobrar, enviar mensajes a terceros ni tocar la ejecución actual de Gym. Una vez recibido, Codex ejecutará el validador real y devolverá errores concretos si los hubiera; no simular un PASS.
