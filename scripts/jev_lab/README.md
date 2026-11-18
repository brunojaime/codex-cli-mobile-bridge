# Laboratorio Jev para Nienfos

Cliente de evaluación aislado del backend. Permite comparar exactamente el mismo corpus por OpenRouter, Cloudflare, TypeSafe, Laya local y una referencia sin modelo. No cambia estados de Gestión, no publica versiones y no envía información real de clientes.

## Estado de preparación

- SDK oficial `typesafe-sdk==0.7.2` instalado en un entorno separado. Inventario: [sdk-lock.txt](../../reports/jev-lab-20260927/sdk-lock.txt).
- Importación y ruta del SDK a OpenRouter verificadas con transporte simulado; eso **no es una inferencia real**.
- El runner `lab.py` usa Python 3.10+ y biblioteca estándar: no necesita instalar SDK, PyTorch ni GPU para llamar a Jev.
- 73 casos originales congelados en [cases.json](cases.json). Sus etiquetas fueron escritas por el asistente, sin revisión independiente.
- OpenRouter ya funciona con la clave del panel Secrets `OPEN_ROUTER_API_KEY`. El intento inicial a Cloudflare quedó como antecedente HTTP 401. Ver [evaluación real de Jev](../../reports/jev-lab-20260927/conclusiones-jev.md).

