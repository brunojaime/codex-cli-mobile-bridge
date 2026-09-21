---
name: nic-ar-domain-registration
description: Verifica disponibilidad y aranceles de dominios .ar y prepara el enlace oficial de NIC Argentina/TAD para que la persona complete el acceso con Clave Fiscal, confirme y pague. Usar cuando pidan buscar, registrar, comprar o verificar un dominio .ar; no usar para comprar dominios de otros TLD ni para automatizar credenciales o pagos.
---

# Registro de dominios NIC Argentina

Usá el servidor MCP `nic-ar-domains` para evitar búsquedas web y razonamiento repetitivo sobre datos estructurados que pueden cambiar.

## Flujo principal

Cuando la persona quiera registrar o comprar un dominio, llamá una sola vez a `prepare_ar_registration`. Esta tool normaliza el nombre, consulta WHOIS oficial, obtiene el arancel vigente y descubre el enlace actual del trámite en TAD/ARCA.

- Si la respuesta indica `ready_for_human_handoff: true`, informá el dominio normalizado, disponibilidad observada, precio y URL oficial devuelta. Aclarale que todavía debe iniciar sesión, confirmar y pagar.
- Si el dominio figura registrado, no presentes la URL como una compra posible. Resumí el estado y pedí otro nombre solamente si hace falta continuar.
- Si alguna verificación queda en estado `unknown` o falla el parseo del arancel, no inventes el resultado ni uses valores recordados. Explicá qué fuente falló y reintentá solamente si la persona lo pide o si fue un error transitorio claro.
- Usá `check_ar_domain` o `get_nic_ar_prices` por separado para comparaciones, diagnósticos o consultas que no sean una intención de compra.

## Límites de seguridad

Nunca solicites, copies, guardes ni pases la Clave Fiscal, CUIT/CUIL, cookies de sesión o datos de tarjeta a una tool. No automatices el inicio de sesión, la declaración jurada, el clic de confirmación ni el pago. No afirmes que el dominio quedó reservado o comprado hasta comprobar posteriormente su registro.

La disponibilidad es una observación puntual y puede cambiar antes de terminar el pago. Las zonas especiales pueden requerir habilitación previa aunque WHOIS muestre el nombre libre.

Para entender el contrato de cada tool, las fuentes oficiales y la división entre tareas determinísticas y decisiones del modelo, leé [references/workflow.md](references/workflow.md).
