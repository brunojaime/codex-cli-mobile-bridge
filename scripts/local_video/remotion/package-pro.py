"""Package only validated, non-secret public video deliverables."""
from pathlib import Path
import json
import zipfile
p=Path(__file__).resolve().parent
out=p.parents[2]/'reports/videos/nienfos-10-profesional'
stories=json.loads((p/'campaign-pro.json').read_text())
validation=json.loads((out/'validation.json').read_text())
motion=json.loads((out/'motion-validation.json').read_text())
assert validation['all_passed'] and motion['all_passed']
assert len(validation['videos'])==10
archive=out/'Nienfos-10-profesional.zip'
notes=['Nienfos · revisión profesional 02','10 videos verticales sin audio.','']
for s,v in zip(stories,validation['videos']):
 notes.append(f"{s['id']} · {s['title']} · {v['duration_seconds']:g} s")
notes+=['','Material original de Nienfos y capturas públicas de nienfos.com.','Las pantallas de RD muestran únicamente el acceso público.','Los diagramas son composiciones explicativas.','No se incorporan datos internos.']
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:
 for s in stories:z.write(out/s['id']/'video.mp4',f"Nienfos-profesional-{s['id']}.mp4")
 z.writestr('LEEME.txt','\n'.join(notes)+'\n')
report=out/'README.md'
text=report.read_text()
text+='\n[Descargar las diez versiones en ZIP](Nienfos-10-profesional.zip) · [Validación de movimiento](motion-validation.json)\n\n'
text+='Se revisaron láminas de escenas y transiciones. Se conservó la [entrega anterior](../nienfos-10-versiones/README.md).\n'
report.write_text(text)
print(f'PACKAGE {archive.stat().st_size/1e6:.1f} MB')
