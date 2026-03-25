import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('active job summary keeps the running reviewer label and elapsed time',
      () async {
    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.review,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.reviewer) {
          return agent.copyWith(
            enabled: true,
            label: 'Safety Reviewer',
          );
        }
        return agent;
      }).toList(growable: false),
    );

    final controller = ChatController(
      apiClient: _ActiveJobSummaryApiClient(
        configuration: configuration,
        messages: <ChatMessage>[
          _pendingMessage(
            id: 'reviewer-pending',
            agentId: AgentId.reviewer,
            agentType: AgentType.reviewer,
            agentLabel: 'Safety Reviewer',
            jobId: 'job-reviewer-1',
            elapsedSeconds: 83,
          ),
        ],
      ),
    );

    await controller.selectSession('session-a');

    final summary = controller.activeJobSummaryForSession('session-a');
    expect(summary, isNotNull);
    expect(summary!.activeJobCount, 1);
    expect(summary.maxElapsedSeconds, 83);
    expect(summary.primaryAgentId, AgentId.reviewer);
    expect(summary.primaryAgentLabel, 'Safety Reviewer');
    expect(summary.primaryAgentSeed, 'reviewer');

    controller.dispose();
  });

  test('active job summary resolves specialist labels from configuration',
      () async {
    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.supervisor,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.supervisor) {
          return agent.copyWith(enabled: true);
        }
        if (agent.agentId == AgentId.qa) {
          return agent.copyWith(
            enabled: true,
            label: 'Release QA',
          );
        }
        return agent;
      }).toList(growable: false),
    );

    final controller = ChatController(
      apiClient: _ActiveJobSummaryApiClient(
        configuration: configuration,
        messages: <ChatMessage>[
          _pendingMessage(
            id: 'generator-pending',
            agentId: AgentId.generator,
            agentType: AgentType.generator,
            jobId: 'job-generator-1',
            elapsedSeconds: 12,
            jobStatus: 'pending',
          ),
          _pendingMessage(
            id: 'qa-running',
            agentId: AgentId.qa,
            agentType: AgentType.qa,
            jobId: 'job-qa-1',
            elapsedSeconds: 15,
            jobStatus: 'running',
          ),
        ],
      ),
    );

    await controller.selectSession('session-a');

    final summary = controller.activeJobSummaryForSession('session-a');
    expect(summary, isNotNull);
    expect(summary!.activeJobCount, 2);
    expect(summary.maxElapsedSeconds, 15);
    expect(summary.primaryAgentId, AgentId.qa);
    expect(summary.primaryAgentLabel, 'Release QA');
    expect(summary.primaryAgentSeed, 'qa');

    controller.dispose();
  });
}

class _ActiveJobSummaryApiClient extends ApiClient {
  _ActiveJobSummaryApiClient({
    required this.configuration,
    required this.messages,
  }) : super(baseUrl: 'http://localhost:8000');

  final AgentConfiguration configuration;
  final List<ChatMessage> messages;
  static final DateTime _timestamp = DateTime.utc(2026, 1, 1, 12);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentConfiguration: configuration,
        createdAt: _timestamp,
        updatedAt: _timestamp,
        activeAgentRunId: 'run-1',
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
      agentConfiguration: configuration,
      activeAgentRunId: 'run-1',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: messages,
    );
  }
}

ChatMessage _pendingMessage({
  required String id,
  required AgentId agentId,
  required AgentType agentType,
  required String jobId,
  required int elapsedSeconds,
  String? agentLabel,
  String jobStatus = 'running',
}) {
  final timestamp = DateTime.utc(2026, 1, 1, 12);
  return ChatMessage(
    id: id,
    text: '',
    isUser: false,
    authorType: ChatMessageAuthorType.assistant,
    agentId: agentId,
    agentType: agentType,
    agentLabel: agentLabel,
    status: ChatMessageStatus.pending,
    createdAt: timestamp,
    updatedAt: timestamp,
    runId: 'run-1',
    jobId: jobId,
    jobStatus: jobStatus,
    jobElapsedSeconds: elapsedSeconds,
  );
}
