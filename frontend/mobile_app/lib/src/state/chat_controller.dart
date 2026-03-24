import 'dart:async';
import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/chat_message.dart';
import '../models/chat_session_summary.dart';
import '../models/job_status_response.dart';
import '../models/session_detail.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
import '../services/chat_notification_service.dart';

class ChatController extends ChangeNotifier {
  ChatController({
    required ApiClient apiClient,
    ChatNotificationService notificationService =
        const NoopChatNotificationService(),
  })  : _apiClient = apiClient,
        _notificationService = notificationService;

  final ApiClient _apiClient;
  final ChatNotificationService _notificationService;
  final List<ChatSessionSummary> _sessions = <ChatSessionSummary>[];
  final List<Workspace> _workspaces = <Workspace>[];
  final Map<String, String> _pendingJobs = <String, String>{};
  final Map<String, int> _pollFailures = <String, int>{};
  final Map<String, JobStatusResponse> _jobSnapshots =
      <String, JobStatusResponse>{};
  final Map<String, WebSocketChannel> _jobChannels =
      <String, WebSocketChannel>{};
  final Map<int, _OutgoingUploadTicket> _outgoingUploads =
      <int, _OutgoingUploadTicket>{};
  final Set<String> _notifiedTerminalJobs = <String>{};

  SessionDetail? _currentSession;
  String? _selectedSessionId;
  String? _errorText;
  bool _isLoading = false;
  int _sendingAudioCount = 0;
  int _sendingDocumentCount = 0;
  int _sendingImageCount = 0;
  int _nextOutgoingUploadToken = 0;
  bool _pollInFlight = false;
  Timer? _pollTimer;

  List<ChatSessionSummary> get sessions =>
      List<ChatSessionSummary>.unmodifiable(_sessions);
  List<Workspace> get workspaces => List<Workspace>.unmodifiable(_workspaces);
  SessionDetail? get currentSession => _currentSession;
  String? get selectedSessionId => _selectedSessionId;
  String? get errorText => _errorText;
  bool get isLoading => _isLoading;
  bool get isSendingAudio => _sendingAudioCount > 0;
  bool get isSendingDocument => _sendingDocumentCount > 0;
  bool get isSendingImage => _sendingImageCount > 0;
  bool get hasSessions => _sessions.isNotEmpty;
  List<ChatMessage> get messages =>
      _currentSession?.messages ?? const <ChatMessage>[];

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
    for (final jobId in jobIds) {
      final elapsedSeconds = _jobSnapshots[jobId]?.elapsedSeconds ?? 0;
      if (elapsedSeconds > maxElapsedSeconds) {
        maxElapsedSeconds = elapsedSeconds;
      }
    }

    return SessionActiveJobSummary(
      activeJobCount: jobIds.length,
      maxElapsedSeconds: maxElapsedSeconds,
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
    try {
      await refreshSessions();
      await refreshWorkspaces();
      if (_sessions.isNotEmpty) {
        await selectSession(_sessions.first.id);
      } else {
        _errorText = null;
        notifyListeners();
      }
    } catch (error) {
      _errorText = '$error';
      notifyListeners();
    }
  }

  Future<void> refreshSessions() async {
    final sessions = await _apiClient.listSessions();
    _sessions
      ..clear()
      ..addAll(sessions);
    _errorText = null;
    notifyListeners();
  }

  Future<void> refreshWorkspaces() async {
    final workspaces = await _apiClient.listWorkspaces();
    _workspaces
      ..clear()
      ..addAll(workspaces);
    _errorText = null;
    notifyListeners();
  }

  Future<void> handleAppResumed() async {
    try {
      await refreshSessions();
      if (_selectedSessionId != null) {
        await _reloadCurrentSession();
      } else if (_sessions.isNotEmpty) {
        await selectSession(_sessions.first.id);
      }

      for (final jobId in _pendingJobs.keys.toList()) {
        _ensureJobStream(jobId);
      }
      if (_pendingJobs.isNotEmpty) {
        _ensurePolling();
      }
    } catch (error) {
      _errorText = 'Failed to reconnect to the backend.\n$error';
      notifyListeners();
    }
  }

  Future<void> createNewSession({String? workspacePath}) async {
    _setLoading(true);
    try {
      final session =
          await _apiClient.createSession(workspacePath: workspacePath);
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
      final session = await _apiClient.getSession(sessionId);
      _currentSession = _overlaySessionWithJobSnapshots(session);
      _selectedSessionId = sessionId;
      _reconcilePendingJobsForSession(_currentSession);
      _trackPendingJobsFromSession(_currentSession);
      _errorText = null;
      notifyListeners();
    } catch (error) {
      _errorText = '$error';
      notifyListeners();
    } finally {
      _setLoading(false);
    }
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
      final session = await _apiClient.updateAutoMode(
        sessionId,
        enabled: enabled,
        maxTurns: maxTurns,
        reviewerPrompt: reviewerPrompt,
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

  Future<bool> sendMessage(
    String rawText, {
    String? sessionIdOverride,
    String? workspacePathOverride,
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
      );
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId,
      );
      return true;
    } catch (error) {
      _errorText = 'Failed to send message.\n$error';
      notifyListeners();
      return false;
    }
  }

