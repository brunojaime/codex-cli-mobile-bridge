import re,subprocess,sys,time,xml.etree.ElementTree as E
D='emulator-5582'
def adb(*a):return subprocess.check_output(['adb','-s',D,*a],timeout=30)
def tree():
 adb('shell','uiautomator','dump','/sdcard/html-ui.xml')
 return E.fromstring(adb('shell','cat','/sdcard/html-ui.xml'))
def find(label):
 for i in range(8):
  for n in tree().iter('node'):
   if label in (n.get('text','') or n.get('content-desc','')):return n
  time.sleep(1)
 raise RuntimeError('Not found: '+label)
def tap(label):
 n=find(label); a=list(map(int,re.findall(r'\d+',n.get('bounds'))));adb('shell','input','tap',str((a[0]+a[2])//2),str((a[1]+a[3])//2));time.sleep(1)
if __name__=='__main__':
 if len(sys.argv)>1:tap(sys.argv[1])
 for n in tree().iter('node'):
  t=n.get('text') or n.get('content-desc')
  if t:print(t[:110],n.get('bounds'))
