#!/usr/bin/env python3
"""Read and verify published Android 150 artifacts and real updater endpoints."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/mobile-tables-release-150'
CACHE = ROOT / '.data/mobile-tables-release-150'
SDK = Path.home() / '.local/share/android-sdk/build-tools/36.0.0'
COMMIT = '62c068cc94eb63b2bc275a9fc6d6ca2a1c37fd77'
RUNS = {'prod': '37863536449', 'dev': '37863540998'}

def cmd(*argv):
    return subprocess.check_output(argv, cwd=ROOT, text=True, timeout=180)

def release(tag):
    return json.loads(cmd('gh','release','view',tag,'--json','tagName,url,isPrerelease,assets'))

def download(url,path):
    cmd('curl','-fLsS','--max-time','150','-o',str(path),url)

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    results={}
    target_before=None
    try:
        first=release('android-v1.0.0-build.150')
        target_before={'environment':'dev','origin':'https://github.com','release_id':first['tagName']+'@'+COMMIT}
        for channel in ['prod','dev']:
            suffix='-dev' if channel=='dev' else ''
            tag=f'android{suffix}-v1.0.0-build.150'
            r=release(tag)
            run=json.loads(cmd('gh','run','view',RUNS[channel],'--json','status,conclusion,headSha,url'))
            asset=next(a for a in r['assets'] if a['name']==f'codex-mobile{suffix}.apk')
            apk=CACHE/f'{channel}.apk'; download(asset['url'],apk)
            digest=hashlib.sha256(apk.read_bytes()).hexdigest()
            badging=cmd(str(SDK/'aapt'),'dump','badging',str(apk))
            package=re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'",badging)
            signing=cmd(str(SDK/'apksigner'),'verify','--print-certs',str(apk))
            cert=re.search(r'Signer #1 certificate SHA-256 digest: (\w+)',signing).group(1)
            old=release(f'android{suffix}-v1.0.0-build.149')
            oldasset=next(a for a in old['assets'] if a['name']==asset['name'])
            oldapk=CACHE/f'{channel}-149.apk'
            if not oldapk.exists(): download(oldasset['url'],oldapk)
            oldsign=cmd(str(SDK/'apksigner'),'verify','--print-certs',str(oldapk))
            oldcert=re.search(r'Signer #1 certificate SHA-256 digest: (\w+)',oldsign).group(1)
            base='http://batata-default-string.tail0302c4.ts.net'+(':8118' if channel=='dev' else '')
            with zipfile.ZipFile(apk) as z:
                binary=z.read('lib/arm64-v8a/libapp.so')
            url='https://batata-default-string.tail0302c4.ts.net'+(':8443' if channel=='dev' else '')+f'/app-updates/codex-mobile{suffix}?platform=android&currentVersion=1.0.0&currentBuild=149&channel={channel}'
            updater=json.loads(cmd('curl','-fsS','--max-time','90','--socks5-hostname','127.0.0.1:1055',url))
            expected_package='io.github.brunojaime.codexmobilebridge.dev' if channel=='dev' else 'com.example.codex_mobile_frontend'
            results[channel]={'release':r['url'],'tag':tag,'apk_url':asset['url'],'bytes':apk.stat().st_size,'sha256':digest,'package':package.group(1),'version':package.group(3),'build':int(package.group(2)),'certificate_sha256':cert,'same_signer_as_149':cert==oldcert,'run':run,'compiled_backend_present':base.encode() in binary,'updater':{k:updater.get(k) for k in ['latestBuild','releaseTag','available','apkUrl','sha256','sizeBytes','packageId','releaseChannel']}}
            checks=[run['conclusion']=='success',run['headSha']==COMMIT,r['isPrerelease']==(channel=='dev'),package.group(1)==expected_package,package.group(2)=='150',cert==oldcert,base.encode() in binary,updater.get('latestBuild')==150,updater.get('releaseTag')==tag,updater.get('available') is True,updater.get('sha256')==digest]
            results[channel]['passed']=all(checks)
        after=release('android-v1.0.0-build.150')
        target_after={'environment':'dev','origin':'https://github.com','release_id':after['tagName']+'@'+json.loads(cmd('gh','run','view',RUNS['prod'],'--json','headSha'))['headSha']}
        source=cmd('git','show',COMMIT+':frontend/mobile_app/lib/src/widgets/rich_message_content.dart')
        tests=(OUT/'flutter-tests.log').read_text()
        observations={'release-source':source==(ROOT/'frontend/mobile_app/lib/src/widgets/rich_message_content.dart').read_text() and 'All tests passed!' in tests,'real-channel-config':all(r['run']['conclusion']=='success' and r['compiled_backend_present'] for r in results.values()),'published-artifacts':all(r['passed'] for r in results.values())}
        payload={'observations':observations,'target_before':target_before,'target_after':target_after}
        (OUT/'release-verification.json').write_text(json.dumps({'results':results,**payload},indent=2)+'\n')
        print('NIENFOS_OBSERVATIONS_V1 '+json.dumps(payload))
        return 0 if all(observations.values()) and target_before==target_after else 1
    except Exception as e:
        (OUT/'release-probe-pending.json').write_text(json.dumps({'results':results,'error_type':type(e).__name__},indent=2)+'\n')
        print('Verification pending:',type(e).__name__)
        return 2

if __name__=='__main__': sys.exit(main())
