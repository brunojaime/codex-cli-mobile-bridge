"""Drive v3 transport. Refreshable OAuth from Secrets; IDs and ETags persisted.

The ChatGPT connector is used for bootstrap, not borrowed as a daemon credential.
"""
import json
import os
from pathlib import Path
import re
import httpx
from .core import atomic, digest

FOLDER='application/vnd.google-apps.folder'
FIELDS='id,name,mimeType,size,version,md5Checksum,parents,capabilities(canDownload),appProperties'

class DriveConflict(RuntimeError):
    pass

class Drive:
    def __init__(self, root_id, state):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',root_id):
            raise ValueError('invalid_root_id')
        self.root_id=root_id
        self.state=Path(state)
        self.http=httpx.Client(timeout=120,follow_redirects=False)
        self.token=None
        self.allowed={root_id}
        self.receipts=json.loads(self.state.read_text()) if self.state.exists() else {}

    def refresh(self):
        r=self.http.post('https://oauth2.googleapis.com/token',data={
            'client_id':os.environ['RELEVAMIENTOS_GOOGLE_CLIENT_ID'],
            'client_secret':os.environ['RELEVAMIENTOS_GOOGLE_CLIENT_SECRET'],
            'refresh_token':os.environ['RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN'],
            'grant_type':'refresh_token'})
        r.raise_for_status()
        self.token=r.json()['access_token']

    def request(self,method,path,**kwargs):
        if self.token is None:
            self.refresh()
        headers=kwargs.pop('headers',{})
        for attempt in range(2):
            r=self.http.request(method,'https://www.googleapis.com/'+path,headers={**headers,'Authorization':'Bearer '+self.token},**kwargs)
            if r.status_code==401 and attempt==0:
                self.refresh()
                continue
            if r.status_code==412:
                raise DriveConflict('remote_changed')
            r.raise_for_status()
            return r

    def children(self,parent):
        if parent not in self.allowed:
            raise ValueError('outside_scope')
        result=[]
        token=None
        while True:
            p={'q':f"'{parent}' in parents and trashed=false",'fields':f'nextPageToken,files({FIELDS})','pageSize':1000}
            if token:p['pageToken']=token
            data=self.request('GET','drive/v3/files',params=p).json()
            result.extend(data['files'])
            token=data.get('nextPageToken')
            if not token:return result

    def clients(self):
        result=[m for m in self.children(self.root_id) if m['mimeType']==FOLDER and m['name'] not in {'procesadas','consolidado'}]
        self.allowed.update(m['id'] for m in result)
        return result

    def recordings(self,client):
        return [{**m,'downloadable':m.get('capabilities',{}).get('canDownload',False)} for m in self.children(client) if m['mimeType']!=FOLDER]

    def download(self,meta,target):
        # Refresh metadata before and after; never process changed or moved source.
        def current():
            return self.request('GET','drive/v3/files/'+meta['id'],params={'fields':FIELDS}).json()
        before=current()
        if before['version']!=meta['version'] or not set(before['parents']) & self.allowed:
            raise ValueError('source_changed')
        size=int(meta['size'])
        if size>int(os.environ.get('RELEVAMIENTOS_MAX_BYTES',str(4*1024**3))):
            raise ValueError('source_limit')
        if self.token is None:self.refresh()
        temp=Path(str(target)+'.part')
        # Streaming prevents recordings occupying RAM. Interrupted transfers are restarted.
        with self.http.stream('GET','https://www.googleapis.com/drive/v3/files/'+meta['id'],params={'alt':'media'},headers={'Authorization':'Bearer '+self.token}) as response:
            response.raise_for_status()
            count=0
            with temp.open('wb') as out:
                os.chmod(temp,0o600)
                for chunk in response.iter_bytes(1024*1024):
                    count+=len(chunk)
                    if count>size:raise ValueError('source_grew')
                    out.write(chunk)
        after=current()
        if count!=size or after['version']!=before['version'] or after['parents']!=before['parents']:
            raise ValueError('source_changed')
        temp.replace(target)

    def folder(self,parent,name):
        found=[m for m in self.children(parent) if m['name']==name]
        if len(found)>1 or found and found[0]['mimeType']!=FOLDER:
            raise DriveConflict('ambiguous_folder')
        if found:ident=found[0]['id']
        else:ident=self.request('POST','drive/v3/files',json={'name':name,'parents':[parent],'mimeType':FOLDER},params={'fields':'id'}).json()['id']
        self.allowed.add(ident)
        return ident

    def sync(self,client,job,outputs):
        # Resolve only folders below the verified client. Original media never updated.
        if client not in {c['id'] for c in self.clients()}:
            raise ValueError('client_outside_scope')
        folders={():client}
        files=sorted(outputs.rglob('*'),key=lambda p:(p.name=='estado.json',str(p)))
        for path in files:
            if not path.is_file():continue
            relative=path.relative_to(outputs)
            parent=client
            parts=()
            for part in relative.parts[:-1]:
                parts+= (part,)
                if parts not in folders:folders[parts]=self.folder(parent,part)
                parent=folders[parts]
            key=client+'/'+str(relative)
            data=path.read_bytes()
            sha=digest(data)
            candidates=[m for m in self.children(parent) if m['name']==path.name]
            if len(candidates)>1:raise DriveConflict('ambiguous_output')
            receipt=self.receipts.get(key)
            if candidates:
                item=candidates[0]
                response=self.request('GET','drive/v3/files/'+item['id'],params={'alt':'media'})
                remote=digest(response.content)
                if remote==sha:
                    self.receipts[key]={'id':item['id'],'sha256':sha}
                    atomic(self.state,self.receipts)
                    continue
                if not receipt or receipt['id']!=item['id'] or receipt['sha256']!=remote:
                    atomic(outputs.parent/'conflict.json',{'path':str(relative),'remote_id':item['id'],'action':'Preservado remoto. Conciliar manualmente y reintentar; nunca sobrescribir automáticamente.'})
                    raise DriveConflict('manual_edit')
                # Require ETag; fail closed if provider does not supply concurrency control.
                etag=response.headers.get('etag')
                if not etag:raise DriveConflict('etag_missing')
                self.request('PATCH','upload/drive/v3/files/'+item['id'],params={'uploadType':'media'},headers={'If-Match':etag,'Content-Type':'text/plain; charset=utf-8'},content=data)
                ident=item['id']
            else:
                # Atomic multipart creation: no empty output on crash between create/upload.
                boundary='relevamientos-'+sha[:24]
                metadata=json.dumps({'name':path.name,'parents':[parent],'appProperties':{'relevamientos':'1'}}).encode()
                body=b'--'+boundary.encode()+b'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+metadata+b'\r\n--'+boundary.encode()+b'\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n'+data+b'\r\n--'+boundary.encode()+b'--'
                ident=self.request('POST','upload/drive/v3/files',params={'uploadType':'multipart','fields':'id'},headers={'Content-Type':'multipart/related; boundary='+boundary},content=body).json()['id']
            check=self.request('GET','drive/v3/files/'+ident,params={'alt':'media'})
            if digest(check.content)!=sha:raise ValueError('sync_integrity')
            self.receipts[key]={'id':ident,'sha256':sha}
            atomic(self.state,self.receipts)
