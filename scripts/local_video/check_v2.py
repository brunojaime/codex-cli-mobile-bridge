"""Executed media/caching/timing evidence; optionally replay the full local UI workflow."""
from pathlib import Path
import argparse, json, shutil, subprocess, sys, tempfile, time
import av, numpy as np
from PIL import Image, ImageChops, ImageStat
from scipy.signal import correlate
import imageio_ffmpeg
import voice
ROOT=Path(__file__).resolve().parent; WORK=ROOT.parents[1]
OUT=WORK/'reports/rd-video-local-v2-20260929'; OLD=WORK/'reports/rd-video-local-20260929'
FF=imageio_ffmpeg.get_ffmpeg_exe(); facts={}; measurements={}
def fact(name,value):
    facts[name]=bool(value);assert value,name

def pcm(path):
    r=subprocess.run([FF,'-v','error','-i',str(path),'-vn','-ac','1','-ar','8000','-f','f32le','-'],check=True,capture_output=True)
    return np.frombuffer(r.stdout,dtype='<f4')

def validate():
    p=argparse.ArgumentParser();p.add_argument('--replay',action='store_true');args=p.parse_args()
    narration=json.loads((OUT/'audio/narration.json').read_text());old_narration=json.loads((OLD/'audio/narration.json').read_text())
    capture=json.loads((OUT/'capture/capture.json').read_text());oldcap=json.loads((OLD/'capture/capture.json').read_text())
    meta=json.loads((OUT/'render.json').read_text()); recipe=json.loads((ROOT/'rd-documents.json').read_text())
    same=all(voice.sha(OUT/'audio'/e['deliverable'])==voice.sha(OLD/'audio'/e['deliverable']) for e in narration['entries'])
    fact('voice-default',same and narration['profile']==voice.profile()[0]=='voz-1' and voice.profile(True)[0]=='peter-fast')
    with tempfile.TemporaryDirectory(prefix='rd-video-v2-check-') as name:
        tmp=Path(name);started=time.perf_counter()
        before={e['path']:Path(e['path']).stat().st_mtime_ns for e in narration['entries']}
        subprocess.run([sys.executable,str(ROOT/'voice.py'),str(ROOT/'rd-documents.json'),'--output',str(tmp/'audio')],check=True,capture_output=True,timeout=30)
        reused=json.loads((tmp/'audio/narration.json').read_text())
        measurements['cache_reuse_seconds']=time.perf_counter()-started
        corrupt=tmp/'bad';corrupt.mkdir(); entry=reused['entries'][0]
        (corrupt/f'{entry["key"]}.json').write_text(json.dumps(entry['metadata']));(corrupt/f'{entry["key"]}.wav').write_bytes(b'corrupt')
        fact('reuse-audio',all(e['cache_hit'] for e in reused['entries']) and all(Path(k).stat().st_mtime_ns==v for k,v in before.items()) and voice.cached(corrupt,entry['key']) is None)
        if args.replay:
            shutil.copyfile(OUT/'alignment.json',tmp/'alignment.json')
            command=[sys.executable,str(ROOT/'run.py'),'--v2','--output',str(tmp),'--rd-project','/home/batata/Projects/rd-gestion-hse/tmp/document-renewal-dev',
                     '--node','/home/batata/.nvm/versions/node/v22.22.2/bin/node','--port','18889']
            r=subprocess.run(command,capture_output=True,text=True,timeout=240)
            assert r.returncode==0,r.stdout[-1200:]+r.stderr[-4000:]
            replay=json.loads((tmp/'capture/capture.json').read_text())
            assert replay['saved_renewals']==replay['saved_files']==replay['saved_notices']==1
            assert not replay['page_errors'] and replay['notice_status']=='blocked'
            measurements['fresh_workflow_seconds']=json.loads((tmp/'run.json').read_text())['seconds']
            assert all(e['cache_hit'] for e in json.loads((tmp/'audio/narration.json').read_text())['entries'])
    fact('local-render',narration['network_policy']=='denied' and capture['environment']=='local' and capture['blocked_external_requests']==0
         and capture['mail_provider']=='simulation' and 'socket.connect' in (ROOT/'align.py').read_text()
         and all(not any(x in (ROOT/name).read_text().lower() for x in ('api.openai.com','openrouter.ai','codex exec')) for name in ('render_v2.py','record_rd_v2.mjs','align.py')))
    path=OUT/'rd-documentos.mp4'; c=av.open(str(path));v=c.streams.video[0];a=c.streams.audio[0]
    duration=float(v.duration*v.time_base);aduration=float(a.duration*a.time_base)
    fact('rd-demo-video',v.width==720 and v.height==1280 and v.codec_context.name=='h264' and a.codec_context.name=='aac'
         and abs(duration-aduration)<.2 and capture['saved_renewals']==capture['saved_files']==capture['saved_notices']==1
         and capture['notice_status']=='blocked' and not capture['page_errors'])
    fps=float(v.average_rate);c.close()
    def decoded_pixels(path):
        result=subprocess.run([FF,'-v','error','-i',str(path),'-vf','crop=584:978:68:99,scale=146:245',
            '-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True,timeout=45)
        return np.frombuffer(result.stdout,dtype=np.uint8).reshape(-1,245,146,3).astype(np.float32)
    pixels=decoded_pixels(path);decoded=[(i/fps,frame) for i,frame in enumerate(pixels)]
    assert len(decoded)>500 and all(float(np.var(frame))>100 for frame in pixels[::30]),'Blank viewport'
    changes=int((np.abs(np.diff(pixels,axis=0)).mean(axis=(1,2,3))>.5).sum())
    old_pixels=decoded_pixels(OLD/'rd-documentos.mp4')
    old_changes=int((np.abs(np.diff(old_pixels,axis=0)).mean(axis=(1,2,3))>.5).sum())
    with av.open(str(OLD/'rd-documentos.mp4')) as old_video:
        old_video_duration=float(old_video.streams.video[0].duration*old_video.streams.video[0].time_base)
    old_duration=sum(s['duration'] for s in oldcap['scenes']);old_rate=sum(s['frames'] for s in oldcap['scenes'])/old_duration
    new_rate=sum(s['frames'] for s in capture['scenes'])/sum(s['duration'] for s in capture['scenes'])
    measurements.update(old_capture_changes_per_second=old_rate,new_capture_changes_per_second=new_rate,
        export_changed_frames=changes,old_export_changed_frames=old_changes,video_seconds=duration)
    fact('fluid-motion',new_rate>old_rate*2 and changes/duration>old_changes/old_video_duration and abs(fps-30)<.01)
    deviations=[]
    for cue in meta['cues']:
        im=Image.open(OUT/'capture'/cue['scene']/cue['source_frame']).resize((584,978),Image.Resampling.LANCZOS).resize((146,245))
        expected=np.asarray(im,dtype=np.float32)
        window=[(float(np.mean(np.abs(pixels-expected))),t) for t,pixels in decoded if abs(t-cue['video_seconds'])<=.35]
        error,observed=min(window)
        assert error<18,(cue['id'],error)
        deviations.append({'id':cue['id'],'expected':cue['video_seconds'],'matched':observed,'difference':abs(observed-cue['video_seconds']),'image_mae':error})
    full=pcm(path); audio_offsets=[]
    for scene in meta['timeline']:
        reference=pcm(OUT/'audio'/f'{scene["id"]}.wav');expected=scene['start']+meta['speech_lead']
        start=max(0,round((expected-.2)*8000));end=min(len(full),round((expected+.2)*8000)+len(reference))
        correlations=correlate(full[start:end],reference,mode='valid',method='fft'); observed=(start+int(np.argmax(correlations)))/8000
        audio_offsets.append({'id':scene['id'],'expected':expected,'observed':observed,'difference':abs(observed-expected)})
    measurements['visual_action_matches']=deviations;measurements['audio_offsets']=audio_offsets
    print(json.dumps({'timing_diagnostics':{'visual':deviations,'audio':audio_offsets}}),flush=True)
    fact('speech-action-sync',len(deviations)==9 and max(x['difference'] for x in deviations)<=.35 and max(x['difference'] for x in audio_offsets)<.09)
    fact('v2-delivery',same and (OLD/'rd-documentos.mp4').exists() and path.stat().st_size>100000 and len((OUT/'subtitulos.srt').read_text().split('-->'))==9)
    fact('evidence-costs',meta['render_seconds']>0 and json.loads((OUT/'run.json').read_text())['completed'] and (OUT/'alignment.json').exists() and 'Codex' in (ROOT/'README.md').read_text())
    print(json.dumps(measurements,ensure_ascii=False))
try: validate()
finally: print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
