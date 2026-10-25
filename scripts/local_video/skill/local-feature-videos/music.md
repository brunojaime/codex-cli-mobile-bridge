# Fondo musical local opcional

`music.py` añade una base original procedural de acordes sostenidos (warm-pad-v1),
sin voz ni percusión, sin grabaciones externas ni modelos. El video y el WAV de
narración se reutilizan. Preferencia actual del usuario: entregar con música con el último +1 dB aprobado, 3 dB por encima de B original (18 dB por debajo de la voz, más 4 dB de atenuación). La base recurrente elegida explícitamente es B, `light-keys`. Usarla salvo otra indicación. La salida seca se conserva para comparación.

Usar un `music-plan.json` con exactamente estas claves:

```json
{"version":1,"mode":"light-keys","level_db_below_voice":18,"duck_db":4,"fade_in_seconds":1.2,"fade_out_seconds":1.8,"duck_attack_seconds":0.18}
```

`mode` admite `none`, `soft-ambient`, `soft-pulse` (A, 92 BPM) o `light-keys` (B, 100 BPM). Los nuevos presets tienen articulación suave, sin pista de batería ni voces. Se iguala su sonoridad integrada con la base ambiental de referencia mediante FFmpeg; no aumentar el volumen aprobado para simular más energía. Nivel: 18–40 dB por debajo de la voz activa;
atenuación adicional: 0–12 dB. Entradas/salidas: 0,5–4 s; ataque: 0,05–0,5 s.
La atenuación comienza antes de la voz y permanece hasta el final, también en las
pausas: no hay una subida automática entre frases. Codex elige los parámetros.
El script no decide el estilo mediante otro modelo.

Desde el Bridge, ejecutar con el Python local del laboratorio:

```bash
/home/batata/.local/share/rd-video-lab/venv/bin/python scripts/local_video/music.py \
  --source reports/rd-video-editorial-20260929 \
  --plan scripts/local_video/skill/local-feature-videos/default-music-plan.json \
  --output reports/mi-video-con-musica
```

Se puede agregar `--music-plan PLAN` a `run_guided.py`: conserva la salida sin música
y añade la variante en `con-musica/`. No sobrescribir el origen. Revisar `music.json`
(niveles y procedencia), `mezcla.wav`, narración aislada y MP4; ofrecer comparación
con/sin música. Decidir si mejora la experiencia escuchándola, sin prometerlo sólo
por los niveles medidos. La composición y mezcla se ejecutan localmente; elegir o
modificar parámetros desde el chat sigue usando Codex.

Los presets tienen patrones deterministas: la misma configuración reproduce la misma base.
La preferencia está en `music-preference.json`; actualizar el estilo elegido sólo
cuando el usuario lo decida. Ejemplos A/B en `reports/rd-musica-opciones-20260929/`.
