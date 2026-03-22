import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/chat_message.dart';
import '../models/chat_session_summary.dart';
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

  SessionDetail? _currentSession;
  String? _selectedSessionId;
  String? _errorText;
  bool _isLoading = false;
  bool _pollInFlight = false;
  Timer? _pollTimer;

  List<ChatSessionSummary> get sessions => List<ChatSessionSummary>.unmodifiable(_sessions);
  List<Workspace> get workspaces => List<Workspace>.unmodifiable(_workspaces);
  SessionDetail? get currentSession => _currentSession;
  String? get selectedSessionId => _selectedSessionId;
  String? get errorText => _errorText;
  bool get isLoading => _isLoading;
  bool get hasSessions => _sessions.isNotEmpty;
  List<ChatMessage> get messages => _currentSession?.messages ?? const <ChatMessage>[];

  Future<void> initialize() async {
    try {
      await refreshSessions();
      await refreshWorkspaces();
      if (_sessions.isNotEmpty) {
        await selectSession(_sessions.first.id);
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
    notifyListeners();
  }

  Future<void> refreshWorkspaces() async {
    final workspaces = await _apiClient.listWorkspaces();
    _workspaces
      ..clear()
      ..addAll(workspaces);
    notifyListeners();
  }

  Future<void> createNewSession({String? workspacePath}) async {
    _setLoading(true);
    try {
      final session = await _apiClient.createSession(workspacePath: workspacePath);
      _errorText = null;
      await refreshSessions();
      _selectedSessionId = session.id;
      _currentSession = session;
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
      _currentSession = await _apiClient.getSession(sessionId);
      _selectedSessionId = sessionId;
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
      await refreshSessions();
      await _reloadCurrentSession();
      _ensurePolling();
    } catch (error) {
      _errorText = 'Failed to send message.\n$error';
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
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

      for (final entry in _pendingJobs.entries) {
        try {
          final result = await _apiClient.getJob(entry.key);
          _pollFailures.remove(entry.key);
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
          if (failures >= 3) {
            completedJobs.add(entry.key);
            _errorText = 'Failed to poll backend after $failures attempts.\n$error';
          }
        }
      }

      for (final jobId in completedJobs) {
        _pendingJobs.remove(jobId);
        _pollFailures.remove(jobId);
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

    _currentSession = await _apiClient.getSession(_selectedSessionId!);
    notifyListeners();
  }

  void _setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }
}
