import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'api_client.dart';
import 'reply_audio_file_cache_stub.dart'
    if (dart.library.io) 'reply_audio_file_cache_io.dart';
import 'reply_speech_player.dart';

class ProviderReplySpeechPlayer implements ReplySpeechPlayer {
  ProviderReplySpeechPlayer({
    required ApiClient apiClient,
    AudioPlayer? audioPlayer,
  })  : _apiClient = apiClient,
        _audioPlayer = audioPlayer;

  final ApiClient _apiClient;
  AudioPlayer? _audioPlayer;
  String? _activeAudioPath;

  @override
  Future<bool> speak(String rawText) async {
    if (kIsWeb) {
      return false;
    }

    final text = sanitizeTextForSpeech(rawText);
    if (text.isEmpty) {
      return true;
    }

    try {
      final clip = await _apiClient.synthesizeSpeech(text);
      final audioPath = await cacheReplyAudioFile(
        clip.audioBytes,
        fileExtension: _fileExtensionForFormat(clip.responseFormat),
      );
      final player = _audioPlayer ??= AudioPlayer();
      await player.stop();
      await _deleteActiveAudioPath();
      _activeAudioPath = audioPath;
      await player.play(DeviceFileSource(audioPath));
      return true;
    } on MissingPluginException {
      return false;
    } on UnsupportedError {
      return false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _audioPlayer?.stop();
    } catch (_) {
      return;
    }
  }

  @override
  Future<void> dispose() async {
    await stop();
    try {
      await _audioPlayer?.dispose();
    } catch (_) {
      // Ignore plugin teardown failures during widget disposal.
    }
    await _deleteActiveAudioPath();
  }

  Future<void> _deleteActiveAudioPath() async {
    final activeAudioPath = _activeAudioPath;
    _activeAudioPath = null;
    if (activeAudioPath == null) {
      return;
    }
    await deleteReplyAudioFile(activeAudioPath);
  }
}

String _fileExtensionForFormat(String responseFormat) {
  switch (responseFormat) {
    case 'aac':
      return 'aac';
    case 'flac':
      return 'flac';
    case 'opus':
      return 'opus';
    case 'pcm':
      return 'pcm';
    case 'wav':
      return 'wav';
    case 'mp3':
    default:
      return 'mp3';
  }
}
