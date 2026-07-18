import 'dart:async';
import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/agent_configuration.dart';
import '../models/agent_profile.dart';
import '../models/agent_profile_blueprint.dart';
import '../models/chat_message.dart';
import '../models/chat_session_summary.dart';
import '../models/codex_tooling.dart';
import '../models/current_run_execution.dart';
import '../models/job_status_response.dart';
import '../models/session_detail.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
import '../services/chat_notification_content.dart';
import '../services/chat_notification_service.dart';

class ChatController extends ChangeNotifier {
  ChatController({
    required ApiClient apiClient,
    ChatNotificationService notificationService =
        const NoopChatNotificationService(),
  })  : _apiClient = apiClient,
        _notificationService = notificationService;

  static const int initialTranscriptMessageLimit = 6;
  static const int olderTranscriptPageLimit = 5;

  final ApiClient _apiClient;
  final ChatNotificationService _notificationService;
  final List<AgentProfile> _agentProfiles = <AgentProfile>[];
  final List<ChatSessionSummary> _sessions = <ChatSessionSummary>[];
  final List<Workspace> _workspaces = <Workspace>[];
  final Map<String, String> _pendingJobs = <String, String>{};
  final Map<String, int> _pollFailures = <String, int>{};
  final Map<String, JobStatusResponse> _jobSnapshots =
      <String, JobStatusResponse>{};
  final Map<String, _DeferredRunNotification> _deferredRunNotifications =
      <String, _DeferredRunNotification>{};
  final Map<String, WebSocketChannel> _jobChannels =
      <String, WebSocketChannel>{};
  final Map<int, _OutgoingUploadTicket> _outgoingUploads =
      <int, _OutgoingUploadTicket>{};
  final Map<int, _OptimisticAudioMessage> _optimisticAudioMessages =
      <int, _OptimisticAudioMessage>{};
  final Set<String> _handledTerminalJobs = <String>{};
  final Set<String> _autoImportedAgentProfileIds = <String>{};

  SessionDetail? _currentSession;
  String? _selectedSessionId;
  String? _errorText;
  String? _olderMessagesError;
  bool _isLoading = false;
  bool _isLoadingOlderMessages = false;
  int _sendingAudioCount = 0;
  int _sendingDocumentCount = 0;
  int _sendingImageCount = 0;
  int _nextOutgoingUploadToken = 0;
  bool _pollInFlight = false;
  Timer? _pollTimer;

  List<ChatSessionSummary> get sessions =>
      List<ChatSessionSummary>.unmodifiable(_sessions);
  List<AgentProfile> get agentProfiles =>
      List<AgentProfile>.unmodifiable(_agentProfiles);
  List<Workspace> get workspaces => List<Workspace>.unmodifiable(_workspaces);
  SessionDetail? get currentSession => _currentSession;
  String? get selectedSessionId => _selectedSessionId;
  String? get errorText => _errorText;
  String? get olderMessagesError => _olderMessagesError;
  bool get isLoading => _isLoading;
  bool get isLoadingOlderMessages => _isLoadingOlderMessages;
  bool get hasOlderMessages =>
      _currentSession?.transcriptWindow.hasOlder ?? false;
  bool get isSendingAudio => _sendingAudioCount > 0;
  bool get isSendingDocument => _sendingDocumentCount > 0;
  bool get isSendingImage => _sendingImageCount > 0;
  bool get hasSessions => _sessions.isNotEmpty;
  List<ChatMessage> get messages {
    final currentSession = _currentSession;
    if (currentSession == null) {
      return const <ChatMessage>[];
    }

    final optimisticMessages = _optimisticAudioMessages.values
        .where((message) => message.sessionId == currentSession.id)
        .map((message) => message.message)
        .toList(growable: false);
    if (optimisticMessages.isEmpty) {
      return currentSession.messages;
    }

    return List<ChatMessage>.unmodifiable(<ChatMessage>[
      ...currentSession.messages,
      ...optimisticMessages,
    ]);
  }

  int activeJobCountForSession(String sessionId) {
    return _pendingJobs.values
        .where((trackedSessionId) => trackedSessionId == sessionId)
        .length;
  }

  SessionActiveJobSummary? activeJobSummaryForSession(String sessionId) {
    final jobIds = _pendingJobs.entries
        .where((entry) => entry.value == sessionId)
        .map((entry) => entry.key)
        .toList(growable: false);

    if (jobIds.isEmpty) {
      return null;
    }

    var maxElapsedSeconds = 0;
    JobStatusResponse? primarySnapshot;
    final activeSession =
        _currentSession != null && _currentSession!.id == sessionId
            ? _currentSession
            : null;
    ChatSessionSummary? sessionSummary;
    for (final session in _sessions) {
      if (session.id == sessionId) {
        sessionSummary = session;
        break;
      }
    }

    for (final jobId in jobIds) {
      final snapshot = _jobSnapshots[jobId];
      final elapsedSeconds = snapshot?.elapsedSeconds ?? 0;
      if (elapsedSeconds > maxElapsedSeconds) {
        maxElapsedSeconds = elapsedSeconds;
      }
      if (snapshot == null) {
        continue;
      }
      if (_isBetterActiveJobSnapshot(snapshot, primarySnapshot)) {
        primarySnapshot = snapshot;
      }
    }

    return SessionActiveJobSummary(
      activeJobCount: jobIds.length,
      maxElapsedSeconds: maxElapsedSeconds,
      primaryAgentId: primarySnapshot?.agentId ?? AgentId.generator,
      primaryAgentLabel: primarySnapshot != null
          ? (_resolveConfiguredAgentLabel(
                primarySnapshot,
                activeSession,
                sessionSummary,
              ) ??
              primarySnapshot.agentLabel ??
              _defaultAgentLabel(primarySnapshot.agentId))
          : _defaultAgentLabel(AgentId.generator),
      primaryAgentSeed: primarySnapshot != null
          ? agentIdToJson(primarySnapshot.agentId)
          : agentIdToJson(AgentId.generator),
    );
  }

  SessionOutgoingUploadSummary? outgoingUploadSummaryForSession(
    String sessionId,
  ) {
    var audioCount = 0;
    var imageCount = 0;
    var fileCount = 0;
    var mixedCount = 0;

    for (final upload in _outgoingUploads.values) {
      if (upload.sessionId != sessionId) {
        continue;
      }
      switch (upload.kind) {
        case OutgoingUploadKind.audio:
          audioCount += 1;
          break;
        case OutgoingUploadKind.image:
          imageCount += 1;
          break;
        case OutgoingUploadKind.file:
          fileCount += 1;
          break;
        case OutgoingUploadKind.mixed:
          mixedCount += 1;
          break;
      }
    }

    final totalCount = audioCount + imageCount + fileCount + mixedCount;
    if (totalCount == 0) {
      return null;
    }

    return SessionOutgoingUploadSummary(
      audioCount: audioCount,
      imageCount: imageCount,
      fileCount: fileCount,
      mixedCount: mixedCount,
    );
  }

  Future<void> initialize() async {
    _setLoading(true);
    try {
      await refreshAppState();
    } finally {
      _setLoading(false);
    }
  }

