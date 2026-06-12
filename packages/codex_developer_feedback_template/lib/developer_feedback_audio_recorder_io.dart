import 'dart:io';
import 'dart:typed_data';

import 'package:record/record.dart';

import 'developer_feedback_audio_recorder_contract.dart';

DeveloperFeedbackAudioRecorder createDeveloperFeedbackAudioRecorder() =>
    NativeDeveloperFeedbackAudioRecorder();

class NativeDeveloperFeedbackAudioRecorder
    implements DeveloperFeedbackAudioRecorder {
  NativeDeveloperFeedbackAudioRecorder({AudioRecorder? recorder})
    : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;
  String? _path;
  DateTime? _startedAt;
  var _recording = false;

  @override
  bool get isRecording => _recording;

  @override
  Future<bool> get isSupported async {
    try {
      return await _recorder.hasPermission();
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> start() async {
    if (!await _recorder.hasPermission()) {
      throw UnsupportedError('Audio recording permission was not granted.');
    }
    final path =
        '${Directory.systemTemp.path}/codex-feedback-audio-'
        '${DateTime.now().microsecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: path,
    );
    _path = path;
    _startedAt = DateTime.now();
    _recording = true;
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() async {
    final startedAt = _startedAt;
    final fallbackPath = _path;
    final path = await _recorder.stop() ?? fallbackPath;
    _recording = false;
    _startedAt = null;
    _path = null;
    if (path == null) return null;

    final file = File(path);
    if (!await file.exists()) return null;
    final bytes = await file.readAsBytes();
    await file.delete().catchError((_) => file);
    if (bytes.isEmpty) return null;

    final durationMs = startedAt == null
        ? 0
        : DateTime.now().difference(startedAt).inMilliseconds;
    return DeveloperFeedbackAudioClip(
      bytes: Uint8List.fromList(bytes),
      mimeType: 'audio/mp4',
      durationMs: durationMs,
    );
  }

  @override
  Future<void> cancel() async {
    final path = _path;
    if (_recording) {
      await _recorder.stop();
    }
    _recording = false;
    _startedAt = null;
    _path = null;
    if (path != null) {
      await File(path).delete().catchError((_) => File(path));
    }
  }
}
