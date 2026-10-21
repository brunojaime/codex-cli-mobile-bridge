"""Verify promotion of the approved mix into shared defaults and new requests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from project import prepare

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'scripts/local_video/skill/local-feature-videos'
INSTALLED = Path.home()/'.codex/skills/local-feature-videos'
APPROVED = ROOT/'reports/rd-video-musica-ajuste-20260929'
PYTHON = Path.home()/'.local/share/rd-video-lab/venv/bin/python'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

facts = {}
try:
    plan = json.loads((APPROVED/'music-plan.json').read_text())
    for folder in [SOURCE, INSTALLED]:
        assert json.loads((folder/'default-music-plan.json').read_text()) == plan
        preference = json.loads((folder/'music-preference.json').read_text())
        assert preference['duck_db'] == plan['duck_db'] == 4
        assert preference['level_db_below_voice'] == plan['level_db_below_voice'] == 18
        assert preference['selected_recurring_style'] == plan['mode'] == 'light-keys'
        assert preference['decision_ref'] == 'source-d4f50975c25194451d291fc3'
        subprocess.run([str(ROOT/'.venv/bin/python'), str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'), str(folder)],check=True)
    for name in ['music.md','music-preference.json','default-music-plan.json']:
        assert (SOURCE/name).read_bytes() == (INSTALLED/name).read_bytes()
    facts['shared-approved-music'] = True
    with tempfile.TemporaryDirectory(prefix='default-music-check-') as temp:
        temp = Path(temp)
        for name in ['project-a','project-b']:
            workspace = temp/name; workspace.mkdir()
            first = prepare(workspace,'feature','Función DEMO','test:explicit')
            record = Path(first['path']); before = record.read_bytes()
            assert first['request']['music'] == plan
            assert first['request']['voice'] == 'voz-1'
            assert first['request']['max_duration_seconds'] == 60
            assert not first['request']['render_started']
            assert not prepare(workspace,'feature','Función DEMO','test:explicit')['created']
            assert record.read_bytes() == before
        facts['new-project-inheritance'] = True
        output = temp/'render'
        subprocess.run([str(PYTHON),str(ROOT/'scripts/local_video/music.py'),
                        '--source',str(ROOT/'reports/rd-video-acciones-20260929/sin-musica'),
                        '--plan',str(INSTALLED/'default-music-plan.json'),
                        '--output',str(output)],check=True,capture_output=True,text=True)
        for name in ['rd-documentos-completo.mp4','narracion.wav','mezcla.wav']:
            assert sha(output/name) == sha(APPROVED/'final'/name), name
        print('Approved MP4 reproduced: '+sha(output/'rd-documentos-completo.mp4'))
        facts['default-render-equivalence'] = True
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
