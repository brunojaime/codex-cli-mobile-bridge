# Audio Session Export And Identification

## Idea General

El objetivo es armar un flujo para una computadora Linux usada por la banda
durante la grabacion. La sesion de grabacion debe partir de una base estable:
pistas preparadas, entradas ordenadas y una mezcla tipo ya definida, pero sin
exigir una produccion fina para cada toma.

La calidad de audio no necesita ser extrema, pero si debe tener una base buena.
La idea es preparar una plantilla de mezcla con criterios razonables, por
ejemplo ruteos, buses, EQ, compresores, limitadores y niveles iniciales. Esa
plantilla se define una vez y luego se reutiliza para futuras grabaciones sin
tocar la mezcla base, salvo que mas adelante se decida mejorarla como version
del sistema.

El alcance de esta etapa no es producir un master final profesional. El alcance
es llegar a una carpeta exportada con los temas separados, en WAV estereo,
nombrados correctamente, y empaquetados junto con el proyecto en un ZIP.

## Flujo Esperado

1. La banda abre una sesion base en la computadora Linux.
2. La sesion ya tiene las pistas, entradas y ruteos preparados.
3. Durante la grabacion, los procesos que puedan generar latencia o consumo
   innecesario deberian estar apagados, bypassed u offline.
4. La banda graba una toma larga, con varios temas en una misma sesion.
5. Entre tema y tema deberia haber silencios notorios o momentos claramente
   separables.
6. Al terminar, se aplica la mezcla base post-grabacion.
7. El sistema detecta los bloques de audio correspondientes a cada tema.
8. Cada bloque se compara contra una biblioteca de grabaciones de referencia.
9. El sistema identifica que cancion es cada bloque.
10. Se exporta cada tema como WAV estereo con el nombre correcto.
11. Se genera un ZIP final con el proyecto, los audios exportados y metadatos.

## Sesion Base De Grabacion

La sesion base deberia funcionar como una plantilla reusable. No deberia exigir
que alguien arme el proyecto desde cero antes de cada grabacion.

Deberia incluir:

- Pistas ya creadas y nombradas.
- Entradas de audio ya asignadas.
- Ruteo hacia buses o grupos.
- Una cadena de mezcla base para post-grabacion.
- Opciones de exportacion ya preparadas o automatizables.
- Una estructura de carpetas predecible para proyecto, takes, exports y logs.

Durante la grabacion, conviene investigar cual es la forma mas estable de dejar
la sesion liviana. Algunas posibilidades a evaluar:

- Plugins apagados durante la toma y activados solo para exportar.
- Plugins en bypass si eso alcanza sin consumir recursos importantes.
- Version de la plantilla "recording" y version "mix/export".
- Congelado, render previo o alternativas del DAW si hiciera falta.

La decision final depende de pruebas reales en la maquina Linux, la interfaz de
audio, el tamano de las sesiones y la latencia aceptable.

## Mezcla Base

La mezcla base deberia ser consistente, no artesanal para cada toma. Tiene que
dejar el material presentable y evitar problemas obvios: volumen muy bajo,
clipping, dinamica demasiado descontrolada o diferencias grandes entre temas.

Elementos a considerar:

- EQ correctiva general por pista o bus.
- Compresion suave.
- Limitador en el master.
- Normalizacion o ajuste de ganancia previo a exportar.
- Buses para ordenar instrumentos o fuentes.
- Control de picos.
- Objetivo de loudness razonable segun el uso final.

No se deberia cerrar todavia una cadena exacta de plugins o tecnologia. Esa es
parte de la investigacion. Lo importante es que la mezcla quede guardada como
plantilla o preset versionado, para que futuras grabaciones usen el mismo
criterio.

## Corte Automatico En Temas

La grabacion larga debe separarse en temas individuales. Como entre tema y tema
va a haber silencios notorios, el primer enfoque deberia ser detectar esos
espacios y crear segmentos candidatos.

Aspectos a resolver:

- Umbral de silencio.
- Duracion minima para considerar que hay separacion entre temas.
- Margen antes y despues del audio util.
- Fades automaticos para evitar clicks.
- Manejo de charla, ruido o afinacion entre temas.
- Revision de cortes dudosos.

El resultado de esta etapa no deberia asumir todavia el nombre de la cancion.
Solo deberia producir segmentos como:

```text
segment_001
segment_002
segment_003
```

Luego esos segmentos se identifican por similitud contra referencias.

## Identificacion Por Similitud De Audio

Este es el camino principal. No se quiere depender solamente del orden del
repertorio. El sistema debe poder reconocer que cancion es cada segmento,
comparandolo contra una biblioteca de grabaciones de referencia de estudio.

La biblioteca de referencia deberia estar formada por audios bien nombrados:

```text
references/
  Cancion A.wav
  Cancion B.wav
  Cancion C.wav
```

Para cada segmento detectado, el sistema deberia compararlo contra todas las
referencias disponibles y devolver un ranking de candidatos.

La investigacion debe evaluar que senales conviene combinar. Posibles lineas:

