# Hacer visibles las acciones sin otro modelo

Cuando se pida mejorar dónde se toca, se puede añadir un contorno breve al control
y un pulso discreto sobre la grabación real. `actions.py` aplica un plan JSON ligado
por SHA al MP4 fuente: tiempos, control, posición, rótulo y tipo (`tap`, `focus`,
`status`). Rechaza coordenadas fuera de la interfaz, marcas sin acción conocida,
tiempos inválidos o separados del evento y superposiciones entre indicaciones.

Ejemplo comprobado: `reports/rd-video-acciones-20260929/actions-plan.json` del Bridge.
Las posiciones son específicas de ese video de 720×1280; para otra receta deben
obtenerse del grabador o inspeccionarse en unas pocas capturas de las acciones.
No inferirlas ciegamente. El pulso es una indicación editorial de la acción, no
telemetría exacta del dedo. Se compara cada marca con imágenes y tiempos del recorrido.

Primero `actions.py --source ORIGEN --plan PLAN --output CON_GUIA`; luego `music.py`
con la salida de guía como origen y el plan musical predeterminado. Mantener la
narración intacta. Comparar duración, subtítulos, sincronización y niveles; revisar
fotogramas con y sin guía. Codex decide los parámetros una vez, el montaje no llama
APIs de modelos. Los ejemplos conservan su primera edición para comparar.

La captura del navegador RD no incluye la ventana nativa del selector de archivos:
la automatización adjunta el PDF y muestra el resultado. No dibujar un selector
inventado. Si se pide mostrar esa ventana, hace falta una nueva captura del escritorio
con datos DEMO y revisar el ritmo del tramo; un resaltado no sustituye ese recorrido.

Música B: nivel 18 dB bajo la voz activa, más 4 dB de atenuación sostenida,
según el último volumen aprobado. No modificar voz ni subir automáticamente la base
en pausas. Verificar la mezcla también en el MP4; no declarar escucha si sólo se midió.