  Future<bool> sendAudioMessage(
    XFile audioFile, {
    String? language,
    String? sessionIdOverride,
    String? workspacePathOverride,
  }) async {
    final originSessionId = sessionIdOverride ?? _selectedSessionId;
    final originWorkspacePath =
        workspacePathOverride ?? _currentSession?.workspacePath;
    final outgoingUploadToken = _beginOutgoingUpload(
      originSessionId,
      OutgoingUploadKind.audio,
    );
    _sendingAudioCount += 1;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendAudioMessage(
        audioFile,
        sessionId: originSessionId,
        workspacePath: originWorkspacePath,
        language: language,
      );
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId,
      );
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
      );
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId,
      );
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
      );
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId,
      );
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
      );
      await _registerAcceptedJob(
        accepted,
        originSessionId: originSessionId,
      );
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
    _pollTimer ??=
        Timer.periodic(const Duration(seconds: 2), (_) => _pollJobs());
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

    final session = await _apiClient.getSession(_selectedSessionId!);
    _currentSession = _overlaySessionWithJobSnapshots(session);
    _reconcilePendingJobsForSession(_currentSession);
    _trackPendingJobsFromSession(_currentSession);
    _errorText = null;
    notifyListeners();
  }

  Future<void> _registerAcceptedJob(
    JobStatusResponse accepted, {
    required String? originSessionId,
  }) async {
    final shouldKeepOriginSessionSelected =
        _selectedSessionId == null || _selectedSessionId == originSessionId;

    _pendingJobs[accepted.jobId] = accepted.sessionId;
    _jobSnapshots[accepted.jobId] = accepted;
    _notifiedTerminalJobs.remove(accepted.jobId);
    _ensureJobStream(accepted.jobId);
    _ensurePolling();

    await refreshSessions();

    if (shouldKeepOriginSessionSelected ||
        _selectedSessionId == accepted.sessionId) {
      _selectedSessionId = accepted.sessionId;
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
        .where((entry) =>
            entry.value == session.id &&
            !activePendingJobIds.contains(entry.key))
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
        providerSessionId: message.providerSessionId,
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

    _currentSession = _currentSession!.copyWith(messages: updatedMessages);
    notifyListeners();
  }

  ChatMessage _applySnapshotToMessage(
      ChatMessage message, JobStatusResponse snapshot) {
    if (message.jobId != snapshot.jobId) {
      return message;
    }

    return message.copyWith(
      text: snapshot.isTerminal
          ? (snapshot.status == 'failed' || snapshot.status == 'cancelled'
              ? (snapshot.error ?? message.text)
              : (snapshot.response ?? message.text))
          : message.text,
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

    return session.copyWith(messages: messages);
  }

  void _finishTrackingJob(String jobId) {
    _pendingJobs.remove(jobId);
    _pollFailures.remove(jobId);
    _jobChannels.remove(jobId)?.sink.close();
  }

  void _maybeNotifyForTerminalJob(JobStatusResponse snapshot) {
    if (!snapshot.isTerminal || snapshot.status == 'cancelled') {
      return;
    }
    if (_notifiedTerminalJobs.contains(snapshot.jobId)) {
      return;
    }

    final notification = _buildTerminalNotification(snapshot);
    if (notification == null) {
      return;
    }

    _notifiedTerminalJobs.add(snapshot.jobId);
    unawaited(_notificationService.showChatCompleted(notification));
  }

  ChatCompletedNotification? _buildTerminalNotification(
    JobStatusResponse snapshot,
  ) {
    final session = _sessionDetailForId(snapshot.sessionId);
    final sessionTitle = _resolveSessionTitle(snapshot.sessionId, session);
    final workspaceName = _resolveWorkspaceName(snapshot.sessionId, session);
    final preview = _buildNotificationPreview(snapshot);
    if (preview == null) {
      return null;
    }

    final statusLine =
        snapshot.status == 'failed' ? 'Chat failed' : 'Reply ready';
    final body = StringBuffer(statusLine);
    if (sessionTitle.isNotEmpty) {
      body.write('\n$sessionTitle');
    }
    body.write('\n$preview');

    return ChatCompletedNotification(
      id: snapshot.jobId.hashCode,
      title: workspaceName,
      body: body.toString(),
      summary: sessionTitle,
    );
  }

  SessionDetail? _sessionDetailForId(String sessionId) {
    final currentSession = _currentSession;
    if (currentSession != null && currentSession.id == sessionId) {
      return currentSession;
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

  String? _buildNotificationPreview(JobStatusResponse snapshot) {
    final rawPreview = switch (snapshot.status) {
      'failed' => snapshot.error,
      _ => snapshot.response ?? snapshot.latestActivity,
    };
    if (rawPreview == null) {
      return null;
    }

    final normalized = rawPreview.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (normalized.isEmpty) {
      return null;
    }
    if (normalized.length <= 220) {
      return normalized;
    }
    return '${normalized.substring(0, 217)}...';
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

  void _finishOutgoingUpload(int? token) {
    if (token == null) {
      return;
    }
    _outgoingUploads.remove(token);
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
      workspacePath: session.workspacePath,
      workspaceName: session.workspaceName,
      providerSessionId: session.providerSessionId,
      reviewerProviderSessionId: session.reviewerProviderSessionId,
      autoModeEnabled: session.autoModeEnabled,
      autoMaxTurns: session.autoMaxTurns,
      autoReviewerPrompt: session.autoReviewerPrompt,
      autoTurnIndex: session.autoTurnIndex,
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

class SessionActiveJobSummary {
  const SessionActiveJobSummary({
    required this.activeJobCount,
    required this.maxElapsedSeconds,
  });

  final int activeJobCount;
  final int maxElapsedSeconds;
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
  const _OutgoingUploadTicket({
    required this.sessionId,
    required this.kind,
  });

  final String sessionId;
  final OutgoingUploadKind kind;
}
