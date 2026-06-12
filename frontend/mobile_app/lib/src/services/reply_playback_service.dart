import '../models/chat_message.dart';
import '../models/server_capabilities.dart';
import '../models/session_detail.dart';
import 'api_client.dart';
import 'provider_reply_speech_player.dart';
import 'reply_speech_player.dart';
import 'text_to_speech_player.dart';

class ReplyPlaybackService {
  ReplyPlaybackService({
    ReplySpeechPlayer? fallbackPlayer,
    ReplySpeechPlayer Function(ApiClient apiClient)? providerPlayerFactory,
  })  : _fallbackPlayer = fallbackPlayer ?? TextToSpeechPlayer(),
        _providerPlayerFactory = providerPlayerFactory ??
            ((apiClient) => ProviderReplySpeechPlayer(apiClient: apiClient));

  final ReplySpeechPlayer _fallbackPlayer;
  final ReplySpeechPlayer Function(ApiClient apiClient) _providerPlayerFactory;
  final Map<String, String> _spokenAssistantMessageIds = <String, String>{};
  final Map<String, String> _speakingAssistantMessageIds = <String, String>{};
  ReplySpeechPlayer? _providerPlayer;
  bool _supportsProviderSpeech = false;
  double _playbackSpeed = 1.0;

  Future<void> setServer(ApiClient apiClient) async {
    await stop();
    final existingProviderPlayer = _providerPlayer;
    _providerPlayer = _providerPlayerFactory(apiClient);
    await _providerPlayer?.setPlaybackSpeed(_playbackSpeed);
    _supportsProviderSpeech = false;
    // Session and message ids are scoped to a server; avoid carrying
    // duplicate-suppression state across server switches.
    _spokenAssistantMessageIds.clear();
    _speakingAssistantMessageIds.clear();
    await existingProviderPlayer?.dispose();
  }

  Future<void> setPlaybackSpeed(double speed) async {
    _playbackSpeed = speed.clamp(1.0, 2.0).toDouble();
    await _providerPlayer?.setPlaybackSpeed(_playbackSpeed);
    await _fallbackPlayer.setPlaybackSpeed(_playbackSpeed);
  }

  void setCapabilities(ServerCapabilities? capabilities) {
    _supportsProviderSpeech = capabilities?.supportsSpeechOutput ?? false;
  }

  void seedSession(SessionDetail session) {
    final latestReply = _latestCompletedAssistantReply(session);
    if (latestReply == null) {
      return;
    }
    _spokenAssistantMessageIds[session.id] = latestReply.id;
  }

  Future<void> maybeSpeakLatestAssistantReply({
    required bool enabled,
    required SessionDetail? session,
  }) async {
    if (!enabled || session == null) {
      return;
    }

    final latestReply = _latestCompletedAssistantReply(session);
    if (latestReply == null) {
      return;
    }
    if (_spokenAssistantMessageIds[session.id] == latestReply.id) {
      return;
    }
    if (_speakingAssistantMessageIds[session.id] == latestReply.id) {
      return;
    }

    _speakingAssistantMessageIds[session.id] = latestReply.id;
    try {
      final didSpeak = await _speakWithBestAvailablePlayer(latestReply.text);
      if (didSpeak &&
          _speakingAssistantMessageIds[session.id] == latestReply.id) {
        _spokenAssistantMessageIds[session.id] = latestReply.id;
      }
    } finally {
      if (_speakingAssistantMessageIds[session.id] == latestReply.id) {
        _speakingAssistantMessageIds.remove(session.id);
      }
    }
  }

  Future<void> handleBeginRecording() {
    return stop();
  }

  Future<void> stop() async {
    await _providerPlayer?.stop();
    await _fallbackPlayer.stop();
  }

  Future<void> dispose() async {
    await _providerPlayer?.dispose();
    await _fallbackPlayer.dispose();
  }

  Future<bool> _speakWithBestAvailablePlayer(String text) async {
    if (_supportsProviderSpeech) {
      final didSpeakWithProvider =
          await (_providerPlayer?.speak(text) ?? Future<bool>.value(false));
      if (didSpeakWithProvider) {
        return true;
      }
    }
    return _fallbackPlayer.speak(text);
  }

  ChatMessage? _latestCompletedAssistantReply(SessionDetail session) {
    for (final message in session.messages.reversed) {
      if (!message.isUser &&
          message.status == ChatMessageStatus.completed &&
          message.text.trim().isNotEmpty) {
        return message;
      }
    }
    return null;
  }
}
