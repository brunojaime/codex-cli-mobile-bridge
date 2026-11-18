#!/usr/bin/env python3
"""Read-only laboratory chat for exercising the distributed APK.
The single chat message is synthetic. File requests go to the actual DEV API.
No writes, model calls, sessions or messages are created on Bridge.
"""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
import requests
SESSION='d1cae0c2-127b-407f-82fc-ce5b19698890'
BASE='http://127.0.0.1:8118'
STAMP='2026-10-13T22:00:00Z'
CHAT={'id':SESSION,'title':'Prueba HTML 153','workspace_path':'/home/batata/Projects/codex-cli-mobile-bridge','workspace_name':'codex-cli-mobile-bridge','created_at':STAMP,'updated_at':STAMP,'has_pending_messages':False}
MESSAGE={'id':'html-preview-laboratory','role':'assistant','author_type':'assistant','status':'completed','content':'Prueba del APK publicado, con documento de laboratorio.\n\n[Abrir HTML](reports/html-preview-153/fixture/index.html)','created_at':STAMP,'updated_at':STAMP}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=='/sessions': self.reply([CHAT]); return
  if path=='/sessions/'+SESSION: self.reply({**CHAT,'messages':[MESSAGE],'current_run':None,'recent_runs':[]}); return
  if path.startswith('/app-updates/'): self.reply({'available':False}); return
  try:
   r=requests.get(BASE+self.path,timeout=20)
   self.send_response(r.status_code);self.send_header('Content-Type',r.headers.get('Content-Type','application/json'));self.end_headers();self.wfile.write(r.content)
  except Exception:
   self.send_response(502);self.end_headers()
 def reply(self,data):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(data).encode())
 def do_POST(self): self.send_response(405);self.end_headers()
 do_PUT=do_POST
 do_DELETE=do_POST
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',18119),Handler).serve_forever()
