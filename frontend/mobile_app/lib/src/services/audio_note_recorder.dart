import 'dart:io';

import 'package:record/record.dart';


class AudioNoteRecorder {
  AudioNoteRecorder({AudioRecorder? recorder}) : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;

  Future<String> start() async {
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      throw Exception('Microphone permission is required to record audio.');
    }

    final directory = await Directory.systemTemp.createTemp('codex-voice-note-');
    final path = '${directory.path}${Platform.pathSeparator}voice-note.m4a';
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        bitRate: 128000,
        sampleRate: 44100,
      ),
      path: path,
    );
    return path;
  }

  Future<String?> stop() {
    return _recorder.stop();
  }

  Future<void> dispose() {
    return _recorder.dispose();
  }
}
