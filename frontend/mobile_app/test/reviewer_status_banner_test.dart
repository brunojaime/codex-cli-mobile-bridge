import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/reviewer_lifecycle_state.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/utils/chat_message_visibility.dart';
import 'package:codex_mobile_frontend/src/widgets/reviewer_status_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('reviewer status presentation covers inactive states', () {
    final offPresentation = reviewerStatusPresentation(
      _buildSession(reviewerState: ReviewerLifecycleState.off),
    );
    final disabledPresentation = reviewerStatusPresentation(
      _buildSession(reviewerState: ReviewerLifecycleState.disabled),
    );

    expect(offPresentation.title, 'Safety Reviewer inactive');
    expect(offPresentation.subtitle, 'Auto mode is off for this chat.');
    expect(disabledPresentation.title, 'Safety Reviewer disabled');
    expect(
      disabledPresentation.subtitle,
      'Auto mode is on, but reviewer turns are disabled.',
    );
  });

  test('reviewer status presentation maps lifecycle state and label', () {
    final presentation = reviewerStatusPresentation(
      _buildSession(
        reviewerState: ReviewerLifecycleState.waitingOnGenerator,
      ),
    );

    expect(presentation.title, 'Safety Reviewer waiting on generator');
    expect(
      presentation.subtitle,
      'The generator has not finished the current run yet.',
    );
    expect(presentation.icon, Icons.hourglass_bottom_rounded);
  });

  testWidgets('reviewer status banner renders visible state copy',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReviewerStatusBanner(
            session: _buildSession(
              reviewerState: ReviewerLifecycleState.running,
            ),
          ),
        ),
      ),
    );

    expect(find.text('Safety Reviewer running'), findsOneWidget);
    expect(
      find.text('The reviewer is actively working on this run.'),
      findsOneWidget,
    );
  });

  testWidgets(
      'collapsed reviewer messages do not hide reviewer status for the active run',
      (WidgetTester tester) async {
    final session = _buildSession(
      reviewerState: ReviewerLifecycleState.completed,
      displayMode: AgentDisplayMode.collapseSpecialists,
      messages: <ChatMessage>[
        _buildMessage(
          id: 'human-message',
          authorType: ChatMessageAuthorType.human,
          agentId: AgentId.user,
          agentType: AgentType.human,
          isUser: true,
        ),
        _buildMessage(id: 'generator-message'),
        _buildMessage(
          id: 'reviewer-message',
          agentId: AgentId.reviewer,
          agentType: AgentType.reviewer,
          authorType: ChatMessageAuthorType.reviewerCodex,
          isUser: true,
          visibility: AgentVisibilityMode.collapsed,
        ),
      ],
    );
    final visibleMessages = filterVisibleMessages(
      session.messages,
      displayMode: session.agentConfiguration.displayMode,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              ReviewerStatusBanner(session: session),
              for (final message in visibleMessages) Text(message.id),
            ],
          ),
        ),
      ),
    );

    expect(find.text('Safety Reviewer completed'), findsOneWidget);
    expect(
      find.text('The reviewer has already acted on this run.'),
      findsOneWidget,
    );
    expect(find.text('human-message'), findsOneWidget);
    expect(find.text('generator-message'), findsOneWidget);
    expect(find.text('reviewer-message'), findsNothing);
  });
}

SessionDetail _buildSession({
  required ReviewerLifecycleState reviewerState,
  AgentDisplayMode displayMode = AgentDisplayMode.showAll,
  List<ChatMessage> messages = const <ChatMessage>[],
}) {
  final configuration = kDefaultAgentConfiguration.copyWith(
    preset: AgentPreset.review,
    displayMode: displayMode,
    agents: kDefaultAgentDefinitions.map((agent) {
      if (agent.agentId == AgentId.reviewer) {
        return agent.copyWith(
          enabled: true,
          label: 'Safety Reviewer',
          visibility: AgentVisibilityMode.collapsed,
          maxTurns: 1,
        );
      }
      if (agent.agentId == AgentId.summary) {
        return agent.copyWith(enabled: false, maxTurns: 0);
      }
      return agent;
    }).toList(),
  );
  final now = DateTime.utc(2026, 1, 1);
  return SessionDetail(
    id: 'session-a',
    title: 'Chat A',
    workspacePath: '/workspace/a',
    workspaceName: 'Workspace A',
    createdAt: now,
    updatedAt: now,
    messages: messages,
    agentConfiguration: configuration,
    autoModeEnabled: true,
    autoMaxTurns: 1,
    activeAgentRunId: 'run-1',
    reviewerState: reviewerState,
  );
}

ChatMessage _buildMessage({
  required String id,
  ChatMessageAuthorType authorType = ChatMessageAuthorType.assistant,
  AgentId agentId = AgentId.generator,
  AgentType agentType = AgentType.generator,
  AgentVisibilityMode visibility = AgentVisibilityMode.visible,
  bool isUser = false,
}) {
  final now = DateTime.utc(2026, 1, 1);
  return ChatMessage(
    id: id,
    text: id,
    isUser: isUser,
    authorType: authorType,
    agentId: agentId,
    agentType: agentType,
    visibility: visibility,
    status: ChatMessageStatus.completed,
    createdAt: now,
    updatedAt: now,
    runId: 'run-1',
  );
}