- Similitud armonica.
- Similitud ritmica.
- Forma o estructura de la cancion.
- Fingerprints de audio cuando sean utiles.
- Embeddings o modelos de clasificacion musical.
- Comparacion robusta ante cambios de tempo, tonalidad, intro o final.
- Tolerancia a versiones en vivo distintas de la version de estudio.

La hipotesis de trabajo es que, si una persona identifica facilmente la cancion,
el sistema deberia poder lograrlo con una combinacion de analisis musical,
clasificacion y sincronizacion.

## Sincronizacion Contra Referencias

Despues de obtener candidatos, el sistema deberia intentar sincronizar el
segmento grabado contra la referencia correspondiente. Esta sincronizacion no
deberia depender de que los audios sean identicos.

Debe tolerar:

- Tempo diferente.
- Intro mas corta o mas larga.
- Final extendido.
- Partes repetidas.
- Errores menores de interpretacion.
- Diferencias de mezcla o instrumentacion.

La tecnologia exacta para esta etapa queda como investigacion. Lo importante es
que la sincronizacion sirva para aumentar la confianza de la identificacion y,
eventualmente, para mejorar los cortes si el inicio o final detectado por
silencio no fue perfecto.

## Confianza Y Revision

El sistema deberia producir una decision con nivel de confianza, no solamente un
nombre.

Ejemplo de salida esperada:

```json
{
  "segment": "segment_002",
  "bestMatch": "Cancion B",
  "confidence": 0.93,
  "alternatives": [
    { "name": "Cancion D", "score": 0.41 },
    { "name": "Cancion F", "score": 0.32 }
  ]
}
```

Si la confianza es alta, se puede nombrar automaticamente el archivo exportado.
Si la confianza es baja, el segmento deberia quedar marcado para revision.

El sistema tambien deberia detectar casos problematicos:

- Mas segmentos que canciones identificables.
- Menos segmentos que los esperados.
- Dos segmentos asignados a la misma cancion.
- Cancion no encontrada en referencias.
- Corte demasiado corto o demasiado largo.

## Exportacion WAV Estereo

El resultado principal de esta etapa son archivos WAV estereo separados y
nombrados correctamente.

Ejemplo:

```text
exports/
  01 - Cancion A.wav
  02 - Cancion B.wav
  03 - Cancion C.wav
```

El orden puede venir del orden real de los segmentos en la grabacion. El nombre
viene de la identificacion por similitud.

Tambien conviene generar metadatos:

```text
exports/
  manifest.json
  identification_report.json
```

El `manifest.json` deberia registrar:

- Nombre final del archivo.
- Segmento de origen.
- Inicio y fin dentro de la sesion larga.
- Cancion identificada.
- Confianza.
- Referencia usada.
- Version de la plantilla de mezcla.
- Fecha de exportacion.

## ZIP Final

Ademas de exportar los WAV estereo, el flujo debe generar un ZIP con todo lo
necesario para archivar o mover la sesion.

El ZIP deberia incluir:

- Proyecto de la sesion.
- Audios originales necesarios para abrir el proyecto.
- WAV estereo exportados por tema.
- Manifest de exportacion.
- Reporte de identificacion.
- Logs del proceso.
- Version de la plantilla o preset usado.

Estructura sugerida:

```text
session-export.zip
  project/
    session-project-files...
  source-audio/
    original-recordings...
  exports/
    01 - Cancion A.wav
    02 - Cancion B.wav
    03 - Cancion C.wav
  metadata/
    manifest.json
    identification_report.json
    process.log
```

La composicion exacta depende del DAW y de como guarde sus proyectos, pero el
principio es que el ZIP debe permitir conservar tanto el resultado final como la
sesion que lo produjo.

## Investigacion Pendiente

Antes de implementar, hay que validar varias decisiones tecnicas:

- Que DAW o motor de audio conviene automatizar en Linux.
- Como conviene guardar y versionar la plantilla de grabacion y mezcla.
- Como activar la mezcla post-grabacion sin afectar la toma.
- Que estrategia de deteccion de silencio funciona mejor con las grabaciones
  reales.
- Que tipo de analisis de similitud identifica mejor las canciones de la banda.
- Como sincronizar una toma en vivo contra una referencia de estudio.
- Que umbrales de confianza son aceptables para nombrado automatico.
- Como presentar o resolver segmentos dudosos.
- Como empaquetar el proyecto completo sin perder dependencias externas.

## Alcance De Esta Etapa

Esta etapa termina cuando el sistema puede tomar una sesion grabada, separar los
temas, identificar sus nombres por similitud contra referencias, exportar WAV
estereo correctamente nombrados y generar un ZIP con el proyecto y los audios.

Quedan fuera de esta etapa:

- Mastering profesional.
- Edicion musical manual fina.
- Correccion de interpretacion.
- Mezcla personalizada por cancion.
- Publicacion automatica a plataformas externas.

La prioridad es construir un flujo confiable, repetible y suficientemente bueno
para que futuras grabaciones salgan ordenadas sin rehacer el proceso a mano.
