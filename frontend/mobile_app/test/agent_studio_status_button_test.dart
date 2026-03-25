import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/reviewer_lifecycle_state.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_studio_status_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('review preset shows reviewer-specific icon state', () {
    final presentation = buildAgentStudioStatusPresentation(
      _buildSession(
        preset: AgentPreset.review,
        reviewerState: ReviewerLifecycleState.waitingOnGenerator,
      ),
    );

    expect(presentation.icon, Icons.rate_review_outlined);
    expect(presentation.badgeLabel, 'R');
    expect(presentation.tooltip, contains('Generator + Reviewer'));
    expect(
        presentation.tooltip, contains('Safety Reviewer waiting on generator'));
  });

  test('solo preset stays on generator-only icon without badge', () {
    final presentation = buildAgentStudioStatusPresentation(
      _buildSession(
        preset: AgentPreset.solo,
        reviewerEnabled: false,
        reviewerState: ReviewerLifecycleState.off,
      ),
    );

    expect(presentation.icon, Icons.smart_toy_outlined);
    expect(presentation.badgeLabel, isNull);
    expect(presentation.tooltip, 'Agents: Solo generator');
  });

  testWidgets('triad preset renders status badge on the agent button',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentStudioStatusButton(
            session: _buildSession(
              preset: AgentPreset.triad,
              reviewerState: ReviewerLifecycleState.completed,
            ),
            onPressed: () {},
          ),
        ),
      ),
    );

    expect(find.byIcon(Icons.hub_outlined), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });
}

SessionDetail _buildSession({
  required AgentPreset preset,
  required ReviewerLifecycleState reviewerState,
  bool reviewerEnabled = true,
}) {
  final configuration = kDefaultAgentConfiguration.copyWith(
    preset: preset,
    agents: kDefaultAgentDefinitions.map((agent) {
      if (agent.agentId == AgentId.reviewer) {
        return agent.copyWith(
          enabled: reviewerEnabled,
          label: 'Safety Reviewer',
        );
      }
      if (agent.agentId == AgentId.summary) {
        return agent.copyWith(
          enabled: preset == AgentPreset.triad,
          maxTurns: preset == AgentPreset.triad ? 1 : 0,
        );
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
    messages: const <ChatMessage>[],
    agentConfiguration: configuration,
    autoModeEnabled: reviewerEnabled,
    autoMaxTurns: reviewerEnabled ? 1 : 0,
    reviewerState: reviewerState,
  );
}
