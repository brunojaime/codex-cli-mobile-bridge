import 'dart:typed_data';

class DeveloperFeedbackAudioClip {
  const DeveloperFeedbackAudioClip({
    required this.bytes,
    required this.mimeType,
    required this.durationMs,
  });

  final Uint8List bytes;
  final String mimeType;
  final int durationMs;
}

abstract class DeveloperFeedbackAudioRecorder {
  bool get isRecording;
  Future<bool> get isSupported;
  Future<void> start();
  Future<DeveloperFeedbackAudioClip?> stop();
  Future<void> cancel();
}