Jev se consume como servicio alojado. Instalar el SDK instala el cliente, no los pesos del modelo. [Acceso y endpoints oficiales de OpenRouter](https://openrouter.ai/docs/guides/community/jev).

## Camino recomendado: OpenRouter

1. Ingresar a [OpenRouter](https://openrouter.ai/), crear la cuenta si hace falta y cargar créditos desde su panel. El mínimo de compra y los cargos de recarga son los que muestre el proveedor.
2. Crear una clave en [API Keys](https://openrouter.ai/settings/keys), con nombre `nienfos-jev-lab`. Usar un límite de gasto pequeño, por ejemplo USD 1, si el panel lo permite.
3. Agregar o rotar la clave desde el panel **Secrets** del chat, con nombre `OPEN_ROUTER_API_KEY`. El panel la guarda en el `.env` del workspace. No pegar claves en la conversación.
4. Ejecutar `doctor`, una prueba de conexión y después el corpus completo.

Desde la raíz del workspace:

```bash
.venv/bin/python scripts/jev_lab/project.py doctor
.venv/bin/python scripts/jev_lab/project.py run --provider openrouter --family noul --variants original --max-requests 1 --out reports/jev-smoke-openrouter-02
.venv/bin/python scripts/jev_lab/project.py run --provider openrouter --repeats 2 --max-requests 500 --budget-usd 0.25 --out reports/jev-openrouter-02
```

`project.py` lee los secretos del workspace, adapta el nombre de la variable únicamente en memoria y no reescribe `.env`. Usa la versión actual del panel aunque el proceso conserve una variable anterior. Los comandos usan carpetas nuevas para no sobrescribir corridas.

Modelo fijado: `typesafe/jev-1.13`. Endpoint: `https://openrouter.ai/api/v1/systemone`. No utilizar `typesafe/jev-router`: ese producto selecciona otros modelos y no es el evaluador que estamos midiendo. El cliente registra la versión resuelta cuando el proveedor la devuelve. [Contrato System One](https://openrouter.ai/docs/guides/community/typesafe-sdk).

## Alternativa: Cloudflare

1. En [Cloudflare Dashboard](https://dash.cloudflare.com/), elegir la cuenta y obtener su **Account ID**.
2. Crear un token dedicado con permiso **Account → Workers AI → Read**, limitado a esa cuenta. El permiso de AI Gateway por sí solo no habilita `/ai/run`.
3. Habilitar AI Gateway y disponer de créditos de **Unified Billing** para modelos externos. Un plan de Workers o un token para desplegar páginas no demuestran acceso a Jev.
4. Guardar `CLOUDFLARE_API_TOKEN` y `CLOUDFLARE_ACCOUNT_ID` mediante el panel Secrets. Opcionalmente definir `CLOUDFLARE_AI_GATEWAY_ID` para un gateway específico; de lo contrario el proveedor usa el predeterminado.
5. Ejecutar la misma prueba y corpus con `--provider cloudflare`.

```bash
.venv/bin/python scripts/jev_lab/project.py run --provider cloudflare --family noul --variants original --max-requests 1 --out reports/jev-smoke-cloudflare-01
.venv/bin/python scripts/jev_lab/project.py run --provider cloudflare --repeats 2 --max-requests 500 --budget-usd 0.25 --out reports/jev-cloudflare-01
```

El cliente usa el modelo `typesafe/jev`, en `/client/v4/accounts/{account_id}/ai/run`, con envelope `{model, input}`. Solicita omitir caché y no recopilar logs de cuerpos en Gateway. No hace falta desplegar un Worker para ejecutar estas pruebas. [REST, permisos y encabezados](https://developers.cloudflare.com/ai-gateway/usage/rest-api/), [modelo y precio](https://developers.cloudflare.com/ai/models/typesafe/jev/).

Para una integración posterior dentro de Gestión se puede agregar el binding `AI` y llamar a `env.AI.run('typesafe/jev', {state, questions}, {gateway: {id: '...', skipCache: true, collectLog: false}})`. Esa integración es trabajo posterior: el laboratorio ejecuta HTTP desde el host. [Binding oficial](https://developers.cloudflare.com/ai-gateway/usage/worker-binding-methods/).

## Qué probamos

| Familia | Casos | Pregunta de trabajo |
|---|---:|---|
| Cobertura de requisitos | 16 | ¿La evidencia respalda, contradice o deja pendiente el requisito? |
| Selección de contexto | 10 | ¿Qué documento conviene recuperar para atender el pedido? |
| Alcance | 12 | ¿El pedido entra en lo aprobado, agrega alcance o es ambiguo? |
| Coherencia | 12 | ¿Hay contradicción real o estados de ámbitos/versiones diferentes? |
| Relación de feedback | 8 | ¿Dos reportes merecen revisión conjunta? |
| Selección de regresión | 8 | ¿Qué recorrido conviene probar primero? |
| Noul | 4 | Control del contrato booleano, con negación y español/inglés |
| Score | 3 | Control de escala ordenada de bloqueo |

Se incluyen casos positivos, negativos, ambiguos, evidencia vieja, resultados parciales, instrucciones adversariales en los datos, errores de tipeo y algunos controles en inglés. No es una evaluación lingüística balanceada.

Cada caso se ejecuta en forma original y con contexto irrelevante agregado. Los 66 casos Choice se ejecutan también con el orden de opciones invertido; las escalas Score conservan su orden semántico. Una vuelta son **212 peticiones**; dos vueltas son **424**. Esas variantes siguen representando 73 casos, no 424 ejemplos independientes.

```bash
python3 scripts/jev_lab/lab.py plan --repeats 2 --max-requests 500
.venv/bin/python -m unittest discover -s scripts/jev_lab -p 'test_*.py' -v
```

La primera ejecución de Laya reutiliza pesos ya disponibles y fijados por revisión. La ruta temporal utilizada consta en las instrucciones de la sesión; para repetir después hay que disponer del mismo snapshot y de Laya 0.3.20. `--laya-site` permite cargar una instalación aislada y `--laya-snapshot` señala su snapshot local. El cliente trabaja offline para Laya y no descarga pesos implícitamente.

## Métricas y límites

Cada corrida produce:

- `run.json`: proveedor, versión, hashes de corpus/runner, número de peticiones y estado de ejecución.
- `predictions.jsonl`: decisión, respuesta esperada, probabilidades, errores, tiempo y uso reportado.
- `metrics.json`: acierto por familia, intervalo de Wilson, matriz de confusión, falsos aceptados, Brier, cobertura/errores por umbral y sensibilidad a variantes/repetición.

Sólo se cuentan como casos independientes los originales de la primera vuelta. Los intervalos reflejan el pequeño tamaño del corpus y no corrigen su sesgo de autoría. Score usa error absoluto y una tolerancia exploratoria de 0,5. La métrica de precisión de una familia no mide por sí sola calidad de una entrega.

La referencia `baseline` es deliberadamente sencilla: búsqueda por palabras en recuperación; `missing`, `unknown` o `unclear` fijos en las otras familias; probabilidad 0,5 en Noul y nivel medio en Score. **Superar esa referencia no prueba ventaja sobre el proceso actual ni sobre reglas bien diseñadas.** La auditoría determinista anterior sigue siendo la referencia adecuada para hashes, tareas, versiones y contadores.

Los casos de cobertura y recuperación se reutilizan de la exploración previa de Laya. El resto se redactó antes de esta ejecución, pero no tiene etiquetas revisadas por una segunda persona. Antes de adoptar un uso hay que incorporar ejemplos reales sanitizados y separar calibración y evaluación final.

## Costo y manejo de errores

La tarifa publicada al preparar el laboratorio es **USD 0,042 por millón de tokens de entrada**, sin cargo por salida. [Modelo en Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/), [TypeSafe](https://docs.typesafe.ai/models).

Para 424 peticiones, la reserva de planificación del corpus es aproximadamente **USD 0,05**, usando bytes del JSON más un margen por petición. Es una estimación, no consumo medido ni límite garantizado. La factura real se registra desde `usage.cost` cuando existe; si sólo hay tokens, se informa estimación separada. Comisiones de recarga, cómputo local y trabajo humano no están incluidos.

`--budget-usd 0.25` detiene nuevas peticiones según esa reserva/consumo conocido. Para un límite de facturación firme se necesita además el límite de la cuenta o clave del proveedor. El runner no reintenta automáticamente, se detiene al primer error y no sigue redirecciones con credenciales. HTTP 401/403 requiere resolver autenticación/permisos; 402 suele requerir revisar saldo; 429 exige respetar límites antes de otra corrida. Un error no cuenta como resultado correcto ni como inferencia gratuita confirmada.

Cada salida usa una carpeta nueva: nunca se sobrescribe una evaluación anterior.

## Medir beneficio en el trabajo

Después de medir precisión, seleccionar uno o dos usos con resultados prometedores, por ejemplo alcance y recuperación. Ejecutarlos como sugerencias mientras el flujo actual continúa. Con casos comparables y revisados, medir:

1. Tiempo humano para decidir sin ayuda frente a tiempo con sugerencia y revisión.
2. Tiempo de corregir sugerencias equivocadas.
3. Pendientes relevantes detectados y falsos “cumple”.
4. Costo total de inferencia y revisión por decisión útil.

Usar [revision-humana.csv](../../reports/jev-lab-20260927/revision-humana.csv) para registrar mediciones. Está vacío intencionalmente: no inventa ahorro. Alternar grupos comparables y controlar el efecto de recordar un caso ya visto; idealmente revisores distintos y orden aleatorio.

**Tiempo neto ahorrado = tiempo sin asistencia − tiempo con asistencia − correcciones.** El despliegue se justifica por una reducción medible de seguimiento o por detecciones relevantes adicionales, manteniendo la calidad requerida. No se fijan umbrales de aprobación automática con este corpus pequeño.
