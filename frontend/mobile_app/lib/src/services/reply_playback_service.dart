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
  ReplySpeechPlayer? _providerPlayer;
  bool _supportsProviderSpeech = false;

  Future<void> setServer(ApiClient apiClient) async {
    await stop();
    final existingProviderPlayer = _providerPlayer;
    _providerPlayer = _providerPlayerFactory(apiClient);
    _supportsProviderSpeech = false;
    await existingProviderPlayer?.dispose();
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

    final didSpeak = await _speakWithBestAvailablePlayer(latestReply.text);
    if (didSpeak) {
      _spokenAssistantMessageIds[session.id] = latestReply.id;
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
