#!/usr/bin/env python3
"""Execute HTML regression checks and inspect both published Android channels."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/html-preview-153'
WORK = Path('/home/batata/.codex-bridge/releases/html-preview-153')
CACHE = ROOT / '.data/mobile-release-153'
SDK = Path.home() / '.local/share/android-sdk/build-tools/36.0.0'

def cmd(*args, cwd=ROOT, timeout=180):
    return subprocess.check_output(args, cwd=cwd, text=True, timeout=timeout)

def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    observations = {}
    results = {}
    target_before = target_after = None
    try:
        commit = json.loads((OUT/'release.json').read_text())['commit']
        def target():
            release = json.loads(cmd('gh','release','view','android-v1.0.0-build.153','--json','tagName'))
            actual = cmd('gh','api','repos/brunojaime/codex-cli-mobile-bridge/commits/'+release['tagName'],'--jq','.sha').strip()
            return {'environment':'dev','origin':'https://github.com','release_id':release['tagName']+'@'+actual}
        target_before = target()
        tests = ['html_document_test.dart','html_file_preview_test.dart','session_file_screen_test.dart','message_tables_test.dart','chat_controller_latency_test.dart','project_secrets_sheet_test.dart']
        with (OUT/'registered-tests.jsonl').open('w') as log:
            tested = subprocess.run(['flutter','test','--no-pub',*['test/'+t for t in tests],'--reporter','json'],cwd=WORK/'frontend/mobile_app',stdout=log,stderr=subprocess.STDOUT,timeout=420)
        events=[]
        for line in (OUT/'registered-tests.jsonl').read_text().splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
        summary={'exit_code':tested.returncode,'passed':sum(e.get('type')=='testDone' and e.get('result')=='success' and not e.get('hidden') for e in events),'complete':any(e.get('type')=='done' and e.get('success') for e in events)}
        (OUT/'registered-test-summary.json').write_text(json.dumps(summary,indent=2))
        for channel in ['prod','dev']:
            suffix = '-dev' if channel == 'dev' else ''
            tag = f'android{suffix}-v1.0.0-build.153'
            release=json.loads(cmd('gh','release','view',tag,'--json','url,assets,isPrerelease'))
            runs=json.loads(cmd('gh','run','list','--branch',tag,'--json','headSha,status,conclusion,url','--limit','5'))
            run=next(r for r in runs if r['headSha']==commit and r['conclusion']=='success')
            asset=next(a for a in release['assets'] if a['name']==f'codex-mobile{suffix}.apk')
            apk=CACHE/f'{channel}.apk'
            cmd('curl','-fLsS','--max-time','150','-o',str(apk),asset['url'])
            digest=hashlib.sha256(apk.read_bytes()).hexdigest()
            badging=cmd(str(SDK/'aapt'),'dump','badging',str(apk))
            package=re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'",badging)
            signing=cmd(str(SDK/'apksigner'),'verify','--print-certs',str(apk))
            cert=re.search(r'Signer #1 certificate SHA-256 digest: (\w+)',signing).group(1)
            previous=json.loads((ROOT/'reports/mobile-release-152/release-verification.json').read_text())['results'][channel]
            with zipfile.ZipFile(apk) as z: binary=z.read('lib/arm64-v8a/libapp.so')
            base='http://batata-default-string.tail0302c4.ts.net'+(':8118' if channel=='dev' else '')
            package_id='io.github.brunojaime.codexmobilebridge.dev' if channel=='dev' else 'com.example.codex_mobile_frontend'
            updater_url='https://batata-default-string.tail0302c4.ts.net'+(':8443' if channel=='dev' else '')+f'/app-updates/codex-mobile{suffix}?platform=android&currentVersion=1.0.0&currentBuild=152&channel={channel}'
            updater=json.loads(cmd('curl','-fsS','--max-time','90','--socks5-hostname','127.0.0.1:1055',updater_url))
            checks=[package.group(1)==package_id,package.group(2)=='153',cert==previous['certificate_sha256'],release['isPrerelease']==(channel=='dev'),base.encode() in binary,b'bridge-document.invalid' in binary,updater.get('latestBuild')==153,updater.get('releaseTag')==tag,updater.get('sha256')==digest,updater.get('packageId')==package_id,updater.get('available') is True]
            results[channel]={'url':release['url'],'apk_url':asset['url'],'sha256':digest,'bytes':apk.stat().st_size,'package':package.group(1),'version':package.group(3),'build':int(package.group(2)),'certificate_sha256':cert,'same_signer_as_152':cert==previous['certificate_sha256'],'run':run,'passed':all(checks),'updater':{k:updater.get(k) for k in ['latestBuild','releaseTag','available','sha256','packageId']}}
        source_paths=['lib/src/models/session_file.dart','lib/src/screens/session_file_screen.dart','lib/src/services/html_document.dart','lib/src/widgets/html_file_preview.dart']
        source_matches=all((WORK/'frontend/mobile_app'/p).read_text()==cmd('git','show',commit+':frontend/mobile_app/'+p) for p in source_paths)
        observations['safe-regressions']=tested.returncode==0 and summary['complete'] and source_matches
        observations['published-channels']=all(r['passed'] for r in results.values()) and source_matches
        # Only an executed test of the distributed APK may satisfy deployed UI evidence.
        # The separate native widget probe is explicitly local evidence.
        target_after=target()
        payload={'observations':observations,'target_before':target_before,'target_after':target_after}
        (OUT/'release-verification.json').write_text(json.dumps({'results':results,'tests':summary,**payload},indent=2)+'\n')
        print('NIENFOS_OBSERVATIONS_V1 '+json.dumps(payload))
        return 0 if all(observations.values()) and target_before==target_after else 1
    except Exception as error:
        (OUT/'verification-pending.json').write_text(json.dumps({'results':results,'error_type':type(error).__name__},indent=2))
        print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':observations,'target_before':target_before,'target_after':target_after}))
        return 2
if __name__=='__main__': sys.exit(main())
