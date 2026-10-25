"""Verify the calmer export, including real rerender, audio timing and every motion interval."""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile
import av,numpy as np
from PIL import Image
from scipy.signal import correlate
import imageio_ffmpeg
import voice
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[1]
OUT=WORK/'reports/rd-video-local-v3-20260929';V2=WORK/'reports/rd-video-local-v2-20260929';V1=WORK/'reports/rd-video-local-20260929'
FF=imageio_ffmpeg.get_ffmpeg_exe();facts={};metrics={}
def fact(name,value):
    facts[name]=bool(value);assert value,name

def pcm(path):
    r=subprocess.run([FF,'-v','error','-i',str(path),'-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype='<f4')

def main():
    p=argparse.ArgumentParser();p.add_argument('--replay',action='store_true');args=p.parse_args()
    meta=json.loads((OUT/'render.json').read_text());old=json.loads((V2/'render.json').read_text());narration=json.loads((OUT/'audio/narration.json').read_text())
    capture=json.loads((OUT/'capture/capture.json').read_text());first=json.loads((V1/'capture/capture.json').read_text())
    same=all(voice.sha(OUT/'audio'/e['deliverable'])==voice.sha(V2/'audio'/e['deliverable'])==e['metadata']['wav_sha256'] for e in narration['entries'])
    fact('voice-default',same and meta['voice']==voice.profile()[0]=='voz-1' and voice.profile(True)[0]=='peter-fast')
    if args.replay:
        with tempfile.TemporaryDirectory(prefix='rd-calm-check-') as name:
            result=subprocess.run([sys.executable,str(ROOT/'run_calm.py'),'--source',str(V2),'--output',name],capture_output=True,text=True,timeout=180)
            assert result.returncode==0,result.stderr[-2500:]
            run=json.loads((Path(name)/'run.json').read_text());assert run['completed'] and run['reuse_audio'] and run['tts_calls']==0
            assert all(voice.sha(Path(name)/'audio'/e['deliverable'])==e['metadata']['wav_sha256'] for e in narration['entries'])
            with av.open(str(Path(name)/'rd-documentos.mp4')) as movie:assert 40<float(movie.duration/av.time_base)<=45
            metrics['repeat_seconds']=run['seconds']
    fact('reuse-audio',same and json.loads((OUT/'run.json').read_text())['reuse_audio'])
    fact('local-render',capture['environment']=='local' and narration['network_policy']=='denied' and capture['blocked_external_requests']==0
         and json.loads((OUT/'run.json').read_text())['model_api_integration']=='none')
    path=OUT/'rd-documentos.mp4'
    with av.open(str(path)) as c:
        v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base);fps=float(v.average_rate)
        fact('rd-demo-video',v.width==720 and v.height==1280 and v.codec_context.name=='h264' and a.codec_context.name=='aac'
             and abs(duration-float(a.duration*a.time_base))<.1 and capture['saved_renewals']==capture['saved_files']==capture['saved_notices']==1
             and capture['mail_provider']=='simulation' and capture['notice_status']=='blocked')
    ratios=[]
    for new,prev in zip(meta['timeline'],old['timeline']):
        assert new['id']==prev['id'] and new['source_anchors']==prev['source_anchors']
        ratios+=list(np.diff(new['target_anchors'])/np.diff(prev['target_anchors']))
    fact('calm-pace',40<=duration<=45 and min(ratios)>=1.3 and all(n['duration']>p['duration'] for n,p in zip(meta['timeline'],old['timeline'])))
    metrics.update(duration=duration,minimum_motion_duration_multiplier=float(min(ratios)),maximum_motion_duration_multiplier=float(max(ratios)))
    r=subprocess.run([FF,'-v','error','-i',str(path),'-vf','crop=584:978:68:99,scale=146:245','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
    frames=np.frombuffer(r.stdout,dtype=np.uint8).reshape(-1,245,146,3).astype(np.float32)
    assert all(np.var(im)>100 for im in frames[::30]),'Blank viewport'
    changes=int((np.abs(np.diff(frames,axis=0)).mean(axis=(1,2,3))>.5).sum())
    new_density=sum(s['frames'] for s in capture['scenes'])/sum(s['duration'] for s in capture['scenes'])
    first_density=sum(s['frames'] for s in first['scenes'])/sum(s['duration'] for s in first['scenes'])
    fact('fluid-motion',changes>25 and new_density>first_density and abs(fps-30)<.01)
    matches=[]
    for cue in meta['cues']:
        expected=np.asarray(Image.open(OUT/'capture'/cue['scene']/cue['source_frame']).resize((584,978),Image.Resampling.LANCZOS).resize((146,245)),dtype=np.float32)
        indices=range(max(0,int((cue['video_seconds']-.35)*fps)),min(len(frames),int((cue['video_seconds']+.35)*fps)+1))
        error,index=min((float(np.mean(np.abs(frames[i]-expected))),i) for i in indices)
        assert error<18,(cue['id'],error)
        matches.append({'id':cue['id'],'expected':cue['video_seconds'],'matched':index/fps,'error_seconds':abs(index/fps-cue['video_seconds'])})
    full=pcm(path);offsets=[];source_audio={e['id']:pcm(OUT/'audio'/e['deliverable']) for e in narration['entries']}
    for piece in meta['audio_segments']:
        expected=piece['start_sample']/meta['audio_sample_rate'];begin=round(piece['source_start_seconds']*8000);end=round(piece['source_end_seconds']*8000)
        reference=source_audio[piece['id']][begin:end];low=max(0,round((expected-.1)*8000));high=round((expected+.1)*8000)+len(reference)
        offset=(low+int(np.argmax(correlate(full[low:high],reference,mode='valid',method='fft'))))/8000
        assert abs(piece['sample_count']/meta['audio_sample_rate']-(piece['source_end_seconds']-piece['source_start_seconds']))<.00005
        offsets.append(abs(offset-expected))
    fact('speech-action-sync',len(matches)==9 and max(m['error_seconds'] for m in matches)<=.35 and max(offsets)<.05)
    silence=[]
    with av.open(str(OUT/'aligned-narration.wav')) as c:
        track=np.concatenate([f.to_ndarray().flatten() for f in c.decode(audio=0)])
    for a,b in zip(meta['audio_segments'],meta['audio_segments'][1:]):
        if a['id']==b['id']:
            start=a['start_sample']+a['sample_count'];end=b['start_sample'];assert np.max(np.abs(track[start:end]))==0
            silence.append((end-start)/meta['audio_sample_rate'])
    fact('natural-pauses',same and len(silence)==5 and min(silence)>=1.0 and len(meta['audio_segments'])==9
         and len((OUT/'subtitulos.srt').read_text().split('-->'))==10 and max(offsets)<.05)
    fact('v2-delivery',(V1/'rd-documentos.mp4').exists() and (V2/'rd-documentos.mp4').exists() and same)
    fact('evidence-costs',meta['render_seconds']>0 and (OUT/'README.md').exists() and 'Codex' in (OUT/'README.md').read_text())
    metrics.update(action_matches=matches,maximum_audio_error_seconds=max(offsets),inserted_pauses=silence,changed_video_frames=changes)
    print(json.dumps(metrics,ensure_ascii=False))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
