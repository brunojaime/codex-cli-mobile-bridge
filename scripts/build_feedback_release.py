"""Build the immutable development distribution from reviewed Bridge sources.

npm pack supplies web; the managed Flutter snapshot includes coordinated packages
and the same conformance engine. Promotion is a separate verified operation.
"""
import argparse, hashlib, io, json, subprocess, tarfile
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()
def build(root, output, release_id):
 output.mkdir(parents=True,exist_ok=True)
 web=root/'packages/codex-developer-feedback-web'
 version=json.loads((web/'package.json').read_text())['version']
 import re
 flutter_version=re.search(r'^version: (.+)$',(root/'packages/codex_developer_feedback_template/pubspec.yaml').read_text(),re.M)[1]
 packed=json.loads(subprocess.check_output(['npm','pack','--json','--pack-destination',str(output)],cwd=web,text=True))[0]
 artifact=output/packed['filename'];web_files={}
 with tarfile.open(artifact) as archive:
  for member in archive.getmembers():
   if member.isfile():
    name=member.name.removeprefix('package/')
    if '__pycache__' in name:raise ValueError('Generated Python cache in package')
    web_files[name]=sha(archive.extractfile(member).read())
 flutter_name=f'codex-feedback-flutter-{flutter_version}.tar.gz';target=output/flutter_name
 if target.exists():raise ValueError('Immutable artifact already exists')
 files={}
 for package in ['codex_developer_feedback_template','codex_app_updater','codex_bridge_workbench']:
  directory=root/'packages'/package
  for p in sorted(directory.rglob('*')):
   rel=p.relative_to(directory)
   if not p.is_file() or any(x in ('.dart_tool','build','node_modules','.git','.gradle') for x in rel.parts) or p.name in ('pubspec.lock','.flutter-plugins-dependencies') or p.suffix in ('.pyc',):continue
   if rel.parts[0] not in ('lib','android','ios','macos') and p.name not in ('pubspec.yaml','README.md','analysis_options.yaml'):continue
   files[package+'/'+rel.as_posix()]=p.read_bytes()
 files['tools/feedback_conformance.py']=(web/'tools/feedback_conformance.py').read_bytes()
 import gzip
 with target.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w') as archive:
  for name,data in sorted(files.items()):
   entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644;archive.addfile(entry,io.BytesIO(data))
 descriptor={'schema':'codex.feedback-release/v1','id':release_id,'status':'candidate','contract':{'canonicalVersion':3,'acceptedVersions':[1,3],'endpoint':'/feedback-batches/start-session','releaseWhenCompleteDefault':False,'supportedExecutionModes':['execute','backlog'],'backlogReceiptField':'backlogId'},'packages':{'web':{'name':'@codex/developer-feedback-web','version':version,'artifact':artifact.name,'sha256':sha(artifact.read_bytes()),'files':web_files},'flutter':{'name':'codex_developer_feedback_template','version':flutter_version,'artifact':flutter_name,'sha256':sha(target.read_bytes()),'files':{name:sha(data) for name,data in files.items()}}},'backend':{'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'installedDev':False,'installedProd':False},'scope':'Development only; QA, production and distributed APKs are not promoted.'}
 (output/(release_id+'.json')).write_text(json.dumps(descriptor,indent=2)+'\n')
 return descriptor
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--id',required=True);a=p.parse_args();print(json.dumps({'release':build(Path(__file__).resolve().parents[1],a.output.resolve(),a.id)['id']}))
