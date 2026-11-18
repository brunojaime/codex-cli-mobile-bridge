# Plantilla vertical con pantalla grande

Usar por defecto `default-screen-template.json` para los nuevos videos: márgenes de
12 px, cabecera de 30 px y subtítulos de 84 px en un cuadro de 720×1280. Personalizar
`client`, `background` y `accent` para el cliente; apertura y cierre siguen la
plantilla de placas con sus logos auténticos. La app ocupa el máximo rectángulo
posible manteniendo su proporción, sin recortar controles. En la captura RD aumenta
del 62 % al 88 % del cuadro. Otras proporciones pueden ocupar menos: adaptar la
captura a un viewport móvil y comprobar el resultado, nunca estirar la imagen.

`screen_template.py` compone la captura existente, conserva tiempos y copia el audio
codificado. Declarar `--source-ui X Y ANCHO ALTO` con la geometría real del adaptador;
no copiar coordenadas RD para otro proyecto. Aplicar después de los efectos de
pulsación: así se escalan juntos y permanecen alineados. El SRT se conserva, con
subtítulos de hasta dos líneas, fuera del área de la app. Si no caben, el script
rechaza el render; dividir las frases y revisar sus tiempos, no reducir la letra.

Ejemplo RD desde el Bridge:

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/screen_template.py \
 --source reports/rd-video-musica-ajuste-20260929/final \
 --output reports/mi-video-pantalla-grande \
 --plan reports/rd-video-pantalla-grande-20260929/template.json \
 --source-ui 68 99 584 978
```

`run_guided.py` aplica por defecto esta composición y devuelve `final_output` en
`run.json`. La salida entregable queda en `pantalla-grande/`; las etapas intermedias
se conservan. Si se agregan efectos después, producir primero la guía en la geometría
original y ejecutar luego la composición final. No aplicar dos veces el rectángulo
original a un video ya ampliado: consultar `ui_rect` de sus metadatos.

Para cada receta revisar inicio, controles con pulsos, subtítulos y cierre en el
MP4 final. Conservar versión anterior y comparar ocupación de pantalla, audio y
cronología. Es montaje local, sin APIs de modelos ni nueva voz. El guion y las
adaptaciones del proyecto siguen siendo trabajo de Codex.
