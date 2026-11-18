"""Verify all ten actual exports and build an offline mobile review catalog."""
from pathlib import Path
import hashlib
import html
import json
import sys

import av
from PIL import Image,ImageDraw,ImageFont

root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-10-profesional'
stories=json.loads((Path(__file__).parent/'campaign-pro.json').read_text())
selected=sys.argv[1:]
results=[]
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',18)
small=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',14)
for story in stories:
    if selected and story['id'] not in selected:continue
    folder=out/story['id'];movie=folder/'video.mp4'
    expected=round(sum(s['seconds'] for s in story['scenes'])*30)
    targets={}
    cursor=0
    for i,s in enumerate(story['scenes']):
        targets[cursor+round(s['seconds']*15)]=f'escena-{i+1}.jpg'
        cursor+=round(s['seconds']*30)
    pictures={}
    with av.open(str(movie)) as container:
        assert len(container.streams.audio)==0,story['id']+' contains audio'
        stream=container.streams.video[0]
        assert (stream.width,stream.height)==(720,1280)
        duration=float(stream.duration*stream.time_base)
        assert abs(duration-expected/30)<.05
        count=0
        for frame in container.decode(video=0):
            if count in targets or count==45:
                im=frame.to_image()
                if count==45:im.save(folder/'portada.jpg',quality=92)
                if count in targets:
                    im.save(folder/targets[count],quality=92);pictures[targets[count]]=im
            count+=1
        assert count==expected,(story['id'],count,expected)
    board=Image.new('RGB',(240*len(story['scenes']),467),'#e5ebe8');draw=ImageDraw.Draw(board)
    for i,s in enumerate(story['scenes']):
        im=pictures[f'escena-{i+1}.jpg'].copy();im.thumbnail((240,427));board.paste(im,(i*240,35))
        draw.text((i*240+12,8),f"{i+1:02d} · {s['seconds']} s",font=small,fill='#1b3038')
    board.save(folder/'escenas.jpg',quality=92)
    result={'id':story['id'],'title':story['title'],'focus':story['focus'],'duration_seconds':duration,
      'frames':count,'size':[720,1280],'fps':30,'audio_streams':0,'bytes':movie.stat().st_size,
      'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),'checks':{'full_decode':True,'zero_audio_tracks':True,'expected_frames':True},
      'real_website_capture':any(s['layout'] in ['hero','ocean'] for s in story['scenes'])}
    (folder/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    results.append(result)
    print('VERIFIED '+story['id']+' '+str(duration)+'s; zero audio tracks',flush=True)
if selected:sys.exit(0)
assert len(results)==10
overview=Image.new('RGB',(1200,1010),'#e5ebe8');draw=ImageDraw.Draw(overview)
for n,s in enumerate(stories):
    image=Image.open(out/s['id']/'portada.jpg');image.thumbnail((240,427))
    x=(n%5)*240;y=(n//5)*505
    overview.paste(image,(x,y+35));draw.text((x+12,y+8),'Nienfos / '+s['id'],font=font,fill='#1b3038')
    # Short identifying line remains readable under each poster.
    draw.text((x+10,y+470),s['title'][:25],font=small,fill='#1b3038')
overview.save(out/'comparativa.jpg',quality=94)
report=['# Nienfos · 10 versiones · revisión profesional sin audio','',
  'Diez propuestas verticales de 720×1280 a 30 fps. Cada archivo contiene cero pistas de audio. Se conservaron las versiones anteriores.',
  '', 'Las versiones **01, 08 y 10** incorporan la portada o el océano con las ballenas de [nienfos.com](https://nienfos.com/), capturados del sitio público. Las demás desarrollan sus servicios y su forma de trabajo con composiciones gráficas.',
  '', 'Revisión 02: paleta de marca unificada, títulos cinéticos, perspectiva y acercamientos en las imágenes, barridos superpuestos de 15 fotogramas y escenas más breves. Sin música ni voz.', '', '![Vista de las diez versiones](comparativa.jpg)','',
  '| Versión | Enfoque | Duración | Archivos |','|---|---|---:|---|']
for s,r in zip(stories,results):
    report.append(f"| {s['id']} · {s['title']} | {s['focus']} | {r['duration_seconds']:g} s | [Video]({s['id']}/video.mp4) · [Escenas]({s['id']}/escenas.jpg) |")
report += ['', '[Abrir catálogo con reproductores](catalogo.html)', '',
  'Las imágenes de Chrem Propiedades y Consultora RD proceden del material publicado en el sitio de Nienfos. La pantalla de RD es su acceso público; no se muestran datos internos ni se presenta el acceso como una demostración de su gestión privada.',
  '', 'Los diagramas de conexión y las tarjetas de gestión son recursos explicativos, no capturas de un producto en uso. No se inventaron métricas ni resultados de clientes.',
  '', 'Se usaron logos originales y Noto Sans. El fondo oceánico conserva los gráficos del sitio; en la captura aislada se aceleró tres veces el desplazamiento de las ballenas. Las escenas oceánicas amplían y animan también la geometría original de las ballenas de la web para que se vea mejor en vertical; ese recurso es una composición del video, no una captura literal del sitio. No se generaron ballenas nuevas.',
  '', 'Verificación: decodificación completa de los diez MP4, cantidad de fotogramas, duración, resolución y ausencia de pistas de audio. Se extrajeron fotogramas de cada escena para la revisión visual. No se publicaron archivos en redes ni se contrataron servicios.',
  '', '[Resultados de validación](validation.json) · [Procedencia web](../nienfos-10-versiones/source/source.json) · [Texto público consultado](../nienfos-10-versiones/source/website-text.txt)']
(out/'README.md').write_text('\n'.join(report)+'\n')
(out/'validation.json').write_text(json.dumps({'videos':results,'all_passed':True,'audio_policy':'zero streams','external_model_api_calls':0},ensure_ascii=False,indent=2)+'\n')
cards=[]
for s,r in zip(stories,results):
    sid=s['id'];cards.append(f'<article><p class="eyebrow">VERSIÓN {sid} · {r["duration_seconds"]:g} s</p><h2>{html.escape(s["title"])}</h2><p>{html.escape(s["focus"])}</p><video controls muted playsinline preload="none" poster="{sid}/portada.jpg" src="{sid}/video.mp4"></video><p><a href="{sid}/video.mp4">Abrir MP4</a> · <a href="{sid}/escenas.jpg">Ver escenas</a></p></article>')
page='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nienfos · 10 versiones</title><style>body{margin:0;background:#10252e;color:#f4f6f5;font:16px system-ui;padding:28px}main{max-width:1200px;margin:auto}h1{font-size:clamp(32px,5vw,64px);letter-spacing:-2px}header{padding:24px 0 48px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}article{background:#1b3038;padding:24px;border:1px solid #39535d;border-radius:20px}h2{min-height:2.4em;letter-spacing:-.5px}video{display:block;width:100%;max-height:70vh;background:#10252e;border-radius:12px;margin-top:24px}a{color:#b7dce3}.eyebrow{font-size:12px;letter-spacing:2px;color:#a7ccd9}p{line-height:1.6}article>p:nth-of-type(2){min-height:3.2em;color:#b7c7cd}</style><main><header><p class="eyebrow">Nienfos · exploraciones visuales</p><h1>Diez formas de contar<br>lo que hacemos.</h1><p>Todas sin audio. Portada y ballenas reales del sitio en 01, 08 y 10.<br>Webs, software de gestión, integración, automatización y acompañamiento.</p></header><section class="grid">'+''.join(cards)+'</section></main></html>'
(out/'catalogo.html').write_text(page)
print('CATALOG COMPLETE')
