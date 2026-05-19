import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('running job snapshots surface partial assistant text immediately',
      () async {
    final controller = ChatController(
      apiClient: _StreamingResponseApiClient(),
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-generator-1',
        sessionId: 'session-a',
        status: 'running',
        elapsedSeconds: 1,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        response: 'Streaming draft text',
        latestActivity: 'Codex is composing the reply.',
      ),
    );

    final session = controller.currentSession;
    expect(session, isNotNull);
    expect(session!.messages.last.text, 'Streaming draft text');
    expect(session.messages.last.jobStatus, 'running');

    controller.dispose();
  });
}

class _StreamingResponseApiClient extends ApiClient {
  _StreamingResponseApiClient() : super(baseUrl: 'http://localhost:8000');

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
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'Workspace A',
      agentConfiguration: kDefaultAgentConfiguration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'user-1',
          text: 'Need help',
          isUser: true,
          authorType: ChatMessageAuthorType.human,
          agentId: AgentId.user,
          agentType: AgentType.human,
          status: ChatMessageStatus.completed,
          createdAt: _timestamp,
          updatedAt: _timestamp,
        ),
        ChatMessage(
          id: 'assistant-1',
          text: '',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          agentId: AgentId.generator,
          agentType: AgentType.generator,
          status: ChatMessageStatus.pending,
          createdAt: _timestamp,
          updatedAt: _timestamp,
          jobId: 'job-generator-1',
          jobStatus: 'running',
        ),
      ],
    );
  }
}