  Future<void> refreshAppState({String? failurePrefix}) async {
    try {
      await Future.wait<void>(<Future<void>>[
        refreshSessions(),
        refreshWorkspaces(),
      ]);
      await _restoreCurrentSelectionAfterRefresh();
      try {
        await refreshAgentProfiles();
      } catch (error) {
        if (_errorText == null) {
          _errorText = 'Agent profiles are unavailable.\n$error';
          notifyListeners();
        }
      }

      for (final jobId in _pendingJobs.keys.toList()) {
        _ensureJobStream(jobId);
      }
      if (_pendingJobs.isNotEmpty) {
        _ensurePolling();
      }
    } catch (error) {
      _errorText = failurePrefix == null ? '$error' : '$failurePrefix\n$error';
      notifyListeners();
    }
  }

  Future<void> refreshSessions() async {
    final sessions = await _apiClient.listSessions();
    sessions.sort(_compareSessionsByRecentActivity);
    _sessions
      ..clear()
      ..addAll(sessions);
    _errorText = null;
    _flushDeferredRunNotifications();
    notifyListeners();
  }

  static int _compareSessionsByRecentActivity(
    ChatSessionSummary left,
    ChatSessionSummary right,
  ) {
    final latestComparison = right.latestActivityAt.compareTo(
      left.latestActivityAt,
    );
    if (latestComparison != 0) {
      return latestComparison;
    }
    final createdComparison = right.createdAt.compareTo(left.createdAt);
    if (createdComparison != 0) {
      return createdComparison;
    }
    return right.id.compareTo(left.id);
  }

  Future<void> refreshWorkspaces() async {
    final workspaces = await _apiClient.listWorkspaces();
    _workspaces
      ..clear()
      ..addAll(workspaces);
    _errorText = null;
    notifyListeners();
  }

  Future<void> refreshAgentProfiles() async {
    final profiles = await _apiClient.listAgentProfiles();
    _agentProfiles
      ..clear()
      ..addAll(profiles);
    _errorText = null;
    notifyListeners();
  }

  Future<void> handleAppResumed() async {
    await refreshAppState(failurePrefix: 'Failed to reconnect to the backend.');
  }

  Future<void> createNewSession({String? workspacePath, String? title}) async {
    await createNewSessionWithProfile(
      workspacePath: workspacePath,
      title: title,
    );
  }

  Future<void> createNewSessionWithProfile({
    String? workspacePath,
    String? agentProfileId,
    String? title,
    bool turnSummariesEnabled = false,
  }) async {
    _setLoading(true);
    try {
      final session = await _apiClient.createSession(
        title: title,
        workspacePath: workspacePath,
        agentProfileId: agentProfileId,
        turnSummariesEnabled: turnSummariesEnabled,
      );
      _errorText = null;
      await refreshSessions();
      _selectedSessionId = session.id;
      _currentSession = session;
      _trackPendingJobsFromSession(session);
      notifyListeners();
    } catch (error) {
      _errorText = '$error';
      notifyListeners();
    } finally {
      _setLoading(false);
    }
  }

  Future<AgentProfile?> createAgentProfile({
    required String name,
    required String description,
    required String colorHex,
    required AgentConfiguration configuration,
  }) async {
    try {
      _errorText = null;
      final profile = await _apiClient.createAgentProfile(
        name: name,
        description: description,
        colorHex: colorHex,
        configuration: configuration,
      );
      await refreshAgentProfiles();
      notifyListeners();
      return profile;
    } catch (error) {
      _errorText = 'Failed to create agent profile.\n$error';
      notifyListeners();
      return null;
    }
  }

  Future<String?> exportAgentProfilesAsJson() async {
    try {
      _errorText = null;
      final profiles = await _apiClient.exportAgentProfiles();
      return jsonEncode(<String, dynamic>{
        'profiles': profiles.map((profile) => profile.toJson()).toList(),
      });
    } catch (error) {
      _errorText = 'Failed to export agent profiles.\n$error';
      notifyListeners();
      return null;
    }
  }

