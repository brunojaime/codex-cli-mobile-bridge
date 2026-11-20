import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the running job (not the queued one) is the steering target', () async {
    final api = _SteeringApiClient(steerAccepted: true);
    final controller = ChatController(apiClient: api);
    await controller.selectSession('session-a');

    expect(controller.runningJobIdForSession('session-a'), 'job-running');
    expect(controller.runningJobIdForSession('other'), isNull);
    controller.dispose();
  });

  test('accepted steering loads the persisted instruction once, no new turn',
      () async {
    final api = _SteeringApiClient(steerAccepted: true);
    final controller = ChatController(apiClient: api);
    await controller.selectSession('session-a');

    final ok = await controller.steerJob('job-running', 'usá SQLite',
        sessionId: 'session-a');

    expect(ok, isTrue);
    expect(api.steered, <String>['job-running:usá SQLite']);
    expect(api.submittedMessages, isEmpty);
    expect(api.cancelledJobs, isEmpty);
    final steered = controller.currentSession!.messages
        .where((m) => m.reasonCode == ChatMessageReasonCode.steeredIntoRunningTurn)
        .toList();
    expect(steered.map((m) => m.text), <String>['usá SQLite']);
    controller.dispose();
  });

  test('refused steering reports false and never cancels the run', () async {
    final api = _SteeringApiClient(steerAccepted: false);
    final controller = ChatController(apiClient: api);
    await controller.selectSession('session-a');

    expect(await controller.steerJob('job-running', 'hola'), isFalse);
    expect(api.cancelledJobs, isEmpty);
    controller.dispose();
  });

  test('steered reason code is parsed from the backend', () {
    final message = ChatMessage.fromJson(<String, dynamic>{
      'id': 'm1',
      'role': 'user',
      'author_type': 'human',
      'content': 'x',
      'status': 'completed',
      'created_at': '2026-01-01T12:00:00Z',
      'updated_at': '2026-01-01T12:00:00Z',
      'reason_code': 'steered_into_running_turn',
    });
    expect(message.reasonCode, ChatMessageReasonCode.steeredIntoRunningTurn);
  });
}

class _SteeringApiClient extends ApiClient {
  _SteeringApiClient({required this.steerAccepted})
      : super(baseUrl: 'http://localhost:8000');

  final bool steerAccepted;
  final List<String> steered = <String>[];
  final List<String> submittedMessages = <String>[];
  final List<String> cancelledJobs = <String>[];
  static final DateTime _timestamp = DateTime.utc(2026, 1, 1, 12);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentConfiguration: kDefaultAgentConfiguration,
        createdAt: _timestamp,
        updatedAt: _timestamp,
        activeAgentRunId: 'run-1',
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'Workspace A',
      agentConfiguration: kDefaultAgentConfiguration,
      activeAgentRunId: 'run-1',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        _assistant('a-running', 'job-running', 'running'),
        _assistant('a-queued', 'job-queued', 'pending'),
        for (final entry in steered)
          ChatMessage(
            id: 'steer-${entry.hashCode}',
            text: entry.split(':').last,
            isUser: true,
            authorType: ChatMessageAuthorType.human,
            status: ChatMessageStatus.completed,
            createdAt: _timestamp,
            updatedAt: _timestamp,
            runId: 'run-1',
            reasonCode: ChatMessageReasonCode.steeredIntoRunningTurn,
          ),
      ],
    );
  }

  @override
  Future<bool> steerJob(String jobId, String message) async {
    if (!steerAccepted) return false;
    steered.add('$jobId:$message');
    return true;
  }

  @override
  Future<JobStatusResponse> cancelJob(String jobId) async {
    cancelledJobs.add(jobId);
    throw UnimplementedError();
  }
}

ChatMessage _assistant(String id, String jobId, String jobStatus) {
  final timestamp = DateTime.utc(2026, 1, 1, 12);
  return ChatMessage(
    id: id,
    text: '',
    isUser: false,
    authorType: ChatMessageAuthorType.assistant,
    agentId: AgentId.generator,
    agentType: AgentType.generator,
    status: ChatMessageStatus.pending,
    createdAt: timestamp,
    updatedAt: timestamp,
    runId: 'run-1',
    jobId: jobId,
    jobStatus: jobStatus,
    jobElapsedSeconds: 5,
  );
}
