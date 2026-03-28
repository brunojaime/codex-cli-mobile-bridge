import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/server_capabilities.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/reply_playback_service.dart';
import 'package:codex_mobile_frontend/src/services/reply_speech_player.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('uses provider-backed playback when speech output is available',
      () async {
    final fallbackPlayer = _FakeReplySpeechPlayer();
    final providerPlayer = _FakeReplySpeechPlayer();
    final service = ReplyPlaybackService(
      fallbackPlayer: fallbackPlayer,
      providerPlayerFactory: (_) => providerPlayer,
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    service.setCapabilities(const ServerCapabilities(
      supportsAudioInput: true,
      supportsSpeechOutput: true,
      supportsImageInput: true,
      supportsDocumentInput: true,
      supportsAttachmentBatch: true,
      supportsJobCancellation: true,
      supportsJobRetry: true,
      supportsPushJobStream: true,
      speechOutputBackend: 'openai',
      speechOutputVoice: 'cedar',
      speechOutputResponseFormat: 'wav',
      audioMaxUploadBytes: 1,
      imageMaxUploadBytes: 1,
      documentMaxUploadBytes: 1,
      documentTextCharLimit: 1,
    ));

    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: _buildSession(
        messages: <ChatMessage>[
          _assistantMessage(id: 'assistant-1', text: 'Natural audio reply'),
        ],
      ),
    );

    expect(providerPlayer.spokenTexts, <String>['Natural audio reply']);
    expect(fallbackPlayer.spokenTexts, isEmpty);
  });

  test('falls back to local playback when provider-backed playback fails',
      () async {
    final fallbackPlayer = _FakeReplySpeechPlayer();
    final providerPlayer = _FakeReplySpeechPlayer(speakResult: false);
    final service = ReplyPlaybackService(
      fallbackPlayer: fallbackPlayer,
      providerPlayerFactory: (_) => providerPlayer,
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    service.setCapabilities(const ServerCapabilities(
      supportsAudioInput: true,
      supportsSpeechOutput: true,
      supportsImageInput: true,
      supportsDocumentInput: true,
      supportsAttachmentBatch: true,
      supportsJobCancellation: true,
      supportsJobRetry: true,
      supportsPushJobStream: true,
      speechOutputBackend: 'openai',
      speechOutputVoice: 'cedar',
      speechOutputResponseFormat: 'wav',
      audioMaxUploadBytes: 1,
      imageMaxUploadBytes: 1,
      documentMaxUploadBytes: 1,
      documentTextCharLimit: 1,
    ));

    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: _buildSession(
        messages: <ChatMessage>[
          _assistantMessage(id: 'assistant-1', text: 'Fallback path'),
        ],
      ),
    );

    expect(providerPlayer.spokenTexts, <String>['Fallback path']);
    expect(fallbackPlayer.spokenTexts, <String>['Fallback path']);
  });

  test('seeding a session suppresses replaying the latest existing reply',
      () async {
    final providerPlayer = _FakeReplySpeechPlayer();
    final service = ReplyPlaybackService(
      fallbackPlayer: _FakeReplySpeechPlayer(),
      providerPlayerFactory: (_) => providerPlayer,
    );
    final session = _buildSession(
      messages: <ChatMessage>[
        _assistantMessage(id: 'assistant-1', text: 'Existing reply'),
      ],
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    service.setCapabilities(const ServerCapabilities(
      supportsAudioInput: true,
      supportsSpeechOutput: true,
      supportsImageInput: true,
      supportsDocumentInput: true,
      supportsAttachmentBatch: true,
      supportsJobCancellation: true,
      supportsJobRetry: true,
      supportsPushJobStream: true,
      speechOutputBackend: 'openai',
      speechOutputVoice: 'cedar',
      speechOutputResponseFormat: 'wav',
      audioMaxUploadBytes: 1,
      imageMaxUploadBytes: 1,
      documentMaxUploadBytes: 1,
      documentTextCharLimit: 1,
    ));
    service.seedSession(session);

    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: session,
    );

    expect(providerPlayer.spokenTexts, isEmpty);
  });

  test('does not replay the same assistant reply twice', () async {
    final providerPlayer = _FakeReplySpeechPlayer();
    final service = ReplyPlaybackService(
      fallbackPlayer: _FakeReplySpeechPlayer(),
      providerPlayerFactory: (_) => providerPlayer,
    );
    final session = _buildSession(
      messages: <ChatMessage>[
        _assistantMessage(id: 'assistant-1', text: 'Only once'),
      ],
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    service.setCapabilities(_speechEnabledCapabilities());

    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: session,
    );
    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: session,
    );

    expect(providerPlayer.spokenTexts, <String>['Only once']);
  });

  test('stops provider and fallback playback when recording begins', () async {
    final fallbackPlayer = _FakeReplySpeechPlayer();
    final providerPlayer = _FakeReplySpeechPlayer();
    final service = ReplyPlaybackService(
      fallbackPlayer: fallbackPlayer,
      providerPlayerFactory: (_) => providerPlayer,
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    final providerStopsBeforeRecording = providerPlayer.stopCount;
    final fallbackStopsBeforeRecording = fallbackPlayer.stopCount;

    await service.handleBeginRecording();

    expect(providerPlayer.stopCount, providerStopsBeforeRecording + 1);
    expect(fallbackPlayer.stopCount, fallbackStopsBeforeRecording + 1);
  });

  test('clears spoken reply history when switching servers', () async {
    final providerPlayerA = _FakeReplySpeechPlayer();
    final providerPlayerB = _FakeReplySpeechPlayer();
    var factoryCalls = 0;
    final service = ReplyPlaybackService(
      fallbackPlayer: _FakeReplySpeechPlayer(),
      providerPlayerFactory: (_) {
        factoryCalls += 1;
        return factoryCalls == 1 ? providerPlayerA : providerPlayerB;
      },
    );
    final session = _buildSession(
      messages: <ChatMessage>[
        _assistantMessage(id: 'assistant-1', text: 'Server-specific reply'),
      ],
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:8000'));
    service.setCapabilities(_speechEnabledCapabilities());
    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: session,
    );

    await service.setServer(ApiClient(baseUrl: 'http://localhost:9000'));
    service.setCapabilities(_speechEnabledCapabilities());
    await service.maybeSpeakLatestAssistantReply(
      enabled: true,
      session: session,
    );

    expect(providerPlayerA.spokenTexts, <String>['Server-specific reply']);
    expect(providerPlayerB.spokenTexts, <String>['Server-specific reply']);
  });
}

