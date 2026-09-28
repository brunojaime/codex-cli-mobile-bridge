const toBase64 = blob => new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob); });
const time = ms => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;
export function createVoiceNotes(container, { onBusy = () => {} } = {}) {
  container.innerHTML = `<strong>Notas de voz</strong><p class="muted">Podés comentar hablando, sin escribir. Agregá las notas que necesites. Sin corte por tiempo; depende del espacio disponible.</p><div class="voice-list"></div><div class="actions"><button type="button" class="voice-start">Grabar nota de voz</button><button type="button" class="voice-stop" hidden>Terminar nota</button><button type="button" class="voice-cancel" hidden>Descartar grabación</button></div><p class="voice-status muted" role="status" aria-live="polite"></p>`;
  const find = name => container.querySelector('.voice-' + name);
  let notes = [], urls = [], session = null, pending = false, generation = 0, disposed = false, readonly = false;
  const status = message => { if (!disposed) find('status').textContent = message; };
  const revoke = () => { for (const audio of container.querySelectorAll('audio')) audio.pause(); urls.forEach(url => URL.revokeObjectURL(url)); urls = []; };
  const active = () => pending || !!session;
  const render = () => {
    if (disposed) return;
    revoke(); find('list').replaceChildren(); container.querySelector('p.muted').hidden = readonly;
    notes.forEach((note, index) => {
      const row = document.createElement('div'); row.className = 'voice-note';
      const label = document.createElement('span'); label.textContent = `Nota ${index + 1} · ${time(note.audioDurationMs)}`;
      const audio = document.createElement('audio'); audio.controls = true; audio.preload = 'metadata'; audio.setAttribute('aria-label', `Escuchar nota ${index + 1}`);
      const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(note.audioBase64), c => c.charCodeAt(0))], { type: note.audioMimeType })); urls.push(url); audio.src = url;
      row.append(label, audio);
      if (!readonly) { const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = `Eliminar nota ${index + 1}`; remove.disabled = active(); remove.onclick = () => { if (active()) return; notes.splice(index, 1); render(); }; row.append(remove); }
      find('list').append(row);
    });
    find('start').hidden = readonly || active(); find('stop').hidden = readonly || !session; find('cancel').hidden = readonly || !active(); find('stop').disabled = !!session?.stopping;
  };
  const update = () => { onBusy(active()); render(); };
  const stop = async (discard = false) => {
    if (pending) { generation++; pending = false; update(); status('Grabación cancelada.'); return; }
    const s = session; if (!s) return;
    if (s.stopping) return s.done;
    s.stopping = true; s.discard = discard; s.durationMs = Math.round(performance.now() - s.started);
    clearInterval(s.timer); status(discard ? 'Descartando…' : 'Preparando nota…');
    if (s.recorder.state !== 'inactive') s.recorder.stop();
    s.stream.getTracks().forEach(track => track.stop()); render();
    return s.done;
  };
  const start = async () => {
    if (active() || disposed || readonly) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { status('Este navegador no permite grabar voz. Usá HTTPS y un navegador compatible.'); return; }
    const attempt = ++generation; pending = true; update(); status('Esperando permiso del micrófono…'); let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      if (attempt !== generation || disposed) { stream.getTracks().forEach(track => track.stop()); return; }
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 32000 });
      const s = session = { stream, recorder, chunks: [], started: performance.now(), stopping: false, discard: false };
      pending = false;
      s.done = new Promise(resolve => { recorder.onstop = async () => {
        clearInterval(s.timer); s.stream.getTracks().forEach(track => track.stop());
        try {
          if (!s.discard && !disposed) {
            const blob = new Blob(s.chunks, { type: recorder.mimeType || s.chunks[0]?.type || 'audio/webm' });
            if (!blob.size) throw new Error('No se obtuvo audio. Volvé a grabar la nota.');
            const audioBase64 = await toBase64(blob);
            if (!disposed) { notes.push({ id: `voice-${crypto.randomUUID()}`, createdAt: new Date().toISOString(), audioBase64, audioMimeType: blob.type, audioDurationMs: s.durationMs ?? Math.round(performance.now() - s.started), audioByteLength: blob.size }); status(s.interrupted ? 'La grabación se interrumpió. Revisá la nota guardada.' : 'Nota lista. Podés escucharla o agregar otra. Guardá en la cola para conservarla.'); }
          } else status('Grabación descartada.');
        } catch (error) { status(error.message || 'No se pudo preparar el audio.'); }
        finally { if (session === s) session = null; if (!disposed) update(); resolve(); }
      }; });
      recorder.ondataavailable = event => { if (event.data.size) s.chunks.push(event.data); };
      recorder.onerror = () => { s.interrupted = true; void stop(); };
      stream.getTracks().forEach(track => { track.onended = () => { if (!s.stopping) { s.interrupted = true; void stop(); } }; });
      recorder.start(1000); s.timer = setInterval(() => status(`Grabando · ${time(performance.now() - s.started)}`), 1000); status('Grabando · 0:00'); update();
    } catch (error) {
      stream?.getTracks().forEach(track => track.stop());
      if (attempt !== generation || disposed) return;
      pending = false; session = null; update(); status(error.name === 'NotAllowedError' ? 'Permití el micrófono para grabar una nota de voz.' : 'No se pudo iniciar el micrófono. Volvé a intentar.');
    }
  };
  const hidden = () => { if (document.hidden) void stop(); };
  const unloading = event => { if (active()) { event.preventDefault(); event.returnValue = ''; } };
  document.addEventListener('visibilitychange', hidden); window.addEventListener('beforeunload', unloading);
  find('start').onclick = start; find('stop').onclick = () => void stop(); find('cancel').onclick = () => void stop(true); render();
  return {
    get notes() { return structuredClone(notes); },
    get active() { return active(); }, stop,
    set(value = [], options = {}) { if (active()) throw new Error('Terminá la nota de voz antes de continuar.'); notes = structuredClone(value); readonly = !!options.readOnly; status(''); render(); },
    pause() { container.querySelectorAll('audio').forEach(audio => audio.pause()); },
    dispose() { disposed = true; generation++; void stop(true); revoke(); document.removeEventListener('visibilitychange', hidden); window.removeEventListener('beforeunload', unloading); },
  };
}
