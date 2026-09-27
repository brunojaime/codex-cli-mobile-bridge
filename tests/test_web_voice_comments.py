"""Validate the web package's actual serialized batch against the existing Bridge."""
import json
from pathlib import Path
import subprocess
import shutil
import pytest

from test_message_flow import build_feedback_queue_client, wait_for_job


def test_web_voice_comments_reach_prompt_with_both_transcripts(tmp_path: Path) -> None:
    script = """
import { createItem, createBatch } from './packages/codex-developer-feedback-web/src/core.js';
const config={sourceApp:'fixture-app',sourceDisplayName:'Voice test',environment:'dev'};
const item=createItem(config,{screenshot:'aW1hZ2U=',comment:'Cambiar el botón',points:[],width:390,height:844,pathname:'/'});
item.id='capture-with-voice';item.voiceNotes=[1,2].map(n=>({id:'note-'+n,audioBase64:'AQI=',audioMimeType:'audio/webm',audioDurationMs:1000*n,audioByteLength:2}));
console.log(JSON.stringify(createBatch(config,[item],'default')));
"""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise the web serializer")
    payload = json.loads(subprocess.check_output([node, "--input-type=module", "-e", script], text=True))
    client = build_feedback_queue_client(tmp_path, audio_transcription_backend="command", audio_transcription_command="python3 tests/fixtures/fake_transcriber.py {filename} {file}")
    response = client.post('/feedback-batches/start-session', json=payload)
    assert response.status_code == 202
    job = wait_for_job(client, response.json()['job_id'])
    assert job['status'] == 'completed'
    message = job['message']
    assert 'Cambiar el botón' in message
    assert 'No desplegar producción' in message
    for n in (1,2):
        assert f'Audio transcript: Transcribed audio from capture-with-voice-note-note-{n}.webm' in message
        assert f'Nota de voz {n}/2' in message
    assert message.index('Nota de voz 1/2') < message.index('Nota de voz 2/2')
    queued = client.get('/feedback-queue').json()
    assert len(queued) == 3
    assert sum(bool(item['audio_transcript']) for item in queued) == 2
