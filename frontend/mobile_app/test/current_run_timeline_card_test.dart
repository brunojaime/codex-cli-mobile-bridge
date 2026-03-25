import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/current_run_execution.dart';
import 'package:codex_mobile_frontend/src/models/reviewer_lifecycle_state.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_studio_status_button.dart';
import 'package:codex_mobile_frontend/src/widgets/current_run_timeline_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('renders active run timeline with stage status details',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: CurrentRunTimelineCard(
              session: _buildSession(
                currentRun: const CurrentRunExecution(
                  runId: 'run-12345678',
                  state: CurrentRunStageState.running,
                  isActive: true,
                  stages: <CurrentRunStageExecution>[
                    CurrentRunStageExecution(
                      stage: CurrentRunStageId.generator,
                      state: CurrentRunStageState.running,
                      configured: true,
                      attemptCount: 2,
                      maxTurns: 3,
                      jobId: 'job-generator',
                      latestActivity: 'Streaming output',
                    ),
                    CurrentRunStageExecution(
                      stage: CurrentRunStageId.reviewer,
                      state: CurrentRunStageState.notScheduled,
                      configured: true,
                      maxTurns: 6,
                    ),
                    CurrentRunStageExecution(
                      stage: CurrentRunStageId.summary,
                      state: CurrentRunStageState.disabled,
                      configured: false,
                      maxTurns: 0,
                    ),
                  ],
                ),
                recentRuns: const <CurrentRunExecution>[
                  CurrentRunExecution(
                    runId: 'run-older',
                    state: CurrentRunStageState.completed,
                    isActive: false,
                    stages: <CurrentRunStageExecution>[
                      CurrentRunStageExecution(
                        stage: CurrentRunStageId.generator,
                        state: CurrentRunStageState.completed,
                        configured: true,
                        attemptCount: 1,
                        maxTurns: 2,
                      ),
                      CurrentRunStageExecution(
                        stage: CurrentRunStageId.reviewer,
                        state: CurrentRunStageState.completed,
                        configured: true,
                        attemptCount: 1,
                        maxTurns: 1,
                      ),
                      CurrentRunStageExecution(
                        stage: CurrentRunStageId.summary,
                        state: CurrentRunStageState.skipped,
                        configured: false,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Run history'), findsOneWidget);
    expect(find.textContaining('Active run run-1234'), findsOneWidget);
    expect(find.textContaining('Run run-olde'), findsOneWidget);
    expect(find.text('Generator 2/3'), findsOneWidget);
    expect(find.text('Reviewer 0/6'), findsOneWidget);
    expect(find.text('Summary 0/0'), findsNWidgets(2));
    expect(find.text('Running'), findsAtLeastNWidgets(1));
    expect(find.text('Not scheduled yet'), findsOneWidget);
    expect(find.text('Disabled'), findsOneWidget);
    expect(find.textContaining('Streaming output'), findsOneWidget);
    expect(find.text('Completed'), findsAtLeastNWidgets(1));
  });

  testWidgets(
      'configuration state and execution state stay separate when no run is active',
      (WidgetTester tester) async {
    final session = _buildSession(
      preset: AgentPreset.review,
      activeAgentRunId: null,
      currentRun: null,
      reviewerState: ReviewerLifecycleState.idle,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(
              children: <Widget>[
                AgentStudioStatusButton(
                  session: session,
                  onPressed: () {},
                ),
                CurrentRunTimelineCard(session: session),
              ],
            ),
          ),
        ),
      ),
    );

    expect(find.byIcon(Icons.rate_review_outlined), findsOneWidget);
    expect(find.text('R'), findsOneWidget);
    expect(
      find.text(
        'No active or recent runs yet. Start an agent request to populate this panel.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('stacks run status content on narrow widths without overflow',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Center(
              child: SizedBox(
                width: 220,
                child: CurrentRunTimelineCard(
                  session: _buildSession(
                    currentRun: const CurrentRunExecution(
                      runId: 'run-with-a-very-long-identifier',
                      state: CurrentRunStageState.running,
                      isActive: true,
                      stages: <CurrentRunStageExecution>[
                        CurrentRunStageExecution(
                          stage: CurrentRunStageId.generator,
                          state: CurrentRunStageState.running,
                          configured: true,
                          attemptCount: 12,
                          maxTurns: 12,
                          latestActivity:
                              'Generator is still streaming a long update.',
                        ),
                        CurrentRunStageExecution(
                          stage: CurrentRunStageId.reviewer,
                          state: CurrentRunStageState.notScheduled,
                          configured: true,
                          maxTurns: 12,
                        ),
                      ],
                    ),
                    generatorLabel: 'Primary Generator With Extended Label',
                    reviewerLabel: 'Safety Reviewer With Extended Label',
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.textContaining('Primary Generator With'), findsOneWidget);
    expect(find.text('Running'), findsAtLeastNWidgets(1));
    expect(find.text('Not scheduled yet'), findsOneWidget);
  });

  testWidgets('run history remains in a short viewport without render overflow',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(320, 520);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            height: 360,
            child: Column(
              children: <Widget>[
                Expanded(
                  child: CustomScrollView(
                    slivers: <Widget>[
                      SliverPadding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                        sliver: SliverToBoxAdapter(
                          child: CurrentRunTimelineCard(
                            session: _buildSession(
                              currentRun: const CurrentRunExecution(
                                runId: 'run-12345678',
                                state: CurrentRunStageState.running,
                                isActive: true,
                                stages: <CurrentRunStageExecution>[
                                  CurrentRunStageExecution(
                                    stage: CurrentRunStageId.generator,
                                    state: CurrentRunStageState.running,
                                    configured: true,
                                    attemptCount: 2,
                                    maxTurns: 3,
                                  ),
                                  CurrentRunStageExecution(
                                    stage: CurrentRunStageId.reviewer,
                                    state: CurrentRunStageState.notScheduled,
                                    configured: true,
                                    maxTurns: 6,
                                  ),
                                  CurrentRunStageExecution(
                                    stage: CurrentRunStageId.summary,
                                    state: CurrentRunStageState.disabled,
                                    configured: false,
                                    maxTurns: 0,
                                  ),
                                ],
                              ),
                              recentRuns: const <CurrentRunExecution>[
                                CurrentRunExecution(
                                  runId: 'run-older',
                                  state: CurrentRunStageState.completed,
                                  isActive: false,
                                  stages: <CurrentRunStageExecution>[
                                    CurrentRunStageExecution(
                                      stage: CurrentRunStageId.generator,
                                      state: CurrentRunStageState.completed,
                                      configured: true,
                                      attemptCount: 1,
                                      maxTurns: 2,
                                    ),
                                    CurrentRunStageExecution(
                                      stage: CurrentRunStageId.reviewer,
                                      state: CurrentRunStageState.completed,
                                      configured: true,
                                      attemptCount: 1,
                                      maxTurns: 1,
                                    ),
                                    CurrentRunStageExecution(
                                      stage: CurrentRunStageId.summary,
                                      state: CurrentRunStageState.skipped,
                                      configured: false,
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SliverFillRemaining(
                        hasScrollBody: false,
                        child: SizedBox(),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 96),
              ],
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Run history'), findsOneWidget);
  });
}

SessionDetail _buildSession({
  AgentPreset preset = AgentPreset.triad,
  String? activeAgentRunId = 'run-12345678',
  ReviewerLifecycleState reviewerState = ReviewerLifecycleState.running,
  CurrentRunExecution? currentRun,
  List<CurrentRunExecution> recentRuns = const <CurrentRunExecution>[],
  String generatorLabel = 'Generator',
  String reviewerLabel = 'Reviewer',
  String summaryLabel = 'Summary',
}) {
  final configuration = kDefaultAgentConfiguration.copyWith(
    preset: preset,
    agents: kDefaultAgentDefinitions.map((agent) {
      if (agent.agentId == AgentId.generator) {
        return agent.copyWith(label: generatorLabel);
      }
      if (agent.agentId == AgentId.reviewer) {
        return agent.copyWith(
          enabled: preset != AgentPreset.solo,
          label: reviewerLabel,
        );
      }
      if (agent.agentId == AgentId.summary) {
        return agent.copyWith(
          label: summaryLabel,
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
    autoModeEnabled: preset != AgentPreset.solo,
    autoMaxTurns: preset == AgentPreset.solo ? 0 : 1,
    activeAgentRunId: activeAgentRunId,
    reviewerState: reviewerState,
    currentRun: currentRun,
    recentRuns: recentRuns,
  );
}
