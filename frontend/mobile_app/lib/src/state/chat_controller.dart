import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/chat_message.dart';
import '../models/chat_session_summary.dart';
import '../models/job_status_response.dart';
import '../models/session_detail.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';

class ChatController extends ChangeNotifier {
  ChatController({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;
  final List<ChatSessionSummary> _sessions = <ChatSessionSummary>[];
  final List<Workspace> _workspaces = <Workspace>[];
  final Map<String, String> _pendingJobs = <String, String>{};
  final Map<String, int> _pollFailures = <String, int>{};
  final Map<String, JobStatusResponse> _jobSnapshots = <String, JobStatusResponse>{};
  final Map<String, WebSocketChannel> _jobChannels = <String, WebSocketChannel>{};

  SessionDetail? _currentSession;
  String? _selectedSessionId;
  String? _errorText;
  bool _isLoading = false;
  bool _isSendingAudio = false;
  bool _pollInFlight = false;
  Timer? _pollTimer;

  List<ChatSessionSummary> get sessions => List<ChatSessionSummary>.unmodifiable(_sessions);
  List<Workspace> get workspaces => List<Workspace>.unmodifiable(_workspaces);
  SessionDetail? get currentSession => _currentSession;
  String? get selectedSessionId => _selectedSessionId;
  String? get errorText => _errorText;
  bool get isLoading => _isLoading;
  bool get isSendingAudio => _isSendingAudio;
  bool get hasSessions => _sessions.isNotEmpty;
  List<ChatMessage> get messages => _currentSession?.messages ?? const <ChatMessage>[];

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
      final session = await _apiClient.createSession(workspacePath: workspacePath);
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

  Future<void> sendMessage(String rawText) async {
    final text = rawText.trim();
    if (text.isEmpty) {
      return;
    }

    try {
      _errorText = null;
      final accepted = await _apiClient.sendMessage(
        text,
        sessionId: _selectedSessionId,
        workspacePath: _currentSession?.workspacePath,
      );
      _selectedSessionId = accepted.sessionId;
      _pendingJobs[accepted.jobId] = accepted.sessionId;
      _jobSnapshots[accepted.jobId] = accepted;
      await refreshSessions();
      await _reloadCurrentSession();
      _ensureJobStream(accepted.jobId);
      _ensurePolling();
    } catch (error) {
      _errorText = 'Failed to send message.\n$error';
      notifyListeners();
    }
  }

  Future<void> sendAudioMessage(
    String audioPath, {
    String? language,
  }) async {
    _isSendingAudio = true;
    notifyListeners();

    try {
      _errorText = null;
      final accepted = await _apiClient.sendAudioMessage(
        audioPath,
        sessionId: _selectedSessionId,
        workspacePath: _currentSession?.workspacePath,
        language: language,
      );
      _selectedSessionId = accepted.sessionId;
      _pendingJobs[accepted.jobId] = accepted.sessionId;
      _jobSnapshots[accepted.jobId] = accepted;
      await refreshSessions();
      await _reloadCurrentSession();
      _ensureJobStream(accepted.jobId);
      _ensurePolling();
    } catch (error) {
      _errorText = 'Failed to send audio message.\n$error';
      notifyListeners();
    } finally {
      _isSendingAudio = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    for (final channel in _jobChannels.values) {
      channel.sink.close();
    }
    _jobChannels.clear();
    super.dispose();
  }

  void _ensurePolling() {
    _pollTimer ??= Timer.periodic(const Duration(seconds: 2), (_) => _pollJobs());
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
          if (errorText.contains('404') || errorText.contains('Job not found')) {
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

  void _reconcilePendingJobsForSession(SessionDetail? session) {
    if (session == null) {
      return;
    }

    final activePendingJobIds = session.messages
        .where((message) {
          final jobStatus = message.jobStatus ?? '';
          return message.jobId != null &&
              (message.isPendingLike || jobStatus == 'pending' || jobStatus == 'running');
        })
        .map((message) => message.jobId!)
        .toSet();

    final staleJobIds = _pendingJobs.entries
        .where((entry) => entry.value == session.id && !activePendingJobIds.contains(entry.key))
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
      final isPending = message.isPendingLike || jobStatus == 'pending' || jobStatus == 'running';
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

  ChatMessage _applySnapshotToMessage(ChatMessage message, JobStatusResponse snapshot) {
    if (message.jobId != snapshot.jobId) {
      return message;
    }

    return message.copyWith(
      text: snapshot.isTerminal
          ? (snapshot.status == 'failed'
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
    final messages = session.messages
        .map((message) {
          if (message.jobId == null) {
            return message;
          }
          final snapshot = _jobSnapshots[message.jobId!];
          if (snapshot == null) {
            return message;
          }
          return _applySnapshotToMessage(message, snapshot);
        })
        .toList(growable: false);

    return session.copyWith(messages: messages);
  }

  void _finishTrackingJob(String jobId) {
    _pendingJobs.remove(jobId);
    _pollFailures.remove(jobId);
    _jobChannels.remove(jobId)?.sink.close();
  }

  void _setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }
}

ChatMessageStatus _statusFromJob(String status) {
  switch (status) {
    case 'failed':
      return ChatMessageStatus.failed;
    case 'completed':
      return ChatMessageStatus.completed;
    default:
      return ChatMessageStatus.pending;
  }
}
