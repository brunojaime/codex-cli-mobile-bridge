import 'package:codex_mobile_frontend/src/models/agent_activity.dart';
import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('legacy activity observations survive completion and transcript refresh',
      () async {
    final controller = ChatController(apiClient: _StreamingResponseApiClient());
    await controller.selectSession('session-a');
    for (final title in ['Leyendo archivos', 'Ejecutando pruebas']) {
      controller.applyJobSnapshotForTesting(JobStatusResponse(
        jobId: 'job-generator-1',
        sessionId: 'session-a',
        status: 'running',
        elapsedSeconds: 1,
        latestActivity: title,
      ));
    }
    await controller.selectSession('session-a');
    final message =
        controller.currentSession!.messages.singleWhere((item) => !item.isUser);
    expect(message.activities.map((item) => item.title),
        ['Leyendo archivos', 'Ejecutando pruebas']);
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
      jobId: 'job-generator-1',
      sessionId: 'session-a',
      status: 'completed',
      elapsedSeconds: 2,
      response: 'Listo',
    ));
    await controller.selectSession('session-a');
    expect(
        controller.currentSession!.messages
            .singleWhere((item) => !item.isUser)
            .activities
            .length,
        2);
    controller.dispose();
  });

  test('running job snapshots surface partial assistant text immediately',
      () async {
    final controller = ChatController(
      apiClient: _StreamingResponseApiClient(),
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      JobStatusResponse(
        jobId: 'job-generator-1',
        sessionId: 'session-a',
        status: 'running',
        updatedAt: _StreamingResponseApiClient._timestamp
            .add(const Duration(seconds: 1)),
        elapsedSeconds: 1,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        response: 'Streaming draft text',
        activities: [
          AgentActivity(
              id: 'cmd',
              kind: 'tool',
              title: 'Comando',
              detail: 'pytest',
              status: 'running')
        ],
        latestActivity: 'Codex is composing the reply.',
      ),
    );

    final session = controller.currentSession;
    expect(session, isNotNull);
    expect(session!.messages.last.text, 'Streaming draft text');
    expect(session.messages.last.jobStatus, 'running');
    expect(session.messages.singleWhere((message) => message.isUser).text,
        'Need help');
    expect(session.messages.last.activities.single.detail, 'pytest');
    // A refreshed transcript must retain the newer streamed activity snapshot.
    await controller.selectSession('session-a');
    expect(
        controller.currentSession!.messages
            .singleWhere((message) => !message.isUser)
            .activities
            .single
            .id,
        'cmd');

    controller.applyJobSnapshotForTesting(JobStatusResponse(
      jobId: 'job-generator-1',
      sessionId: 'session-a',
      status: 'running',
      elapsedSeconds: 0,
      updatedAt: DateTime.utc(2025, 1, 1),
    ));
    expect(
        controller.currentSession!.messages
            .singleWhere((message) => !message.isUser)
            .activities
            .single
            .id,
        'cmd');
    await controller.selectSession('session-a');
    expect(
        controller.currentSession!.messages
            .singleWhere((message) => !message.isUser)
            .activities
            .single
            .id,
        'cmd');
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
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'user-1',
          text: 'Need help',
          jobId: 'job-generator-1',
          jobStatus: 'running',
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
