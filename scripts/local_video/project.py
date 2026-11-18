"""Prepare an explicitly requested project-local video. No renderer or model calls."""
from pathlib import Path
import argparse
import json
import re

ENGINE = Path(__file__).resolve().parent
PYTHON = Path.home()/'.local/share/rd-video-lab/venv/bin/python'


def prepare(workspace, feature_id, feature, request_ref, *, feature_ready=False,
            fast=False, engine=ENGINE, python=PYTHON):
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir() or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', feature_id):
        raise ValueError('Workspace existente e ID simple requeridos')
    if not feature.strip() or len(feature)>500 or not request_ref.strip() or len(request_ref)>300:
        raise ValueError('Función y referencia al pedido explícito requeridas')
    folder = workspace/'.local-videos'/feature_id
    output = workspace/'reports'/'videos'/feature_id
    for path in [folder, output]:
        if not path.resolve().is_relative_to(workspace):
            raise ValueError('El pedido y la entrega deben permanecer en el workspace')
    engine = Path(engine).resolve()
    config_paths = [engine/'voices.json',engine/'skill/local-feature-videos/default-music-plan.json']
    required = [Path(python),engine/'voice.py',engine/'align.py',engine/'music.py',
                engine/'guide_qc.py',engine/'editorial.py',engine/'screen_template.py',engine/'skill/local-feature-videos/default-screen-template.json',*config_paths]
    missing = [str(p) for p in required if not p.is_file()]
    voice = 'peter-fast' if fast else 'voz-1'
    music = None
    if config_paths[0].is_file():
        cfg=json.loads(config_paths[0].read_text())
        voice='peter-fast' if fast else cfg['default']
        profile=cfg['profiles'][voice]
        if 'reference' in profile and not (engine/profile['reference']).is_file():
            missing.append(str(engine/profile['reference']))
    if config_paths[1].is_file():
        music=json.loads(config_paths[1].read_text())
    record = {
        'version':1,'workspace':str(workspace),'feature_id':feature_id,
        'feature':feature.strip(),'request_ref':request_ref.strip(),
        'status':'blocked_resources' if missing else ('awaiting_recipe' if feature_ready else 'awaiting_feature_validation'),
        'feature_validated':bool(feature_ready),'voice':voice,'fast_explicit':bool(fast),
        'music':music,'max_duration_seconds':60,'engine':str(engine),
        'python':str(python),'output':str(output.relative_to(workspace)),
        'recipe':None,'blockers':missing,'render_started':False,
        'screen_template':json.loads((engine/'skill/local-feature-videos/default-screen-template.json').read_text()) if (engine/'skill/local-feature-videos/default-screen-template.json').is_file() else None,
        'source_ui_rect':None,
        'preflight_scope':'files only; verify dependencies, offline model cache and project adapter before rendering',
        'next_steps':['validate feature','adapt real project actions and script','compact brief and pacing plan',
                      'local capture, voice cache, render and music','media checks and workspace delivery'],
    }
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'request.json'
    if target.is_symlink():
        raise ValueError('El registro del pedido no puede ser un enlace simbólico')
    try:
        with target.open('x') as handle:
            json.dump(record,handle,ensure_ascii=False,indent=2);handle.write('\n')
    except FileExistsError:
        existing=json.loads(target.read_text())
        for key in ['workspace','feature_id','feature','voice','fast_explicit']:
            if existing[key]!=record[key]:
                raise ValueError('El ID ya corresponde a otro pedido; usar otro ID o revisar el registro existente')
        return {'created':False,'path':str(target),'request':existing}
    return {'created':True,'path':str(target),'request':record}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--feature-id',required=True)
    p.add_argument('--feature',required=True)
    p.add_argument('--request-ref',required=True)
    p.add_argument('--feature-ready',action='store_true')
    p.add_argument('--fast',action='store_true',help='Only if the user explicitly requested speed')
    a=p.parse_args()
    try:
        result=prepare(a.workspace,a.feature_id,a.feature,a.request_ref,feature_ready=a.feature_ready,fast=a.fast)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:
        p.exit(2,str(exc)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
