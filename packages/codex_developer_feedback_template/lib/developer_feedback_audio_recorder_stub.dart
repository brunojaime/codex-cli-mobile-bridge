import 'developer_feedback_audio_recorder_contract.dart';

DeveloperFeedbackAudioRecorder createDeveloperFeedbackAudioRecorder() =>
    const UnsupportedDeveloperFeedbackAudioRecorder();

class UnsupportedDeveloperFeedbackAudioRecorder
    implements DeveloperFeedbackAudioRecorder {
  const UnsupportedDeveloperFeedbackAudioRecorder();

  @override
  bool get isRecording => false;

  @override
  Future<bool> get isSupported async => false;

  @override
  Future<void> start() async {
    throw UnsupportedError('Audio recording is not supported here.');
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() async => null;

  @override
  Future<void> cancel() async {}
}