ServerCapabilities _speechEnabledCapabilities() {
  return const ServerCapabilities(
    supportsAudioInput: true,
    supportsSpeechOutput: true,
    supportsImageInput: true,
    supportsDocumentInput: true,
    supportsAttachmentBatch: true,
    supportsJobCancellation: true,
    supportsJobRetry: true,
    supportsPushJobStream: true,
    speechOutputBackend: 'openai',
    speechOutputVoice: 'cedar',
    speechOutputResponseFormat: 'wav',
    audioMaxUploadBytes: 1,
    imageMaxUploadBytes: 1,
    documentMaxUploadBytes: 1,
    documentTextCharLimit: 1,
  );
}

class _FakeReplySpeechPlayer implements ReplySpeechPlayer {
  _FakeReplySpeechPlayer({this.speakResult = true});

  final bool speakResult;
  final List<String> spokenTexts = <String>[];
  int stopCount = 0;
  int disposeCount = 0;

  @override
  Future<void> dispose() async {
    disposeCount += 1;
  }

  @override
  Future<bool> speak(String rawText) async {
    spokenTexts.add(rawText);
    return speakResult;
  }

  @override
  Future<void> stop() async {
    stopCount += 1;
  }
}

SessionDetail _buildSession({required List<ChatMessage> messages}) {
  const timestamp = '2026-01-01T00:00:00.000Z';
  return SessionDetail(
    id: 'session-a',
    title: 'Chat A',
    workspacePath: '/workspace/a',
    workspaceName: 'Workspace A',
    createdAt: DateTime.parse(timestamp),
    updatedAt: DateTime.parse(timestamp),
    messages: messages,
  );
}

ChatMessage _assistantMessage({
  required String id,
  required String text,
}) {
  const timestamp = '2026-01-01T00:00:00.000Z';
  return ChatMessage(
    id: id,
    text: text,
    isUser: false,
    authorType: ChatMessageAuthorType.assistant,
    status: ChatMessageStatus.completed,
    createdAt: DateTime.parse(timestamp),
    updatedAt: DateTime.parse(timestamp),
    jobStatus: 'completed',
    jobPhase: 'Completed',
  );
}
