import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'reply_speech_player.dart' as reply_speech;

String sanitizeTextForSpeech(String text) {
  return reply_speech.sanitizeTextForSpeech(text);
}

class TextToSpeechPlayer implements reply_speech.ReplySpeechPlayer {
  final FlutterTts _tts = FlutterTts();
  bool _configured = false;

  @override
  Future<bool> speak(String rawText) async {
    final text = sanitizeTextForSpeech(rawText);
    if (text.isEmpty) {
      return true;
    }

    try {
      await _configureIfNeeded();
      await _tts.stop();
      await _tts.speak(text);
      return true;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _tts.stop();
    } on MissingPluginException {
      return;
    } catch (_) {
      return;
    }
  }

  @override
  Future<void> dispose() async {
    await stop();
  }

  Future<void> _configureIfNeeded() async {
    if (_configured) {
      return;
    }

    await _tts.setSpeechRate(0.45);
    await _tts.setPitch(1.0);
    await _tts.setVolume(1.0);
    _configured = true;
  }
}
