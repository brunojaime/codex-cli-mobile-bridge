import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

class TextToSpeechPlayer {
  final FlutterTts _tts = FlutterTts();
  bool _configured = false;

  Future<void> speak(String rawText) async {
    final text = _sanitize(rawText);
    if (text.isEmpty) {
      return;
    }

    try {
      await _configureIfNeeded();
      await _tts.stop();
      await _tts.speak(text);
    } on MissingPluginException {
      return;
    } catch (_) {
      return;
    }
  }

  Future<void> stop() async {
    try {
      await _tts.stop();
    } on MissingPluginException {
      return;
    } catch (_) {
      return;
    }
  }

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

  String _sanitize(String text) {
    return text
        .replaceAllMapped(
          RegExp(r'\[([^\]]+)\]\([^)]+\)'),
          (match) => match.group(1) ?? '',
        )
        .replaceAll(RegExp(r'```[\s\S]*?```'), ' ')
        .replaceAll('`', '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }
}
