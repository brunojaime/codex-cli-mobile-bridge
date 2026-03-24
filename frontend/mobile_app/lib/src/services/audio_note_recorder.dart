import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

import 'android_audio_focus_controller.dart';
import 'recording_target_stub.dart'
    if (dart.library.io) 'recording_target_io.dart';

class AudioNoteRecorder {
  AudioNoteRecorder({AudioRecorder? recorder})
      : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;
  RecordingTarget? _activeTarget;

  Future<void> start() async {
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      throw Exception('Microphone permission is required to record audio.');
    }

    final fileName = kIsWeb ? 'voice-note.wav' : 'voice-note.m4a';
    final target = await createRecordingTarget(fileName);
    _activeTarget = target;
    await AndroidAudioFocusController.requestTransientRecordingFocus();

    try {
      await _recorder.start(
        RecordConfig(
          encoder: kIsWeb ? AudioEncoder.wav : AudioEncoder.aacLc,
          bitRate: kIsWeb ? 1411200 : 128000,
          sampleRate: 44100,
          audioInterruption: defaultTargetPlatform == TargetPlatform.android
              ? AudioInterruptionMode.none
              : AudioInterruptionMode.pause,
        ),
        path: target.path,
      );
    } catch (_) {
      await AndroidAudioFocusController.releaseRecordingFocus();
      rethrow;
    }
  }

  Future<XFile?> stop() async {
    final target = _activeTarget;
    _activeTarget = null;
    final path = await _recorder.stop();
    await AndroidAudioFocusController.releaseRecordingFocus();
    if (path == null) {
      return null;
    }

    return XFile(
      path,
      name: target?.fileName ?? (kIsWeb ? 'voice-note.wav' : 'voice-note.m4a'),
    );
  }

  Future<void> cancel() async {
    final target = _activeTarget;
    _activeTarget = null;
    await _recorder.cancel();
    await AndroidAudioFocusController.releaseRecordingFocus();
    if (target != null && !kIsWeb) {
      await cleanupRecordingTarget(target.path);
    }
  }

  Future<void> cleanup(XFile file) async {
    if (kIsWeb) {
      return;
    }

    await cleanupRecordingTarget(file.path);
  }

  Future<void> dispose() {
    return Future.wait<void>([
      AndroidAudioFocusController.releaseRecordingFocus(),
      _recorder.dispose(),
    ]);
  }
}
