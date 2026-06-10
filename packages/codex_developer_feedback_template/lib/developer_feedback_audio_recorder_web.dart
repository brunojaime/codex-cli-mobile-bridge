import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'developer_feedback_audio_recorder_contract.dart';

DeveloperFeedbackAudioRecorder createDeveloperFeedbackAudioRecorder() =>
    WebDeveloperFeedbackAudioRecorder();

class WebDeveloperFeedbackAudioRecorder
    implements DeveloperFeedbackAudioRecorder {
  static const _mimeCandidates = <String>[
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];

  web.MediaRecorder? _recorder;
  web.MediaStream? _stream;
  final List<web.Blob> _chunks = <web.Blob>[];
  Completer<DeveloperFeedbackAudioClip?>? _stopCompleter;
  Stopwatch? _stopwatch;
  String? _mimeType;

  @override
  bool get isRecording => _recorder?.state == 'recording';

  @override
  Future<bool> get isSupported async => _preferredMimeType() != null;

  @override
  Future<void> start() async {
    if (isRecording) return;
    final mimeType = _preferredMimeType();
    if (mimeType == null) {
      throw UnsupportedError(
        'Audio recording is not supported in this browser.',
      );
    }

    try {
      final constraints = web.MediaStreamConstraints(audio: true.toJS);
      _stream = await web.window.navigator.mediaDevices
          .getUserMedia(constraints)
          .toDart;
      final recorder = web.MediaRecorder(
        _stream!,
        web.MediaRecorderOptions(mimeType: mimeType),
      );
      _chunks.clear();
      _stopCompleter = null;
      _mimeType = mimeType;
      _stopwatch = Stopwatch()..start();
      recorder.ondataavailable = ((web.BlobEvent event) {
        final data = event.data;
        if (data.size > 0) _chunks.add(data);
      }).toJS;
      recorder.onerror = ((web.Event _) {
        _finishRecordingWith(null);
      }).toJS;
      recorder.onstop = ((web.Event _) {
        unawaited(_handleStop(mimeType));
      }).toJS;
      _recorder = recorder;
      recorder.start(1000);
    } catch (_) {
      _finishRecordingWith(null);
      _stopTracks();
      throw UnsupportedError('Audio recording is not available.');
    }
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() {
    final existingStop = _stopCompleter;
    if (existingStop != null && !existingStop.isCompleted) {
      return existingStop.future;
    }
    final recorder = _recorder;
    if (recorder == null || recorder.state == 'inactive') {
      _stopTracks();
      return Future<DeveloperFeedbackAudioClip?>.value(null);
    }
    final completer = Completer<DeveloperFeedbackAudioClip?>();
    _stopCompleter = completer;
    recorder.stop();
    return completer.future.timeout(
      const Duration(seconds: 5),
      onTimeout: () {
        _stopTracks();
        return null;
      },
    );
  }

  @override
  Future<void> cancel() async {
    final recorder = _recorder;
    if (recorder != null && recorder.state != 'inactive') {
      recorder.stop();
    }
    _finishRecordingWith(null);
  }

  String? _preferredMimeType() {
    for (final mimeType in _mimeCandidates) {
      if (web.MediaRecorder.isTypeSupported(mimeType)) {
        return mimeType;
      }
    }
    return null;
  }

  Future<void> _handleStop(String fallbackMimeType) async {
    if (_chunks.isEmpty) {
      _finishRecordingWith(null);
      return;
    }
    final blobParts = _chunks.cast<web.BlobPart>().toList().toJS;
    final blob = web.Blob(
      blobParts,
      web.BlobPropertyBag(type: _mimeType ?? fallbackMimeType),
    );
    final buffer = await blob.arrayBuffer().toDart;
    _finishRecordingWith(
      DeveloperFeedbackAudioClip(
        bytes: Uint8List.view(buffer.toDart),
        mimeType: blob.type.isEmpty ? fallbackMimeType : blob.type,
        durationMs: _stopwatch?.elapsedMilliseconds ?? 0,
      ),
    );
  }

  void _finishRecordingWith(DeveloperFeedbackAudioClip? clip) {
    final completer = _stopCompleter;
    _stopTracks();
    _chunks.clear();
    _stopwatch = null;
    _mimeType = null;
    if (completer != null && !completer.isCompleted) {
      completer.complete(clip);
    }
  }

  void _stopTracks() {
    final stream = _stream;
    if (stream != null) {
      for (final track in stream.getTracks().toDart) {
        track.stop();
      }
    }
    _stream = null;
    _recorder = null;
  }
}
