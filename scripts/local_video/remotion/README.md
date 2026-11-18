# Remotion local

Instalación de Remotion CLI y React separada del backend y de la aplicación móvil.
Remotion 4.0.540 queda fijado junto con sus dependencias en `package-lock.json`.

Desde esta carpeta:

```bash
nvm use
npm ci
npm run versions
npm run check:browser
```

Requiere Node >=22.12; `.nvmrc` selecciona el Node 22.22.2 disponible en este host.
La configuración reutiliza `/usr/bin/google-chrome` si existe; puede indicarse otro
binario con `REMOTION_BROWSER_EXECUTABLE`. En otro equipo sin Chrome, ejecutar
`npm run browser:ensure` para descargar el navegador de Remotion.

Validación local: versiones Remotion alineadas y navegador abierto/cerrado por el
renderer sin producir un video. La descarga automática de Chrome Headless Shell
falló por timeout de red; se utiliza Chrome ya instalado en este host.

Incluye una primera composición institucional de Nienfos, identificada como
borrador y usada como ejemplo a falta de un brief de marca. Cuatro escenas,
24 segundos, vertical 720×1280, 30 fps. Se conserva el logo original sin modificar.
Las recetas anteriores de Python/FFmpeg no se migraron automáticamente.

```bash
npx remotion studio src/index.ts
npx remotion render src/index.ts Institucional out/visual-sin-audio.mp4 --codec=h264 --concurrency=2
```

La narración se prepara con `../voice.py narration.json --output CARPETA/voice`
usando el Python del laboratorio. `finish.py CARPETA` exige el visual como
`CARPETA/visual-sin-audio.mp4`, agrega las cuatro frases sin acelerar la voz,
mezcla la música aprobada y valida la decodificación del MP4. Conserva una versión
sin música, los WAV y el SRT. No llama APIs de modelos ni contrata servicios cloud.

El borrador entregado se encuentra en
[`reports/videos/institucional-remotion-20261104`](../../../reports/videos/institucional-remotion-20261104/README.md).

La captura Playwright, la narración local y la alineación existentes pueden
reutilizarse como entradas de futuras composiciones React.

## Revisión 02 · sin audio

Por pedido del usuario, `InstitucionalAgil` ofrece una revisión de 14 segundos,
cinco escenas y tipografía cinética. No incluye componentes de audio. Exportar
con `--muted` y verificar que el archivo tenga cero pistas de audio:

```bash
npx remotion render src/index.ts InstitucionalAgil out/institucional.mp4 --codec=h264 --muted --concurrency=1
```

`check-silent.py CARPETA` decodifica el MP4, comprueba sus 420 fotogramas, título
inicial visible y ausencia de audio, y extrae portada y lámina de escenas.
Entrega: [institucional silencioso](../../../reports/videos/institucional-remotion-v2-silencioso/README.md).

## Diez propuestas de Nienfos

`campaign.json` contiene diez guiones diferentes orientados a los servicios y
casos publicados en nienfos.com. `src/Campaign.tsx` registra `Nienfos-01` a
`Nienfos-10`. Incluye composición de portada, océano, tarjetas, conexiones,
proceso y casos públicos. Todos se exportan sin pista de audio.

`capture-site.mjs` captura únicamente la web pública en un contexto anónimo.
Ejecutar después `prepare-site.py` con el Python del laboratorio para extraer
los fondos listos para el render.
Los fondos usados se extrajeron de los últimos ocho segundos de cada grabación,
a 15 fps; la composición tipográfica se renderiza a 30 fps. Se usan secuencias
de imágenes para evitar la decodificación repetida de video durante el render.
La animación de desplazamiento de las ballenas se capturó a velocidad ×3.
Los recursos conservan procedencia y huellas en `public/campaign/provenance.json`.

```bash
node render-campaign.mjs
# Repetir sólo algunas variantes:
node render-campaign.mjs 01 08
```

Con el Python del laboratorio, `check-campaign.py` decodifica las diez entregas,
verifica fotogramas/resolución/duración y cero pistas de audio, y genera
contactos de escenas, catálogo HTML autónomo y reporte Markdown.
`check-campaign.py 01` permite verificar sólo una entrega durante el trabajo.

[Catálogo de diez versiones](../../../reports/videos/nienfos-10-versiones/README.md).

## Licencia y costos consultados el 04/11/2026

- Uso individual u organizaciones/equipos de hasta 3 personas: gratuito, también
  para videos comerciales y automatización, sujeto a los términos oficiales.
- Organizaciones no elegibles para la licencia gratuita: Creators cuesta USD 25
  por usuario/mes para creación manual; Automators cuesta USD 0,01 por render con
  un mínimo de USD 100/mes para automatización.
- El tamaño corresponde a la organización, no sólo a quienes usan Remotion.
- Puede evaluarse gratuitamente antes del uso comercial. No se verificó el tamaño
  de la organización ni se compró una licencia.
- El renderizado local no requiere contratar infraestructura cloud.

Fuentes oficiales: [precios](https://www.remotion.dev/docs/license/pricing),
[preguntas de licencia](https://www.remotion.dev/docs/license/faq) y
[licencia del código instalado](https://github.com/remotion-dev/remotion/blob/v4.0.540/LICENSE.md).
Revisar los términos aplicables antes de iniciar uso comercial; pueden cambiar.

### Revisión profesional de las diez versiones

La revisión conserva los diez enfoques y los archivos anteriores. `campaign-pro.json`
contiene las escenas y tiempos; `campaign-pro-direction.json` documenta las decisiones.
`src/CampaignPro.tsx` incorpora transiciones superpuestas, títulos cinéticos,
encuadres de proyectos con perspectiva y ballenas originales ampliadas.
La revisión es completamente silenciosa.

Con Node 22, desde esta carpeta:

```bash
node render-pro.mjs
/home/batata/.local/share/rd-video-lab/venv/bin/python check-pro.py
/home/batata/.local/share/rd-video-lab/venv/bin/python check-pro-motion.py
```

Entregables: [catálogo de la revisión profesional](../../../reports/videos/nienfos-10-profesional/README.md).
La verificación de movimiento mide variación entre imágenes de cada escena; la calidad
visual se revisa además en las láminas de escenas y transiciones.
