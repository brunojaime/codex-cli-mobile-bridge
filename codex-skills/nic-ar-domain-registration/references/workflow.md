# Contrato operativo

## Reparto de responsabilidades

Las tools resuelven tareas repetibles y verificables:

- normalización del nombre y la zona;
- consulta de disponibilidad por `whois.nic.ar`;
- lectura y parseo de la tabla oficial de aranceles;
- descubrimiento del identificador vigente del trámite y de los proveedores de autenticación de TAD;
- construcción del enlace oficial para iniciar el trámite con ARCA;
- generación de los pasos humanos restantes.

El modelo interpreta el pedido, elige la tool, explica resultados, detecta excepciones y ayuda a decidir entre nombres o zonas. No debe reemplazar datos estructurados devueltos por las tools con memoria o estimaciones.

## Tools

### `prepare_ar_registration`

Es la entrada preferida para una intención de registro. Acepta `domain`, `default_zone` y `provider`. Si la persona da solamente un nombre, se aplica `.com.ar` por defecto y debe hacerse visible en el resumen.

Una salida lista requiere simultáneamente:

- WHOIS con estado `available`;
- arancel vigente encontrado para la zona;
- enlace de TAD verificado contra las páginas oficiales actuales.

`ok: true` significa solamente que el traspaso a la persona está listo. Nunca significa que el dominio fue comprado.

### `check_ar_domain`

Consulta el protocolo WHOIS documentado por NIC Argentina. Devuelve únicamente campos operativos y omite datos personales del titular. Sirve para disponibilidad y para verificar después del pago que el dominio figure registrado.

### `get_nic_ar_prices`

Lee `https://nic.ar/dominios/aranceles` en cada llamada y devuelve importes ARS con fecha de observación. Si cambia la estructura HTML y el parser deja de reconocerla, devuelve error explícito; no usa precios embebidos.

## Fuentes y enlace final

- WHOIS: `https://nic.ar/es/whois/info`
- Aranceles: `https://nic.ar/dominios/aranceles`
- Servicio de registro: `https://www.argentina.gob.ar/servicio/registrar-un-dominio-de-internet`
- Buscador alternativo: `https://nic.ar/buscar-dominio`
