#!/usr/bin/env python3
"""Exercise the real Flutter file screen and Android WebView against Bridge DEV.
Exercises the downloaded signed DEV APK in a read-only laboratory chat.
"""
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports/html-preview-153'
DEVICE='emulator-5582'
PACKAGE='io.github.brunojaime.codexmobilebridge.dev'
def adb(*args):
    return subprocess.check_output(['adb','-s',DEVICE,*args],timeout=30)
def screen():
    for attempt in range(3):
        try:
            adb('shell','uiautomator','dump','/sdcard/html-preview.xml')
            break
        except subprocess.CalledProcessError:
            time.sleep(2)
    return ET.fromstring(adb('shell','cat','/sdcard/html-preview.xml'))
def node(text):
    for _ in range(12):
        tree=screen()
        for n in tree.iter('node'):
            if (text in n.get('text','') or text in n.get('content-desc','')) and n.get('bounds') != '[0,0][0,0]': return n
        time.sleep(1)
    raise AssertionError('Visible UI not found: '+text)
def tap(n):
    x1,y1,x2,y2=map(int,re.findall(r'\d+',n.get('bounds')))
    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
def capture(name):
    (OUT/name).write_bytes(adb('exec-out','screencap','-p'))

def main():
    adb('shell','am','force-stop',PACKAGE)
    adb('shell','am','start','-n',PACKAGE+'/com.example.codex_mobile_frontend.MainActivity')
    tap(node('Abrir HTML'))
    time.sleep(4)
    node('Tu HTML')
    adb('shell','input','swipe','500','650','500','1900','500')
    time.sleep(2)
    capture('android-preview.png')
    tap(node('Ver código'))
    node('<!DOCTYPE html>')
    capture('android-source.png')
    tap(node('Vista previa'))
    node('Tu HTML')
    size=adb('shell','wm','size').decode()
    w,h=map(int,re.findall(r'(\d+)x(\d+)',size)[-1])
    adb('shell','input','swipe',str(w//2),str(h*3//4),str(w//2),str(h//3),'450')
    adb('shell','input','swipe','540','1900','540','900','450')
    tap(node('Abrir otro documento'))
    node('Segundo documento')
    capture('android-relative-link.png')
    adb('shell','input','tap','500','1400')
    adb('shell','input','keyevent','4')
    time.sleep(2)
    node('index.html')
    payload={'scope':'published-dev-apk-laboratory','version':153,'apk':'GitHub downloaded DEV signed APK','device':DEVICE,'backend':'Bridge DEV existing file API','observations':{'rendered-document':True,'source-toggle':True,'relative-navigation':True,'back-to-document':True},'screenshots':['android-preview.png','android-source.png','android-relative-link.png']}
    (OUT/'native-probe.json').write_text(json.dumps(payload,indent=2))
    print(json.dumps(payload))
if __name__=='__main__': main()
