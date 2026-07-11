import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/project_factory.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('New Project intake config keeps reviewer gated during collection', () {
    final config = buildProjectFactoryIntakeConfiguration(
      kDefaultAgentConfiguration,
    );

    expect(isProjectFactoryIntakeConfiguration(config), isTrue);
    expect(config.byId(AgentId.reviewer)?.enabled, isFalse);
  });

  test('build confirmation requires ready marker in transcript', () {
    expect(isProjectFactoryBuildConfirmation('ok, dale para adelante'), isTrue);
    expect(projectFactoryHasBuildReadyMarker(<ChatMessage>[]), isFalse);

    final readyMessage = ChatMessage(
      id: 'assistant-ready',
      text: 'Contract accepted\n$kProjectFactoryReadyForBuildMarker',
      isUser: false,
      authorType: ChatMessageAuthorType.assistant,
      agentId: AgentId.generator,
      status: ChatMessageStatus.completed,
      createdAt: DateTime.utc(2026, 1, 1),
      updatedAt: DateTime.utc(2026, 1, 1),
    );

    expect(
        projectFactoryHasBuildReadyMarker(<ChatMessage>[readyMessage]), isTrue);
  });

  test('guided intake model parses questions preview and build gate', () {
    final intake = ProjectFactoryGuidedIntake.fromJson(
      const <String, dynamic>{
        'enabled': true,
        'status': 'ready_for_review',
        'questions': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'initial_admin_emails',
            'title': 'Initial admin emails',
          }
        ],
        'answers': <Map<String, dynamic>>[
          <String, dynamic>{
            'questionId': 'initial_admin_emails',
            'value': <String>['owner@example.com'],
            'source': 'user',
            'confidence': 1.0,
            'updatedAt': '2026-07-09T00:00:00Z',
          }
        ],
        'missingFields': <Map<String, dynamic>>[],
        'assumptions': <Map<String, dynamic>>[],
        'blockers': <Map<String, dynamic>>[],
        'contractPreview': <String, dynamic>{
          'decisions': <String, dynamic>{'name': 'Clinica Norte'},
        },
        'updatedAt': '2026-07-09T00:00:00Z',
        'readyForConfirmation': true,
        'buildAllowed': false,
      },
    );

    expect(intake.enabled, isTrue);
    expect(intake.readyForConfirmation, isTrue);
    expect(intake.answers.single.questionId, 'initial_admin_emails');
    expect(intake.contractPreview!['decisions']['name'], 'Clinica Norte');
  });

  testWidgets('guided intake card renders questions preview and answer actions',
      (tester) async {
    final answers = <Object?>[];
    var previewed = 0;
    var confirmed = 0;
    final intake = ProjectFactoryGuidedIntake.fromJson(
      const <String, dynamic>{
        'enabled': true,
        'status': 'ready_for_review',
        'questions': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'initial_admin_emails',
            'title': 'Initial admin emails',
            'prompt': 'Who should receive the first preview admin invite?',
            'options': <Map<String, dynamic>>[
              <String, dynamic>{
                'label': 'Owner',
                'value': <String>['owner@example.com'],
                'recommended': true,
              }
            ],
          }
        ],
        'answers': <Map<String, dynamic>>[],
        'missingFields': <Map<String, dynamic>>[],
        'assumptions': <Map<String, dynamic>>[],
        'blockers': <Map<String, dynamic>>[
          <String, dynamic>{
            'scope': 'release',
            'message': 'Cloudflare doctor pending',
            'external': true,
          }
        ],
        'contractPreview': <String, dynamic>{
          'decisions': <String, dynamic>{
            'name': 'Clinica Norte',
            'platforms': <String>['ios', 'android', 'web'],
          },
          'defaults': <String, dynamic>{
            'previewUrl': 'https://preview.nienfos.com/clinica-norte',
          },
        },
        'updatedAt': '2026-07-09T00:00:00Z',
        'readyForConfirmation': true,
        'buildAllowed': false,
      },
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryGuidedIntakeCard(
            intake: intake,
            onAnswer: (_, value) async => answers.add(value),
            onPreview: () async => previewed += 1,
            onConfirm: () async => confirmed += 1,
          ),
        ),
      ),
    );

    expect(find.text('Initial admin emails'), findsOneWidget);
    expect(find.text('Contract preview'), findsOneWidget);
    expect(find.textContaining('release:'), findsOneWidget);

    await tester.tap(find.textContaining('Owner'));
    await tester.tap(find.text('Preview contract'));
    await tester.tap(find.text('Confirm build'));
    await tester.pump();

    expect(answers.single, <String>['owner@example.com']);
    expect(previewed, 1);
    expect(confirmed, 1);
  });

  testWidgets('New Project opens persisted guided intake and live answers',
      (tester) async {
    final apiClient = _GuidedProjectApiClient();
    final controller = ChatController(
      apiClient: apiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          projectFactoryClientOverride: apiClient,
        ),
      ),
    );

    await tester.tap(find.byTooltip('New project'));
    await tester.pumpAndSettle();

    expect(apiClient.createDraftCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(apiClient.lastDraftRequest?.guidedIntakeEnabled, isTrue);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
    expect(
        find.textContaining('Current phase: Init preflight'), findsOneWidget);
    expect(find.text('Initial admin emails'), findsOneWidget);
    expect(find.textContaining('Cloudflare doctor pending'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, 'owner@example.com');
    await tester.tap(find.text('Save answer'));
    await tester.pumpAndSettle();

    expect(apiClient.answerCalls, 1);
    expect(apiClient.previewCalls, 1);
    expect(find.text('Contract preview'), findsOneWidget);
    expect(find.textContaining('https://preview.nienfos.com'), findsOneWidget);

    await tester.tap(find.text('Confirm build'));
    await tester.pumpAndSettle();

    expect(apiClient.confirmCalls, 1);
    expect(find.text('Confirm the project contract and start the build.'),
        findsOneWidget);

    await tester.tap(find.byTooltip('New project'));
    await tester.pumpAndSettle();

    expect(apiClient.createDraftCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(apiClient.getIntakeCalls, greaterThanOrEqualTo(1));
  });
}