  Future<bool> importAgentProfilesFromJson(String rawJson) async {
    try {
      final decoded = jsonDecode(rawJson);
      final rawProfiles = switch (decoded) {
        {'profiles': final List<dynamic> profiles} => profiles,
        final List<dynamic> profiles => profiles,
        _ => throw const FormatException(
            'Expected either a JSON array or an object with a profiles array.',
          ),
      };
      final profiles = rawProfiles
          .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
          .toList();
      _errorText = null;
      await _apiClient.importAgentProfiles(profiles);
      await refreshAgentProfiles();
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to import agent profiles.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> applyAgentProfile(String profileId) async {
    final sessionId = _selectedSessionId;
    if (sessionId == null) {
      return false;
    }

    try {
      _errorText = null;
      final session = await _apiClient.applyAgentProfile(
        sessionId,
        profileId: profileId,
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      await refreshSessions();
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to apply agent profile.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> setSessionArchived(
    String sessionId, {
    required bool archived,
  }) async {
    try {
      _errorText = null;
      final session = await _apiClient.setSessionArchived(
        sessionId,
        archived: archived,
      );
      await refreshSessions();
      if (_selectedSessionId == sessionId) {
        _currentSession = _overlaySessionWithJobSnapshots(session);
        _reconcilePendingJobsForSession(_currentSession);
        _trackPendingJobsFromSession(_currentSession);
      }
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to update archive state.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> renameSession(String sessionId, {required String title}) async {
    try {
      _errorText = null;
      final session = await _apiClient.renameSession(sessionId, title: title);
      await _applyUpdatedSession(sessionId, session);
      return true;
    } catch (error) {
      _errorText = 'Failed to rename chat.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> generateSessionTitle(
    String sessionId, {
    String? instructions,
  }) async {
    try {
      _errorText = null;
      final session = await _apiClient.generateSessionTitle(
        sessionId,
        instructions: instructions,
      );
      await _applyUpdatedSession(sessionId, session);
      return true;
    } catch (error) {
      _errorText = 'Failed to generate chat title.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> generateSessionTitleFromAudio(
    String sessionId,
    XFile audioFile, {
    String? instructions,
  }) async {
    try {
      _errorText = null;
      final session = await _apiClient.generateSessionTitleFromAudio(
        sessionId,
        audioFile,
        instructions: instructions,
      );
      await _applyUpdatedSession(sessionId, session);
      return true;
    } catch (error) {
      _errorText = 'Failed to generate chat title from audio.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<void> selectSession(String sessionId) async {
    ChatSessionSummary? sessionSummary;
    for (final session in _sessions) {
      if (session.id == sessionId) {
        sessionSummary = session;
        break;
      }
    }
    if (sessionSummary != null) {
      _selectedSessionId = sessionId;
      _currentSession = _placeholderSessionDetail(sessionSummary);
      _errorText = null;
      notifyListeners();
    }

    _setLoading(true);
    try {
      final session = await _apiClient.getSession(
        sessionId,
        limit: initialTranscriptMessageLimit,
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      _selectedSessionId = sessionId;
      _olderMessagesError = null;
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      await _maybeImportGeneratedAgentProfiles(_currentSession);
      _errorText = null;
      _flushDeferredRunNotifications();
      notifyListeners();
    } catch (error) {
      _errorText = '$error';
      notifyListeners();
    } finally {
      _setLoading(false);
    }
  }

  Future<bool> loadOlderMessages() async {
    final currentSession = _currentSession;
    if (currentSession == null ||
        _isLoadingOlderMessages ||
        !currentSession.transcriptWindow.hasOlder) {
      return false;
    }
    final cursor = currentSession.transcriptWindow.oldestCursor;
    if (cursor == null || cursor.isEmpty) {
      return false;
    }

    _isLoadingOlderMessages = true;
    _olderMessagesError = null;
    notifyListeners();
    try {
      final olderPage = await _apiClient.getSession(
        currentSession.id,
        before: cursor,
        limit: olderTranscriptPageLimit,
      );
      if (_currentSession?.id != currentSession.id) {
        return false;
      }
      _currentSession = _overlaySessionWithJobSnapshots(
        olderPage.copyWith(
          messages: _mergePrependedMessages(
            olderPage.messages,
            _currentSession!.messages,
          ),
          transcriptWindow: olderPage.transcriptWindow.copyWith(
            newestCursor: _currentSession!.transcriptWindow.newestCursor,
            hasNewer: false,
            windowAnchorMessageId:
                _currentSession!.transcriptWindow.windowAnchorMessageId,
            isPartial: olderPage.transcriptWindow.hasOlder,
          ),
        ),
      );
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      _olderMessagesError = null;
      notifyListeners();
      return true;
    } catch (error) {
      _olderMessagesError = '$error';
      notifyListeners();
      return false;
    } finally {
      _isLoadingOlderMessages = false;
      notifyListeners();
    }
  }

  static List<ChatMessage> _mergePrependedMessages(
    List<ChatMessage> olderMessages,
    List<ChatMessage> currentMessages,
  ) {
    final seen = <String>{};
    final merged = <ChatMessage>[];
    for (final message in <ChatMessage>[...olderMessages, ...currentMessages]) {
      if (seen.add(message.id)) {
        merged.add(message);
      }
    }
    return List<ChatMessage>.unmodifiable(merged);
  }

  Future<bool> updateAutoMode({
    required bool enabled,
    required int maxTurns,
    String? reviewerPrompt,
  }) async {
    final sessionId = _selectedSessionId;
    if (sessionId == null) {
      return false;
    }

    try {
      _errorText = null;
      final currentSession = _currentSession;
      if (currentSession == null) {
        return false;
      }
      final currentConfiguration = currentSession.agentConfiguration;
      final updatedAgents = currentConfiguration.agents.map((agent) {
        switch (agent.agentId) {
          case AgentId.reviewer:
            return agent.copyWith(
              enabled: enabled,
              maxTurns: maxTurns,
              prompt: reviewerPrompt ?? agent.prompt,
            );
          case AgentId.summary:
            return agent.copyWith(enabled: false, maxTurns: 0);
          default:
            return agent;
        }
      }).toList(growable: false);
      final session = await _apiClient.updateAgentConfiguration(
        sessionId,
        configuration: currentConfiguration.copyWith(
          preset: enabled ? AgentPreset.review : AgentPreset.solo,
          agents: updatedAgents,
        ),
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      await refreshSessions();
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to update auto mode.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateAgentConfiguration(
    AgentConfiguration configuration,
  ) async {
    final sessionId = _selectedSessionId;
    if (sessionId == null) {
      return false;
    }

    try {
      _errorText = null;
      final session = await _apiClient.updateAgentConfiguration(
        sessionId,
        configuration: configuration,
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      await refreshSessions();
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to update agent configuration.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> startDomainFactoryMode({String? workspacePathOverride}) async {
    final sessionId = _selectedSessionId;
    final currentSession = _currentSession;
    if (sessionId == null || currentSession == null) {
      _errorText = 'Choose a project chat before starting Domain Factory.';
      notifyListeners();
      return false;
    }

    try {
      _errorText = null;
      final result = await _apiClient.startDomainFactoryMode(
        sessionId,
        workspacePath: workspacePathOverride ?? currentSession.workspacePath,
      );
      _currentSession = _overlaySessionWithJobSnapshots(result.session);
      await refreshSessions();
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      notifyListeners();
      return result.isReady;
    } catch (error) {
      _errorText = 'Failed to start Domain Factory.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateTurnSummariesEnabled(bool enabled) async {
    final sessionId = _selectedSessionId;
    if (sessionId == null) {
      return false;
    }

    try {
      _errorText = null;
      final session = await _apiClient.updateTurnSummaries(
        sessionId,
        enabled: enabled,
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      await refreshSessions();
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = _formatActionError(
        'Failed to update turn summaries.',
        error,
      );
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateAgentStudioSettings({
    required AgentConfiguration configuration,
    required bool turnSummariesEnabled,
  }) async {
    final currentSession = _currentSession;
    if (currentSession == null) {
      return false;
    }

    final configChanged =
        currentSession.agentConfiguration.toJson().toString() !=
            configuration.toJson().toString();
    final turnSummariesChanged =
        currentSession.turnSummariesEnabled != turnSummariesEnabled;

    if (!configChanged && !turnSummariesChanged) {
      return true;
    }

    if (configChanged && !await updateAgentConfiguration(configuration)) {
      return false;
    }
    if (turnSummariesChanged &&
        !await updateTurnSummariesEnabled(turnSummariesEnabled)) {
      return false;
    }
    return true;
  }

  Future<bool> sendMessage(
    String rawText, {
    String? sessionIdOverride,
    String? workspacePathOverride,
    CodexRunOptions? codexRunOptions,
  }) async {
    final text = rawText.trim();
    if (text.isEmpty) {
      return false;
    }
    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;

    try {
      _errorText = null;
      final accepted = await _apiClient.sendMessage(
        text,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        codexRunOptions: codexRunOptions,
      );
      await _registerAcceptedJob(accepted, originSessionId: originSessionId);
      return true;
    } catch (error) {
      _errorText = 'Failed to send message.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<void> registerAcceptedExternalJob(JobStatusResponse accepted) async {
    _errorText = null;
    await _registerAcceptedJob(accepted, originSessionId: _selectedSessionId);
  }

  Future<bool> sendAudioMessage(
    XFile audioFile, {
    String? message,
    String? language,
    String? sessionIdOverride,
    String? workspacePathOverride,
    CodexRunOptions? codexRunOptions,
  }) async {
    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;
    final outgoingUploadToken = _beginOutgoingUpload(
      originSessionId,
      OutgoingUploadKind.audio,
    );
    _beginOptimisticAudioMessage(
      outgoingUploadToken,
      sessionId: originSessionId,
    );
    _sendingAudioCount += 1;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendAudioMessage(
        audioFile,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        message: message,
        language: language,
        codexRunOptions: codexRunOptions,
      );
      await _registerAcceptedJob(accepted, originSessionId: originSessionId);
      return true;
    } catch (error) {
      _errorText = 'Failed to send audio message.\n$error';
      notifyListeners();
      return false;
    } finally {
      _sendingAudioCount -= 1;
      _finishOutgoingUpload(outgoingUploadToken);
      notifyListeners();
    }
  }

  Future<bool> sendImageMessage(
    XFile imageFile, {
    String? message,
    String? sessionIdOverride,
    String? workspacePathOverride,
    CodexRunOptions? codexRunOptions,
  }) async {
    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;
    final outgoingUploadToken = _beginOutgoingUpload(
      originSessionId,
      OutgoingUploadKind.image,
    );
    _sendingImageCount += 1;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendImageMessage(
        imageFile,
        message: message,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        codexRunOptions: codexRunOptions,
      );
      await _registerAcceptedJob(accepted, originSessionId: originSessionId);
      return true;
    } catch (error) {
      _errorText = 'Failed to send image message.\n$error';
      notifyListeners();
      return false;
    } finally {
      _sendingImageCount -= 1;
      _finishOutgoingUpload(outgoingUploadToken);
      notifyListeners();
    }
  }

  Future<bool> sendDocumentMessage(
    XFile documentFile, {
    String? message,
    String? language,
    String? sessionIdOverride,
    String? workspacePathOverride,
    CodexRunOptions? codexRunOptions,
  }) async {
    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;
    final outgoingUploadToken = _beginOutgoingUpload(
      originSessionId,
      OutgoingUploadKind.file,
    );
    _sendingDocumentCount += 1;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendDocumentMessage(
        documentFile,
        message: message,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        language: language,
        codexRunOptions: codexRunOptions,
      );
      await _registerAcceptedJob(accepted, originSessionId: originSessionId);
      return true;
    } catch (error) {
      _errorText = 'Failed to send document.\n$error';
      notifyListeners();
      return false;
    } finally {
      _sendingDocumentCount -= 1;
      _finishOutgoingUpload(outgoingUploadToken);
      notifyListeners();
    }
  }

  Future<bool> sendAttachmentsMessage(
    List<XFile> attachments, {
    String? message,
    String? language,
    String? sessionIdOverride,
    String? workspacePathOverride,
    CodexRunOptions? codexRunOptions,
  }) async {
    if (attachments.isEmpty) {
      return false;
    }

    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;
    final outgoingUploadToken = _beginOutgoingUpload(
      originSessionId,
      _resolveAttachmentsUploadKind(attachments),
    );
    _sendingDocumentCount += 1;
    _sendingImageCount += 1;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendAttachmentsMessage(
        attachments,
        message: message,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        language: language,
        codexRunOptions: codexRunOptions,
      );
      await _registerAcceptedJob(accepted, originSessionId: originSessionId);
      return true;
    } catch (error) {
      _errorText = 'Failed to send attachments.\n$error';
      notifyListeners();
      return false;
    } finally {
      _sendingDocumentCount -= 1;
      _sendingImageCount -= 1;
      _finishOutgoingUpload(outgoingUploadToken);
      notifyListeners();
    }
  }

  Future<bool> cancelJob(String jobId) async {
    final sessionId = _sessionIdForJob(jobId);

    try {
      _errorText = null;
      final snapshot = await _apiClient.cancelJob(jobId);
      _applyJobSnapshot(snapshot);
      if (snapshot.isTerminal) {
        _finishTrackingJob(jobId);
      }
      await refreshSessions();
      if (sessionId != null && sessionId == _selectedSessionId) {
        await _reloadCurrentSession();
      } else {
        notifyListeners();
      }
      return true;
    } catch (error) {
      _errorText = 'Failed to cancel job.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> retryJob(String jobId) async {
    final originSessionId = _sessionIdForJob(jobId);

    try {
      _errorText = null;
      final accepted = await _apiClient.retryJob(jobId);
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId ?? accepted.sessionId,
      );
      return true;
    } catch (error) {
      _errorText = 'Failed to retry job.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> recoverMessage(
    String messageId, {
    required MessageRecoveryAction action,
  }) async {
    final sessionId = _selectedSessionId;
    if (sessionId == null) {
      return false;
    }

    try {
      _errorText = null;
      final session = await _apiClient.recoverMessage(
        sessionId,
        messageId,
        action: action,
      );
      _currentSession = _overlaySessionWithJobSnapshots(session);
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      await refreshSessions();
      notifyListeners();
      return true;
    } catch (error) {
      _errorText = 'Failed to recover message.\n$error';
      notifyListeners();
      return false;
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    for (final channel in _jobChannels.values.toList(growable: false)) {
      channel.sink.close();
    }
    _jobChannels.clear();
    super.dispose();
  }

  void _ensurePolling() {
    _pollTimer ??= Timer.periodic(
      const Duration(seconds: 2),
      (_) => _pollJobs(),
    );
    _pollJobs();
  }

  Future<void> _pollJobs() async {
    if (_pollInFlight || _pendingJobs.isEmpty) {
      if (_pendingJobs.isEmpty) {
        _pollTimer?.cancel();
        _pollTimer = null;
      }
      return;
    }

    _pollInFlight = true;
    try {
      final completedJobs = <String>[];
      var shouldRefreshSessions = false;
      var shouldReloadCurrentSession = false;

      for (final entry in _pendingJobs.entries.toList()) {
        try {
          final result = await _apiClient.getJob(entry.key);
          _pollFailures.remove(entry.key);
          _applyJobSnapshot(result);
          _errorText = null;
          if (result.isTerminal) {
            completedJobs.add(entry.key);
            shouldRefreshSessions = true;
            if (result.sessionId == _selectedSessionId) {
              shouldReloadCurrentSession = true;
            }
          }
        } catch (error) {
          final failures = (_pollFailures[entry.key] ?? 0) + 1;
          _pollFailures[entry.key] = failures;
          final errorText = '$error';
          if (errorText.contains('404') ||
              errorText.contains('Job not found')) {
            completedJobs.add(entry.key);
            continue;
          }
          if (failures >= 3) {
            _errorText =
                'Connection to the backend was interrupted. Retrying automatically.\n$error';
            notifyListeners();
          }
        }
      }

      for (final jobId in completedJobs) {
        _finishTrackingJob(jobId);
      }

      if (shouldRefreshSessions) {
        await refreshSessions();
      }
      if (shouldReloadCurrentSession) {
        await _reloadCurrentSession();
      } else if (completedJobs.isNotEmpty) {
        notifyListeners();
      }
    } finally {
      _pollInFlight = false;
    }
  }

  Future<void> _reloadCurrentSession() async {
    if (_selectedSessionId == null) {
      notifyListeners();
      return;
    }

    final session = await _apiClient.getSession(
      _selectedSessionId!,
      limit: initialTranscriptMessageLimit,
    );
    _currentSession = _overlaySessionWithJobSnapshots(
      _mergeWithCurrentSession(session),
    );
    _reconcilePendingJobsForSession(_currentSession);
    _trackPendingJobsFromSession(_currentSession);
    await _maybeImportGeneratedAgentProfiles(_currentSession);
    _errorText = null;
    _flushDeferredRunNotifications();
    notifyListeners();
  }

  Future<void> _restoreCurrentSelectionAfterRefresh() async {
    final selectedSessionId = _selectedSessionId;
    if (selectedSessionId != null &&
        _sessions.any((session) => session.id == selectedSessionId)) {
      await _reloadCurrentSession();
      return;
    }

    if (_sessions.isNotEmpty) {
      await selectSession(_sessions.first.id);
      return;
    }

    _selectedSessionId = null;
    _currentSession = null;
    _errorText = null;
    notifyListeners();
  }

  Future<void> _registerAcceptedJob(
    JobStatusResponse accepted, {
    required String? originSessionId,
  }) async {
    final resolvedSessionId = accepted.sessionId.isNotEmpty
        ? accepted.sessionId
        : (originSessionId ?? _selectedSessionId ?? '');
    final acceptedSnapshot = accepted.sessionId == resolvedSessionId
        ? accepted
        : accepted.copyWith(sessionId: resolvedSessionId);
    final shouldKeepOriginSessionSelected =
        _selectedSessionId == null || _selectedSessionId == originSessionId;

    _pendingJobs[acceptedSnapshot.jobId] = resolvedSessionId;
    _jobSnapshots[acceptedSnapshot.jobId] = acceptedSnapshot;
    _handledTerminalJobs.remove(acceptedSnapshot.jobId);
    _ensureJobStream(acceptedSnapshot.jobId);
    _ensurePolling();

    await refreshSessions();

    if (shouldKeepOriginSessionSelected ||
        _selectedSessionId == resolvedSessionId) {
      _selectedSessionId = resolvedSessionId;
      await _reloadCurrentSession();
    }
  }

  void _reconcilePendingJobsForSession(SessionDetail? session) {
    if (session == null) {
      return;
    }

    final activePendingJobIds = session.messages
        .where((message) {
          final jobStatus = message.jobStatus ?? '';
          return message.jobId != null &&
              (message.isPendingLike ||
                  jobStatus == 'pending' ||
                  jobStatus == 'running');
        })
        .map((message) => message.jobId!)
        .toSet();

    final staleJobIds = _pendingJobs.entries
        .where(
          (entry) =>
              entry.value == session.id &&
              !activePendingJobIds.contains(entry.key),
        )
        .map((entry) => entry.key)
        .toList(growable: false);

    for (final jobId in staleJobIds) {
      _finishTrackingJob(jobId);
    }
  }

  void _trackPendingJobsFromSession(SessionDetail? session) {
    if (session == null) {
      return;
    }

    for (final message in session.messages) {
      if (message.jobId == null) {
        continue;
      }
      final jobStatus = message.jobStatus ?? '';
      final isPending = message.isPendingLike ||
          jobStatus == 'pending' ||
          jobStatus == 'running';
      if (!isPending) {
        continue;
      }
      _pendingJobs[message.jobId!] = session.id;
      _jobSnapshots[message.jobId!] ??= JobStatusResponse(
        jobId: message.jobId!,
        sessionId: session.id,
        status: jobStatus.isNotEmpty ? jobStatus : 'pending',
        elapsedSeconds: message.jobElapsedSeconds ?? 0,
        agentId: message.agentId,
        agentType: message.agentType,
        agentLabel: message.agentLabel,
        providerSessionId: message.providerSessionId,
        runId: message.runId,
        phase: message.jobPhase,
        latestActivity: message.jobLatestActivity,
        updatedAt: message.updatedAt,
        completedAt: message.completedAt,
      );
      _ensureJobStream(message.jobId!);
    }

    if (_pendingJobs.isNotEmpty) {
      _ensurePolling();
    }
  }

  void _ensureJobStream(String jobId) {
    if (_jobChannels.containsKey(jobId)) {
      return;
    }

    try {
      final channel = WebSocketChannel.connect(_apiClient.jobStreamUri(jobId));
      _jobChannels[jobId] = channel;
      channel.stream.listen(
        (event) {
          if (event is! String) {
            return;
          }
          final payload = jsonDecode(event) as Map<String, dynamic>;
          if (payload.containsKey('error')) {
            _errorText = payload['error'] as String?;
            notifyListeners();
            return;
          }
          final snapshot = JobStatusResponse.fromJson(payload);
          _applyJobSnapshot(snapshot);
          _errorText = null;
          if (snapshot.isTerminal) {
            _finishTrackingJob(jobId);
            refreshSessions();
            if (snapshot.sessionId == _selectedSessionId) {
              _reloadCurrentSession();
            } else {
              notifyListeners();
            }
          }
        },
        onError: (_) {
          _jobChannels.remove(jobId);
          if (_pendingJobs.containsKey(jobId)) {
            _ensurePolling();
          }
        },
        onDone: () {
          _jobChannels.remove(jobId);
          if (_pendingJobs.containsKey(jobId)) {
            _ensurePolling();
          }
        },
        cancelOnError: true,
      );
    } catch (_) {
      // Keep polling as the fallback path.
    }
  }

  void _applyJobSnapshot(JobStatusResponse snapshot) {
    _jobSnapshots[snapshot.jobId] = snapshot;
    _maybeNotifyForTerminalJob(snapshot);

    if (_currentSession == null) {
      notifyListeners();
      return;
    }

    final updatedMessages = _currentSession!.messages
        .map((message) => _applySnapshotToMessage(message, snapshot))
        .toList(growable: false);
    final updatedCurrentRun = _applySnapshotToRun(
      _currentSession!.currentRun,
      snapshot,
    );
    final updatedRecentRuns = _applySnapshotToRuns(
      _currentSession!.recentRuns,
      snapshot,
    );

    _currentSession = _currentSession!.copyWith(
      messages: updatedMessages,
      currentRun: updatedCurrentRun,
      recentRuns: updatedRecentRuns,
    );
    notifyListeners();
  }

  ChatMessage _applySnapshotToMessage(
    ChatMessage message,
    JobStatusResponse snapshot,
  ) {
    if (message.jobId != snapshot.jobId) {
      return message;
    }

    return message.copyWith(
      text: snapshot.status == 'failed' || snapshot.status == 'cancelled'
          ? (snapshot.error ?? message.text)
          : (snapshot.response ?? message.text),
      status: _statusFromJob(snapshot.status),
      jobStatus: snapshot.status,
      jobPhase: snapshot.phase,
      jobLatestActivity: snapshot.latestActivity,
      jobElapsedSeconds: snapshot.elapsedSeconds,
      providerSessionId: snapshot.providerSessionId,
      updatedAt: snapshot.updatedAt ?? message.updatedAt,
      completedAt: snapshot.completedAt ?? message.completedAt,
    );
  }

  SessionDetail _overlaySessionWithJobSnapshots(SessionDetail session) {
    final messages = session.messages.map((message) {
      if (message.jobId == null) {
        return message;
      }
      final snapshot = _jobSnapshots[message.jobId!];
      if (snapshot == null) {
        return message;
      }
      return _applySnapshotToMessage(message, snapshot);
    }).toList(growable: false);
    var currentRun = session.currentRun;
    var recentRuns = session.recentRuns;
    for (final snapshot in _jobSnapshots.values) {
      if (snapshot.sessionId != session.id) {
        continue;
      }
      currentRun = _applySnapshotToRun(currentRun, snapshot);
      recentRuns = _applySnapshotToRuns(recentRuns, snapshot);
    }

    return session.copyWith(
      messages: messages,
      currentRun: currentRun,
      recentRuns: recentRuns,
    );
  }

  Future<void> _maybeImportGeneratedAgentProfiles(
    SessionDetail? session,
  ) async {
    if (session == null || session.agentProfileId != 'agent_creator') {
      return;
    }

    final knownProfileIds = <String>{
      ..._autoImportedAgentProfileIds,
      ..._agentProfiles.map((profile) => profile.id),
    };
    final profilesToImport = <AgentProfile>[];

    for (final message in session.messages.reversed) {
      if (message.isUser || message.status != ChatMessageStatus.completed) {
        continue;
      }
      final generatedProfiles = extractAgentProfilesFromMessage(message.text);
      for (final profile in generatedProfiles) {
        if (knownProfileIds.add(profile.id)) {
          profilesToImport.add(profile);
        }
      }
    }

    if (profilesToImport.isEmpty) {
      return;
    }

    try {
      final importedProfiles = await _apiClient.importAgentProfiles(
        profilesToImport,
      );
      _autoImportedAgentProfileIds.addAll(
        importedProfiles.map((profile) => profile.id),
      );
      await refreshAgentProfiles();
    } catch (_) {
      // Ignore malformed generated blueprints so the chat stays usable.
    }
  }

  void _finishTrackingJob(String jobId) {
    _pendingJobs.remove(jobId);
    _pollFailures.remove(jobId);
    _jobChannels.remove(jobId)?.sink.close();
  }

  void _maybeNotifyForTerminalJob(JobStatusResponse snapshot) {
    if (!snapshot.isTerminal) {
      return;
    }
    if (_handledTerminalJobs.contains(snapshot.jobId)) {
      return;
    }
    _handledTerminalJobs.add(snapshot.jobId);

    if (snapshot.status == 'cancelled') {
      return;
    }

    final runId = _runIdForJob(snapshot);
    if (runId != null && _isRunStillActive(snapshot.sessionId, runId)) {
      _deferredRunNotifications[runId] = _DeferredRunNotification(
        runId: runId,
        snapshot: snapshot,
      );
      return;
    }

    if (runId != null && _wasRunMultiAgent(snapshot.sessionId, runId)) {
      final notification = _buildRunTerminalNotification(snapshot, runId);
      unawaited(_notificationService.showChatCompleted(notification));
      return;
    }

    final notification = _buildTerminalNotification(snapshot);
    unawaited(_notificationService.showChatCompleted(notification));
  }

  void _flushDeferredRunNotifications() {
    if (_deferredRunNotifications.isEmpty) {
      return;
    }

    for (final entry in _deferredRunNotifications.entries.toList()) {
      final deferred = entry.value;
      if (_isRunStillActive(deferred.snapshot.sessionId, deferred.runId)) {
        continue;
      }
      _deferredRunNotifications.remove(entry.key);
      final notification = _buildRunTerminalNotification(
        deferred.snapshot,
        deferred.runId,
      );
      unawaited(_notificationService.showChatCompleted(notification));
    }
  }

  ChatCompletedNotification _buildTerminalNotification(
    JobStatusResponse snapshot,
  ) {
    final session = _sessionDetailForId(snapshot.sessionId);
    final sessionSummary = _sessionSummaryForId(snapshot.sessionId);
    final sessionTitle = _resolveSessionTitle(snapshot.sessionId, session);
    final workspaceName = _resolveWorkspaceName(snapshot.sessionId, session);
    return buildChatCompletedNotification(
      snapshot: snapshot,
      workspaceName: workspaceName,
      sessionTitle: sessionTitle,
      configuredAgentLabel: _resolveConfiguredAgentLabel(
        snapshot,
        session,
        sessionSummary,
      ),
    );
  }

  ChatCompletedNotification _buildRunTerminalNotification(
    JobStatusResponse snapshot,
    String runId,
  ) {
    final session = _sessionDetailForId(snapshot.sessionId);
    final sessionTitle = _resolveSessionTitle(snapshot.sessionId, session);
    final workspaceName = _resolveWorkspaceName(snapshot.sessionId, session);
    return buildRunCompletedNotification(
      snapshot: snapshot,
      runId: runId,
      workspaceName: workspaceName,
      sessionTitle: sessionTitle,
    );
  }

  SessionDetail? _sessionDetailForId(String sessionId) {
    final currentSession = _currentSession;
    if (currentSession != null && currentSession.id == sessionId) {
      return currentSession;
    }
    return null;
  }

  Future<void> _applyUpdatedSession(
    String sessionId,
    SessionDetail session,
  ) async {
    await refreshSessions();
    if (_selectedSessionId == sessionId) {
      _currentSession = _overlaySessionWithJobSnapshots(
        _mergeWithCurrentSession(session),
      );
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
    }
    notifyListeners();
  }

  SessionDetail _mergeWithCurrentSession(SessionDetail freshSession) {
    final currentSession = _currentSession;
    if (currentSession == null || currentSession.id != freshSession.id) {
      return freshSession;
    }
    final messages = _mergeChronologicalMessages(
      currentSession.messages,
      freshSession.messages,
    );
    return freshSession.copyWith(
      messages: messages,
      transcriptWindow: freshSession.transcriptWindow.copyWith(
        oldestCursor: currentSession.transcriptWindow.oldestCursor,
        hasOlder: currentSession.transcriptWindow.hasOlder,
        isPartial: currentSession.transcriptWindow.hasOlder,
      ),
    );
  }

  static List<ChatMessage> _mergeChronologicalMessages(
    List<ChatMessage> left,
    List<ChatMessage> right,
  ) {
    final byId = <String, ChatMessage>{};
    for (final message in <ChatMessage>[...left, ...right]) {
      byId[message.id] = message;
    }
    final messages = byId.values.toList(growable: false)
      ..sort((left, right) {
        final createdComparison = left.createdAt.compareTo(right.createdAt);
        if (createdComparison != 0) {
          return createdComparison;
        }
        return left.id.compareTo(right.id);
      });
    return List<ChatMessage>.unmodifiable(messages);
  }

  ChatSessionSummary? _sessionSummaryForId(String sessionId) {
    for (final summary in _sessions) {
      if (summary.id == sessionId) {
        return summary;
      }
    }
    return null;
  }

  String _resolveSessionTitle(String sessionId, SessionDetail? session) {
    if (session != null && session.title.trim().isNotEmpty) {
      return session.title.trim();
    }

    for (final summary in _sessions) {
      if (summary.id == sessionId && summary.title.trim().isNotEmpty) {
        return summary.title.trim();
      }
    }

    return 'Chat';
  }

  String _resolveWorkspaceName(String sessionId, SessionDetail? session) {
    if (session != null && session.workspaceName.trim().isNotEmpty) {
      return session.workspaceName.trim();
    }

    for (final summary in _sessions) {
      if (summary.id == sessionId && summary.workspaceName.trim().isNotEmpty) {
        return summary.workspaceName.trim();
      }
    }

    return 'Codex Remote';
  }

  String? _resolveConfiguredAgentLabel(
    JobStatusResponse snapshot,
    SessionDetail? session,
    ChatSessionSummary? sessionSummary,
  ) {
    final sessionConfiguration = session?.agentConfiguration.byId(
      snapshot.agentId,
    );
    if (sessionConfiguration != null &&
        sessionConfiguration.label.trim().isNotEmpty) {
      return sessionConfiguration.label.trim();
    }

    final summaryConfiguration = sessionSummary?.agentConfiguration.byId(
      snapshot.agentId,
    );
    if (summaryConfiguration != null &&
        summaryConfiguration.label.trim().isNotEmpty) {
      return summaryConfiguration.label.trim();
    }

    return null;
  }

  @visibleForTesting
  ChatCompletedNotification buildTerminalNotificationForTesting(
    JobStatusResponse snapshot,
  ) {
    return _buildTerminalNotification(snapshot);
  }

  @visibleForTesting
  void applyJobSnapshotForTesting(JobStatusResponse snapshot) {
    _applyJobSnapshot(snapshot);
  }

  String? _runIdForJob(JobStatusResponse snapshot) {
    if (snapshot.runId != null && snapshot.runId!.trim().isNotEmpty) {
      return snapshot.runId;
    }

    final currentSession = _sessionDetailForId(snapshot.sessionId);
    if (currentSession != null) {
      for (final message in currentSession.messages) {
        if (message.jobId == snapshot.jobId &&
            message.runId != null &&
            message.runId!.trim().isNotEmpty) {
          return message.runId;
        }
      }

      for (final run in <CurrentRunExecution?>[
        currentSession.currentRun,
        ...currentSession.recentRuns,
      ]) {
        if (run == null) {
          continue;
        }
        if (run.stages.any((stage) => stage.jobId == snapshot.jobId)) {
          return run.runId;
        }
      }
    }

    return null;
  }

  bool _isRunStillActive(String sessionId, String runId) {
    final currentSession = _sessionDetailForId(sessionId);
    if (currentSession != null) {
      if (currentSession.activeAgentRunId == runId) {
        return true;
      }
      final currentRun = currentSession.currentRun;
      if (currentRun != null &&
          currentRun.runId == runId &&
          currentRun.isActive) {
        return true;
      }
      return false;
    }

    final summary = _sessionSummaryForId(sessionId);
    return summary?.activeAgentRunId == runId;
  }

  bool _wasRunMultiAgent(String sessionId, String runId) {
    final currentSession = _sessionDetailForId(sessionId);
    if (currentSession != null) {
      final run = _runExecutionForId(currentSession, runId);
      if (run != null && run.participantAgentIds.length > 1) {
        return true;
      }

      final participantIds = currentSession.messages
          .where((message) => message.runId == runId)
          .map((message) => message.agentId)
          .where((agentId) => agentId != AgentId.user)
          .toSet();
      if (participantIds.length > 1) {
        return true;
      }
    }

    final summary = _sessionSummaryForId(sessionId);
    final configuration = currentSession?.agentConfiguration ??
        summary?.agentConfiguration ??
        kDefaultAgentConfiguration;
    final normalized = configuration;
    return normalized.preset != AgentPreset.solo &&
        normalized.agents.any(
          (agent) =>
              agent.agentId != AgentId.generator &&
              agent.agentId != AgentId.user &&
              agent.enabled &&
              agent.maxTurns > 0,
        );
  }

  CurrentRunExecution? _runExecutionForId(SessionDetail session, String runId) {
    final currentRun = session.currentRun;
    if (currentRun != null && currentRun.runId == runId) {
      return currentRun;
    }

    for (final run in session.recentRuns) {
      if (run.runId == runId) {
        return run;
      }
    }
    return null;
  }

  void _setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }

  int? _beginOutgoingUpload(String? sessionId, OutgoingUploadKind kind) {
    if (sessionId == null) {
      return null;
    }

    final token = _nextOutgoingUploadToken;
    _nextOutgoingUploadToken += 1;
    _outgoingUploads[token] = _OutgoingUploadTicket(
      sessionId: sessionId,
      kind: kind,
    );
    return token;
  }

  void _beginOptimisticAudioMessage(int? token, {required String? sessionId}) {
    if (token == null || sessionId == null) {
      return;
    }

    final timestamp = DateTime.now().toUtc();
    _optimisticAudioMessages[token] = _OptimisticAudioMessage(
      sessionId: sessionId,
      message: ChatMessage(
        id: 'local-audio-upload-$token',
        text: 'Sending voice...',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.user,
        agentType: AgentType.human,
        status: ChatMessageStatus.sending,
        createdAt: timestamp,
        updatedAt: timestamp,
      ),
    );
  }

  void _finishOutgoingUpload(int? token) {
    if (token == null) {
      return;
    }
    _outgoingUploads.remove(token);
    _optimisticAudioMessages.remove(token);
  }

  OutgoingUploadKind _resolveAttachmentsUploadKind(List<XFile> attachments) {
    var imageCount = 0;
    for (final attachment in attachments) {
      if (_looksLikeImageAttachment(attachment)) {
        imageCount += 1;
      }
    }

    if (imageCount == attachments.length) {
      return OutgoingUploadKind.image;
    }
    if (imageCount == 0) {
      return OutgoingUploadKind.file;
    }
    return OutgoingUploadKind.mixed;
  }

  SessionDetail _placeholderSessionDetail(ChatSessionSummary session) {
    return SessionDetail(
      id: session.id,
      title: session.title,
      archivedAt: session.archivedAt,
      workspacePath: session.workspacePath,
      workspaceName: session.workspaceName,
      agentProfileId: session.agentProfileId,
      agentProfileName: session.agentProfileName,
      agentProfileColor: session.agentProfileColor,
      providerSessionId: session.providerSessionId,
      reviewerProviderSessionId: session.reviewerProviderSessionId,
      activeAgentRunId: session.activeAgentRunId,
      activeAgentTurnIndex: session.activeAgentTurnIndex,
      agentConfiguration: session.agentConfiguration,
      autoModeEnabled: session.autoModeEnabled,
      autoMaxTurns: session.autoMaxTurns,
      autoReviewerPrompt: session.autoReviewerPrompt,
      autoTurnIndex: session.autoTurnIndex,
      reviewerState: session.reviewerState,
      conversationProduct: session.conversationProduct,
      topicDescription: session.topicDescription,
      createdAt: session.createdAt,
      updatedAt: session.updatedAt,
      messages: const <ChatMessage>[],
    );
  }

  bool _looksLikeImageAttachment(XFile attachment) {
    final mimeType = attachment.mimeType;
    if (mimeType != null && mimeType.toLowerCase().startsWith('image/')) {
      return true;
    }

    final name = attachment.name.toLowerCase();
    return name.endsWith('.bmp') ||
        name.endsWith('.gif') ||
        name.endsWith('.jpeg') ||
        name.endsWith('.jpg') ||
        name.endsWith('.png') ||
        name.endsWith('.tif') ||
        name.endsWith('.tiff') ||
        name.endsWith('.webp');
  }

  String? _sessionIdForJob(String jobId) {
    final trackedSessionId =
        _pendingJobs[jobId] ?? _jobSnapshots[jobId]?.sessionId;
    if (trackedSessionId != null) {
      return trackedSessionId;
    }

    final currentSession = _currentSession;
    if (currentSession == null) {
      return null;
    }

    for (final message in currentSession.messages) {
      if (message.jobId == jobId) {
        return currentSession.id;
      }
    }
    return null;
  }

  bool _isBetterActiveJobSnapshot(
    JobStatusResponse candidate,
    JobStatusResponse? current,
  ) {
    if (current == null) {
      return true;
    }

    final candidatePriority = _activeJobStatusPriority(candidate.status);
    final currentPriority = _activeJobStatusPriority(current.status);
    if (candidatePriority != currentPriority) {
      return candidatePriority > currentPriority;
    }

    if (candidate.elapsedSeconds != current.elapsedSeconds) {
      return candidate.elapsedSeconds > current.elapsedSeconds;
    }

    final candidateTimestamp = candidate.updatedAt ?? candidate.completedAt;
    final currentTimestamp = current.updatedAt ?? current.completedAt;
    if (candidateTimestamp == null) {
      return false;
    }
    if (currentTimestamp == null) {
      return true;
    }
    return candidateTimestamp.isAfter(currentTimestamp);
  }

  int _activeJobStatusPriority(String status) {
    return switch (status) {
      'running' => 2,
      'pending' => 1,
      _ => 0,
    };
  }

  String _defaultAgentLabel(AgentId agentId) {
    return switch (agentId) {
      AgentId.generator => 'Generator',
      AgentId.reviewer => 'Reviewer',
      AgentId.summary => 'Summary',
      AgentId.supervisor => 'Supervisor',
      AgentId.qa => 'QA',
      AgentId.ux => 'UX',
      AgentId.seniorEngineer => 'Senior Engineer',
      AgentId.scraper => 'Scraper',
      AgentId.user => 'User',
    };
  }

  String _formatActionError(String prefix, Object error) {
    final detail = '$error'.trim().replaceFirst(RegExp(r'^Exception:\s*'), '');
    final normalizedPrefix = prefix.trim().replaceFirst(
          RegExp(r'[.:!?]+$'),
          '',
        );
    if (detail.isEmpty) {
      return prefix;
    }
    if (detail.startsWith(prefix)) {
      return detail;
    }
    if (detail.startsWith('$normalizedPrefix: ')) {
      return '$prefix\n${detail.substring(normalizedPrefix.length + 2)}';
    }
    return '$prefix\n$detail';
  }
}

CurrentRunExecution? _applySnapshotToRun(
  CurrentRunExecution? currentRun,
  JobStatusResponse snapshot,
) {
  if (currentRun == null) {
    return null;
  }

  var didUpdate = false;
  final stages = currentRun.stages.map((stage) {
    if (stage.jobId != snapshot.jobId) {
      return stage;
    }
    didUpdate = true;
    return stage.copyWith(
      state: _stageStateFromJobStatus(snapshot.status),
      jobStatus: snapshot.status,
      latestActivity: snapshot.latestActivity,
      updatedAt: snapshot.updatedAt ?? stage.updatedAt,
      completedAt: snapshot.completedAt ?? stage.completedAt,
    );
  }).toList(growable: false);

  if (!didUpdate) {
    return currentRun;
  }

  final latestTimestamp = snapshot.completedAt ?? snapshot.updatedAt;
  return currentRun.copyWith(
    state: _deriveRunStateFromStages(stages, currentRun.isActive),
    updatedAt: latestTimestamp ?? currentRun.updatedAt,
    completedAt: snapshot.completedAt ?? currentRun.completedAt,
    stages: stages,
  );
}

List<CurrentRunExecution> _applySnapshotToRuns(
  List<CurrentRunExecution> runs,
  JobStatusResponse snapshot,
) {
  if (runs.isEmpty) {
    return runs;
  }

  var didUpdate = false;
  final updatedRuns = runs.map((run) {
    final updatedRun = _applySnapshotToRun(run, snapshot);
    if (!identical(updatedRun, run)) {
      didUpdate = true;
    }
    return updatedRun!;
  }).toList(growable: false);
  return didUpdate ? updatedRuns : runs;
}

ChatMessageStatus _statusFromJob(String status) {
  switch (status) {
    case 'cancelled':
      return ChatMessageStatus.cancelled;
    case 'failed':
      return ChatMessageStatus.failed;
    case 'completed':
      return ChatMessageStatus.completed;
    default:
      return ChatMessageStatus.pending;
  }
}

CurrentRunStageState _stageStateFromJobStatus(String status) {
  switch (status) {
    case 'running':
      return CurrentRunStageState.running;
    case 'completed':
      return CurrentRunStageState.completed;
    case 'failed':
      return CurrentRunStageState.failed;
    case 'cancelled':
      return CurrentRunStageState.cancelled;
    default:
      return CurrentRunStageState.queued;
  }
}

CurrentRunStageState _deriveRunStateFromStages(
  List<CurrentRunStageExecution> stages,
  bool isActive,
) {
  final states = stages.map((stage) => stage.state).toSet();
  if (states.contains(CurrentRunStageState.running)) {
    return CurrentRunStageState.running;
  }
  if (states.contains(CurrentRunStageState.queued)) {
    return CurrentRunStageState.queued;
  }
  if (states.contains(CurrentRunStageState.failed)) {
    return CurrentRunStageState.failed;
  }
  if (states.contains(CurrentRunStageState.cancelled)) {
    return CurrentRunStageState.cancelled;
  }
  if (states.contains(CurrentRunStageState.stale)) {
    return CurrentRunStageState.stale;
  }
  if (isActive) {
    if (states.contains(CurrentRunStageState.notScheduled)) {
      return CurrentRunStageState.notScheduled;
    }
    if (states.contains(CurrentRunStageState.waiting)) {
      return CurrentRunStageState.waiting;
    }
  }
  if (states.contains(CurrentRunStageState.completed)) {
    return CurrentRunStageState.completed;
  }
  return CurrentRunStageState.skipped;
}

class SessionActiveJobSummary {
  const SessionActiveJobSummary({
    required this.activeJobCount,
    required this.maxElapsedSeconds,
    required this.primaryAgentId,
    required this.primaryAgentLabel,
    required this.primaryAgentSeed,
  });

  final int activeJobCount;
  final int maxElapsedSeconds;
  final AgentId primaryAgentId;
  final String primaryAgentLabel;
  final String primaryAgentSeed;
}

enum OutgoingUploadKind { audio, image, file, mixed }

class SessionOutgoingUploadSummary {
  const SessionOutgoingUploadSummary({
    required this.audioCount,
    required this.imageCount,
    required this.fileCount,
    required this.mixedCount,
  });

  final int audioCount;
  final int imageCount;
  final int fileCount;
  final int mixedCount;

  int get totalCount => audioCount + imageCount + fileCount + mixedCount;
}

class _OutgoingUploadTicket {
  const _OutgoingUploadTicket({required this.sessionId, required this.kind});

  final String sessionId;
  final OutgoingUploadKind kind;
}

class _OptimisticAudioMessage {
  const _OptimisticAudioMessage({
    required this.sessionId,
    required this.message,
  });

  final String sessionId;
  final ChatMessage message;
}

class _DeferredRunNotification {
  const _DeferredRunNotification({required this.runId, required this.snapshot});

  final String runId;
  final JobStatusResponse snapshot;
}