class _GuidedProjectApiClient extends ApiClient {
  _GuidedProjectApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 7, 9);

  ProjectFactoryDraftRequest? lastDraftRequest;
  int createDraftCalls = 0;
  int answerCalls = 0;
  int previewCalls = 0;
  int confirmCalls = 0;
  int getIntakeCalls = 0;
  int startInitCalls = 0;
  int sendMessageCalls = 0;
  final Map<String, SessionDetail> _sessions = <String, SessionDetail>{};
  ProjectFactoryGuidedIntake _intake = _intakeFromJson(
    status: 'collecting',
    questions: const <Map<String, dynamic>>[
      <String, dynamic>{
        'id': 'initial_admin_emails',
        'title': 'Initial admin emails',
        'prompt': 'Who should receive the first preview admin invite?',
        'options': <Map<String, dynamic>>[
          <String, dynamic>{
            'label': 'Use owner/admin email',
            'value': '',
            'recommended': true,
          }
        ],
      }
    ],
    missingFields: const <Map<String, dynamic>>[
      <String, dynamic>{
        'field': 'initial_admin_emails',
        'message': 'Initial admin email is required.',
      }
    ],
    blockers: const <Map<String, dynamic>>[
      <String, dynamic>{
        'scope': 'release',
        'message': 'Cloudflare doctor pending',
        'external': true,
      }
    ],
  );

  @override
  Future<ProjectFactoryOptions> getProjectFactoryOptions() async {
    return const ProjectFactoryOptions(
      defaultPlatforms: <String>['ios', 'android', 'web'],
      platforms: <String>['ios', 'android', 'web'],
      defaultBackend: 'fastapi',
      backends: <String>['fastapi'],
      defaultFrontendStrategy: 'flutter',
      frontendStrategies: <Map<String, dynamic>>[
        <String, dynamic>{'id': 'flutter'}
      ],
      logoModes: <String>['generate'],
      businessTypes: <String>['saas'],
      creationWorkflow: <String, dynamic>{},
    );
  }

  @override
  Future<List<ProjectFactoryDraftSummary>> listProjectFactoryDrafts({
    int limit = 50,
  }) async {
    if (createDraftCalls == 0) {
      return const <ProjectFactoryDraftSummary>[];
    }
    return <ProjectFactoryDraftSummary>[
      ProjectFactoryDraftSummary(
        id: 'pf-draft-1',
        draftId: 'pf-draft-1',
        name: 'Untitled project',
        businessType: 'saas',
        primaryGoal: 'Build a new application',
        status: 'draft',
        ok: true,
        createdAt: _timestamp.toIso8601String(),
        guidedIntake: _intake,
      ),
    ];
  }

  @override
  Future<ProjectFactoryDraft> createProjectFactoryDraft(
    ProjectFactoryDraftRequest request,
  ) async {
    createDraftCalls += 1;
    lastDraftRequest = request;
    return _draft();
  }

  @override
  Future<ProjectFactoryDraft> getProjectFactoryDraft(String draftId) async {
    return _draft();
  }

  @override
  Future<ProjectFactoryGuidedIntake> getProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    getIntakeCalls += 1;
    return _intake;
  }

  @override
  Future<ProjectFactoryGuidedIntake> answerProjectFactoryGuidedIntake({
    required String draftId,
    required String questionId,
    required Object? value,
    String source = 'user',
    double confidence = 1,
  }) async {
    answerCalls += 1;
    _intake = _intakeFromJson(
      status: 'ready_for_review',
      answers: <Map<String, dynamic>>[
        <String, dynamic>{
          'questionId': questionId,
          'value': value,
          'source': source,
          'confidence': confidence,
          'updatedAt': _timestamp.toIso8601String(),
        }
      ],
      blockers: const <Map<String, dynamic>>[
        <String, dynamic>{
          'scope': 'release',
          'message': 'Cloudflare doctor pending',
          'external': true,
        }
      ],
      readyForConfirmation: true,
    );
    return _intake;
  }

  @override
  Future<ProjectFactoryGuidedIntake> previewProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    previewCalls += 1;
    _intake = _intakeFromJson(
      status: 'ready_for_review',
      blockers: const <Map<String, dynamic>>[
        <String, dynamic>{
          'scope': 'release',
          'message': 'Cloudflare doctor pending',
          'external': true,
        }
      ],
      contractPreview: const <String, dynamic>{
        'decisions': <String, dynamic>{
          'name': 'Untitled project',
          'platforms': <String>['ios', 'android', 'web'],
        },
        'defaults': <String, dynamic>{
          'previewUrl': 'https://preview.nienfos.com/untitled-project',
        },
      },
      readyForConfirmation: true,
    );
    return _intake;
  }

  @override
  Future<ProjectFactoryGuidedIntake> confirmProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    confirmCalls += 1;
    _intake = _intakeFromJson(
      status: 'confirmed',
      contractPreview: _intake.contractPreview,
      buildAllowed: true,
    );
    return _intake;
  }

  @override
  Future<ProjectFactoryInitJob> startProjectFactoryInit({
    required String draftId,
    String? chatSessionId,
    String? workspacePath,
  }) async {
    startInitCalls += 1;
    return ProjectFactoryInitJob(
      initJobId: 'pf-init-1',
      draftId: draftId,
      chatSessionId: chatSessionId,
      createdAt: _timestamp.toIso8601String(),
      updatedAt: _timestamp.toIso8601String(),
      status: 'queued',
      currentPhase: 'init_preflight',
      workspacePath: workspacePath,
      phases: const <ProjectFactoryInitPhase>[
        ProjectFactoryInitPhase(
          name: 'init_preflight',
          status: 'pending',
          message: '',
          blockers: <Map<String, dynamic>>[],
          commandEvidence: <Map<String, dynamic>>[],
          artifacts: <Map<String, dynamic>>[],
        ),
      ],
      remoteResources: const <Map<String, dynamic>>[],
      blockers: const <Map<String, dynamic>>[],
      readyForBusinessLlm: false,
      canContinueWithBlockedContext: false,
    );
  }

  @override
  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    final session = SessionDetail(
      id: 'created-session',
      title: title ?? 'New project',
      workspacePath: workspacePath ?? '/workspace/a',
      workspaceName: 'A',
      agentProfileId: agentProfileId ?? 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration: kDefaultAgentConfiguration,
      turnSummariesEnabled: turnSummariesEnabled,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
    _sessions[session.id] = session;
    return session;
  }

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return _sessions.values
        .map(
          (session) => ChatSessionSummary(
            id: session.id,
            title: session.title,
            workspacePath: session.workspacePath,
            workspaceName: session.workspaceName,
            agentProfileId: session.agentProfileId,
            agentProfileName: session.agentProfileName,
            agentProfileColor: session.agentProfileColor,
            createdAt: session.createdAt,
            updatedAt: session.updatedAt,
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
    return _sessions[sessionId]!;
  }

  @override
  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    final current = _sessions[sessionId]!;
    final updated = current.copyWith(agentConfiguration: configuration);
    _sessions[sessionId] = updated;
    return updated;
  }

  @override
  Future<JobStatusResponse> sendMessage(
    String text, {
    String? sessionId,
    String? workspacePath,
    String? language,
    CodexRunOptions? codexRunOptions,
  }) async {
    sendMessageCalls += 1;
    return JobStatusResponse(
      jobId: 'job-${DateTime.now().microsecondsSinceEpoch}',
      sessionId: sessionId ?? 'created-session',
      status: 'completed',
      elapsedSeconds: 0,
    );
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[];
  }

  ProjectFactoryDraft _draft() {
    return ProjectFactoryDraft(
      draftId: 'pf-draft-1',
      createdAt: _timestamp.toIso8601String(),
      manifestPlan: const <String, dynamic>{'ok': true},
      guidedIntake: _intake,
    );
  }

  static ProjectFactoryGuidedIntake _intakeFromJson({
    required String status,
    List<Map<String, dynamic>> questions = const <Map<String, dynamic>>[],
    List<Map<String, dynamic>> answers = const <Map<String, dynamic>>[],
    List<Map<String, dynamic>> missingFields = const <Map<String, dynamic>>[],
    List<Map<String, dynamic>> blockers = const <Map<String, dynamic>>[],
    Map<String, dynamic>? contractPreview,
    bool readyForConfirmation = false,
    bool buildAllowed = false,
  }) {
    return ProjectFactoryGuidedIntake.fromJson(
      <String, dynamic>{
        'enabled': true,
        'status': status,
        'questions': questions,
        'answers': answers,
        'missingFields': missingFields,
        'assumptions': <Map<String, dynamic>>[],
        'blockers': blockers,
        if (contractPreview != null) 'contractPreview': contractPreview,
        'updatedAt': _timestamp.toIso8601String(),
        'readyForConfirmation': readyForConfirmation,
        'buildAllowed': buildAllowed,
      },
    );
  }
}
