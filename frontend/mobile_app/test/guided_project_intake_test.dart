import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/domain_factory.dart';
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

  test('UX lane configs bind generator and reviewer prompts with stop budget',
      () {
    final generatorOnly = buildUxGeneratorConfiguration(
      kDefaultAgentConfiguration,
    );
    final full = buildUxFullConfiguration(kDefaultAgentConfiguration);

    expect(isUxGeneratorConfiguration(generatorOnly), isTrue);
    expect(generatorOnly.byId(AgentId.generator)?.label, 'UX Generator');
    expect(generatorOnly.byId(AgentId.generator)?.prompt,
        contains('visual-ux-polish'));
    expect(generatorOnly.byId(AgentId.reviewer)?.enabled, isFalse);
    expect(isUxFullConfiguration(full), isTrue);
    expect(full.byId(AgentId.reviewer)?.label, 'UX Reviewer');
    expect(full.byId(AgentId.reviewer)?.prompt, contains('"status"'));
    expect(full.byId(AgentId.generator)?.maxTurns, 15);
    expect(full.byId(AgentId.reviewer)?.maxTurns, 15);
  });

  test('build confirmation requires ready marker in transcript', () {
    expect(isProjectFactoryBuildConfirmation('ok'), isTrue);
    expect(isProjectFactoryBuildConfirmation('dale'), isTrue);
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
          ),
        ),
      ),
    );

    expect(find.text('Initial admin emails'), findsOneWidget);
    expect(find.text('Contract preview'), findsOneWidget);
    expect(find.textContaining('release:'), findsOneWidget);

    await tester.tap(find.textContaining('Owner'));
    await tester.tap(find.text('Preview contract'));
    await tester.pump();

    expect(answers.single, <String>['owner@example.com']);
    expect(previewed, 1);
    expect(find.text('Confirm build'), findsNothing);
  });

  testWidgets('New Project opens persisted guided intake and live answers',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true;
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

    expect(find.text('Project title'), findsOneWidget);
    expect(apiClient.createDraftCalls, 0);

    bool startIsEnabled() {
      final Finder startButton = find.descendant(
        of: find.byType(AlertDialog),
        matching: find.widgetWithText(FilledButton, 'Start'),
      );
      return tester.widget<FilledButton>(startButton).onPressed != null;
    }

    final firstDialogFields = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(TextField),
    );
    expect(startIsEnabled(), isFalse);

    await tester.enterText(
      firstDialogFields.at(0),
      'Clinica Norte',
    );
    await tester.pumpAndSettle();
    expect(startIsEnabled(), isFalse);
    expect(apiClient.createDraftCalls, 0);

    await tester.enterText(firstDialogFields.at(1), 'not-an-email');
    await tester.tap(find.byTooltip('Add admin email'));
    await tester.pumpAndSettle();
    expect(startIsEnabled(), isFalse);
    expect(find.text('Enter a valid admin email.'), findsOneWidget);

    await tester.enterText(firstDialogFields.at(1), 'OWNER@Example.COM');
    await tester.tap(find.byTooltip('Add admin email'));
    await tester.pumpAndSettle();
    expect(find.text('owner@example.com'), findsOneWidget);
    expect(startIsEnabled(), isTrue);

    await tester.tap(find.byTooltip('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('owner@example.com'), findsNothing);
    expect(startIsEnabled(), isFalse);

    await tester.enterText(firstDialogFields.at(1), 'OWNER@Example.COM');
    await tester.tap(find.byTooltip('Add admin email'));
    await tester.pumpAndSettle();
    expect(find.text('owner@example.com'), findsOneWidget);
    expect(startIsEnabled(), isTrue);

    await tester.tap(find.text('Start'));
    await tester.pumpAndSettle();

    expect(apiClient.createDraftCalls, 1);
    expect(apiClient.startInitCalls, 0);
    expect(apiClient.lastInitWorkspacePath, isNull);
    expect(apiClient.sendMessageCalls, 0);
    expect(apiClient.lastDraftRequest?.guidedIntakeEnabled, isTrue);
    expect(apiClient.lastDraftRequest?.name, 'Clinica Norte');
    expect(apiClient.lastDraftRequest?.initialAdminEmails,
        <String>['owner@example.com']);
    expect(apiClient.lastCreatedSessionTitle, 'Clinica Norte');
    expect(find.text('Deterministic baseline init'), findsNothing);
    expect(find.text('Initial admin emails'), findsOneWidget);
    expect(find.textContaining('Cloudflare doctor pending'), findsOneWidget);
    expect(find.text('Preview contract'), findsOneWidget);
    expect(find.text('Confirm build'), findsNothing);
    expect(apiClient.answerCalls, 0);
    expect(apiClient.previewCalls, 0);
    expect(apiClient.confirmCalls, 0);

    await tester.ensureVisible(find.byType(ActionChip).first);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(ActionChip).first);
    await tester.pumpAndSettle();
    expect(apiClient.answerCalls, 1);
    expect(apiClient.previewCalls, 1);

    await _tapOkDaleProjectFactoryButton(tester);

    expect(apiClient.confirmCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
    expect(
        find.textContaining('Current phase: Init preflight'), findsOneWidget);

    await tester.tap(find.byTooltip('New project'));
    await tester.pumpAndSettle();

    final secondDialogFields = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(TextField),
    );
    await tester.enterText(
      secondDialogFields.at(0),
      'Veterinaria Sur',
    );
    await tester.enterText(secondDialogFields.at(1), 'admin@vet.test');
    await tester.tap(find.byTooltip('Add admin email'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Start'));
    await tester.pumpAndSettle();

    expect(apiClient.createDraftCalls, 2);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(apiClient.createdDraftNames,
        containsAllInOrder(<String>['Clinica Norte', 'Veterinaria Sur']));
  });

  testWidgets(
      'empty Project Factory session hydrates intake and waits for approval',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..exposePersistedDraftSummary = true
      ..persistedDraftName = 'Clinica Norte'
      ..setReadyForReviewIntake();
    apiClient.seedProjectFactorySession(
      id: 'empty-session',
      title: 'Clinica Norte',
    );
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

    await controller.selectSession('empty-session');
    await tester.pumpAndSettle();

    expect(controller.currentSession?.messages, isEmpty);
    expect(apiClient.listDraftCalls, 1);
    expect(apiClient.createDraftCalls, 0);
    expect(apiClient.confirmCalls, 0);
    expect(apiClient.startInitCalls, 0);
    expect(find.text('Guided intake'), findsOneWidget);
    expect(find.text('Contract preview'), findsOneWidget);
    expect(find.text('Confirm build'), findsOneWidget);

    await tester.tap(find.text('Confirm build'));
    await tester.pumpAndSettle();

    expect(apiClient.confirmCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
  });

  testWidgets('persisted blocked init hydrates retry action', (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..exposePersistedDraftSummary = true
      ..persistedDraftName = 'Clinica Norte'
      ..setReadyForReviewIntake()
      ..persistedInitJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'blocked_with_context',
          currentPhase: 'github_repository',
          canContinueWithBlockedContext: true,
          retryAvailable: true,
          phases: const <ProjectFactoryInitPhase>[
            ProjectFactoryInitPhase(
              name: 'github_repository',
              status: 'blocked',
              message: 'GitHub repository could not be created.',
              blockers: <Map<String, dynamic>>[
                <String, dynamic>{
                  'code': 'github_repo_create_failed',
                  'phase': 'github_repository',
                  'message': 'GitHub repository could not be created.',
                  'nextAction': 'Retry repository creation.',
                  'recoverable': true,
                }
              ],
              commandEvidence: <Map<String, dynamic>>[],
              artifacts: <Map<String, dynamic>>[],
            ),
          ],
          blockers: const <Map<String, dynamic>>[
            <String, dynamic>{
              'code': 'github_repo_create_failed',
              'phase': 'github_repository',
              'message': 'GitHub repository could not be created.',
              'nextAction': 'Retry repository creation.',
              'recoverable': true,
            }
          ],
        ),
      ];
    apiClient.seedProjectFactorySession(
      id: 'blocked-session',
      title: 'Clinica Norte',
    );
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

    await controller.selectSession('blocked-session');
    await tester.pumpAndSettle();

    expect(apiClient.listDraftCalls, 1);
    expect(apiClient.listInitJobCalls, 1);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
    expect(find.text('Github repository'), findsWidgets);
    expect(
      find.byKey(const ValueKey<String>('project-factory-init-retry-button')),
      findsOneWidget,
    );
  });

  testWidgets('context-only blocked init hydrates retry action',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..initPollJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'blocked_with_context',
          currentPhase: 'android_preview_release',
          canContinueWithBlockedContext: true,
          retryAvailable: true,
          phases: const <ProjectFactoryInitPhase>[
            ProjectFactoryInitPhase(
              name: 'android_preview_release',
              status: 'blocked',
              message: 'Android preview APK release publish failed.',
              blockers: <Map<String, dynamic>>[
                <String, dynamic>{
                  'code': 'android_preview_release_publish_failed',
                  'phase': 'android_preview_release',
                  'message': 'Android preview APK release publish failed.',
                  'nextAction': 'Run publish script.',
                  'recoverable': true,
                }
              ],
              commandEvidence: <Map<String, dynamic>>[],
              artifacts: <Map<String, dynamic>>[],
            ),
          ],
          blockers: const <Map<String, dynamic>>[
            <String, dynamic>{
              'code': 'android_preview_release_publish_failed',
              'phase': 'android_preview_release',
              'message': 'Android preview APK release publish failed.',
              'nextAction': 'Run publish script.',
              'recoverable': true,
            }
          ],
        ),
      ];
    apiClient.seedProjectFactorySession(
      id: 'context-only-session',
      title: 'prueba11',
      agentConfiguration: kDefaultAgentConfiguration,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'pf-init-context-pf-init-1',
          text: '# Deterministic Init Context\n\n'
              'Project: prueba11 (`prueba11`)\n'
              'Init job id: `pf-init-1`\n\n'
              '## Current Blockers\n'
              '- `android_preview_release`: failed',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          agentId: AgentId.generator,
          status: ChatMessageStatus.completed,
          createdAt: _GuidedProjectApiClient._timestamp,
          updatedAt: _GuidedProjectApiClient._timestamp,
        ),
      ],
    );
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

    await controller.selectSession('context-only-session');
    await tester.pumpAndSettle();

    expect(apiClient.listDraftCalls, 0);
    expect(apiClient.getInitJobCalls, 1);
    expect(apiClient.listInitJobCalls, 0);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
    expect(find.text('Android preview release'), findsWidgets);
    expect(
      find.byKey(const ValueKey<String>('project-factory-init-retry-button')),
      findsOneWidget,
    );
  });

  testWidgets('Ok dale CTA is consumed as a technical event before init',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true;

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );

    expect(apiClient.createDraftCalls, 1);
    expect(apiClient.startInitCalls, 0);
    expect(apiClient.lastInitWorkspacePath, isNull);
    expect(apiClient.domainFactoryStarts, 0);
    expect(apiClient.sentMessages, isEmpty);
    expect(find.text('Deterministic baseline init'), findsNothing);

    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    expect(apiClient.confirmCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sentMessages, isEmpty);
    expect(apiClient.lastInitWorkspacePath, isNull);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
  });

  testWidgets('Ok dale button appears under generator and approves technically',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true;

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );

    final okDaleButton =
        find.byKey(const ValueKey<String>('project-factory-ok-dale-button'));
    expect(okDaleButton, findsOneWidget);
    expect(apiClient.startInitCalls, 0);
    expect(apiClient.sentMessages, isEmpty);
    expect(
      tester.getTopLeft(okDaleButton).dy,
      greaterThan(
        tester
            .getBottomLeft(find.byKey(const ValueKey<String>(
              'chat-bubble-generator-ready',
            )))
            .dy,
      ),
    );

    await tester.tap(okDaleButton);
    await tester.pumpAndSettle();

    expect(apiClient.confirmCalls, 1);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.sendMessageCalls, 0);
    expect(apiClient.sentMessages, isEmpty);
    expect(find.text('Deterministic baseline init'), findsOneWidget);
    expect(okDaleButton, findsNothing);
  });

  testWidgets(
      'init polling starts Domain Factory once with generated workspace when ready',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true
      ..initPollJobs = <ProjectFactoryInitJob>[
        _initJob(status: 'running', readyForBusinessLlm: false),
        _initJob(
          status: 'ready',
          readyForBusinessLlm: true,
          generatedWorkspacePath: '/projects/generated/clinica-norte',
          workspacePath: '/projects/older-session-workspace',
        ),
      ];

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    expect(apiClient.startInitCalls, 1);
    expect(apiClient.domainFactoryStarts, 0);
    await _sendComposerMessage(tester, 'ok');
    expect(apiClient.startInitCalls, 1);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
    expect(apiClient.getInitJobCalls, 1);
    expect(apiClient.domainFactoryStarts, 0);

    await tester.pump(const Duration(seconds: 2));
    await _pumpDeferredDomainFactoryStart(tester);

    expect(apiClient.getInitJobCalls, 2);
    expect(apiClient.startInitCalls, 1);
    expect(apiClient.domainFactoryStarts, 1);
    expect(apiClient.domainFactoryWorkspacePaths,
        <String?>['/projects/generated/clinica-norte']);
  });

  testWidgets(
      'blocked-with-context init can start Domain Factory with generated workspace',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true
      ..initPollJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'blocked_with_context',
          canContinueWithBlockedContext: true,
          generatedWorkspacePath: '/projects/generated/blocked',
        ),
      ];

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    await tester.pump(const Duration(seconds: 2));
    await _pumpDeferredDomainFactoryStart(tester);

    expect(apiClient.getInitJobCalls, 1);
    expect(apiClient.domainFactoryStarts, 1);
    expect(apiClient.domainFactoryWorkspacePaths,
        <String?>['/projects/generated/blocked']);
  });

  testWidgets('blocked init shows phases and can be retried', (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true
      ..initPollJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'blocked_with_context',
          currentPhase: 'preview_smoke',
          canContinueWithBlockedContext: true,
          generatedWorkspacePath: '/projects/generated/blocked',
          retryAvailable: true,
          phases: const <ProjectFactoryInitPhase>[
            ProjectFactoryInitPhase(
              name: 'github_repository',
              status: 'completed',
              message: 'GitHub repository verified.',
              blockers: <Map<String, dynamic>>[],
              commandEvidence: <Map<String, dynamic>>[],
              artifacts: <Map<String, dynamic>>[],
            ),
            ProjectFactoryInitPhase(
              name: 'preview_smoke',
              status: 'blocked',
              message: '',
              blockers: <Map<String, dynamic>>[
                <String, dynamic>{
                  'code': 'web_preview_invite_secret_missing',
                  'phase': 'preview_smoke',
                  'message': 'Invite secret missing.',
                  'nextAction': 'Configure WEB_PREVIEW_INVITE_SECRET.',
                  'recoverable': true,
                }
              ],
              commandEvidence: <Map<String, dynamic>>[],
              artifacts: <Map<String, dynamic>>[],
            ),
          ],
          blockers: const <Map<String, dynamic>>[
            <String, dynamic>{
              'code': 'web_preview_invite_secret_missing',
              'phase': 'preview_smoke',
              'message': 'Invite secret missing.',
              'nextAction': 'Configure WEB_PREVIEW_INVITE_SECRET.',
              'recoverable': true,
            }
          ],
        ),
      ]
      ..retryInitJobs = <ProjectFactoryInitJob>[
        _initJob(status: 'running', currentPhase: 'preview_smoke'),
      ]
      ..initPollAfterRetryJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'ready',
          readyForBusinessLlm: true,
          generatedWorkspacePath: '/projects/generated/blocked',
        ),
      ];

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    await tester.pump(const Duration(seconds: 2));
    await _pumpDeferredDomainFactoryStart(tester);

    expect(find.text('Preview smoke'), findsWidgets);
    expect(find.text('Invite secret missing.'), findsWidgets);
    expect(
        find.byKey(const ValueKey<String>('project-factory-init-retry-button')),
        findsOneWidget);

    final retryButton = tester.widget<FilledButton>(find
        .byKey(const ValueKey<String>('project-factory-init-retry-button')));
    retryButton.onPressed?.call();
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    await _pumpDeferredDomainFactoryStart(tester);

    expect(apiClient.retryInitCalls, 1);
    expect(apiClient.domainFactoryStarts, 1);
  });

  testWidgets('cancelled init does not start Domain Factory', (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true
      ..initPollJobs = <ProjectFactoryInitJob>[
        _initJob(
          status: 'cancelled',
          generatedWorkspacePath: '/projects/generated/cancelled',
        ),
      ];

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    await tester.pump(const Duration(seconds: 2));
    await _pumpDeferredDomainFactoryStart(tester);

    expect(apiClient.getInitJobCalls, 1);
    expect(apiClient.domainFactoryStarts, 0);
    expect(tester.takeException(), isNull);

    apiClient
      ..initPollError = StateError('poll failed')
      ..initPollJobs = <ProjectFactoryInitJob>[];
    await _sendComposerMessage(tester, 'ok');
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(apiClient.startInitCalls, 1);
    expect(apiClient.domainFactoryStarts, 0);
    expect(apiClient.sentMessages, isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('init poll errors leave chat recoverable', (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true
      ..initPollError = StateError('poll failed');

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(apiClient.startInitCalls, 1);
    expect(apiClient.getInitJobCalls, 1);
    expect(apiClient.domainFactoryStarts, 0);
    expect(find.textContaining('Could not refresh deterministic init.'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('disposing chat cancels pending init polling safely',
      (tester) async {
    final apiClient = _GuidedProjectApiClient()
      ..includeGeneratorReadyMessage = true;

    await _pumpGuidedChat(tester, apiClient);
    await _openNewProjectIntake(
      tester,
      name: 'Clinica Norte',
      adminEmail: 'owner@example.com',
    );
    await _answerGuidedIntakeQuestion(tester);
    await _tapOkDaleProjectFactoryButton(tester);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 3));

    expect(apiClient.getInitJobCalls, 0);
    expect(apiClient.domainFactoryStarts, 0);
    expect(tester.takeException(), isNull);
  });
}

Finder _composerField() {
  return find.byWidgetPredicate(
    (widget) => widget is TextField && widget.decoration?.hintText == 'Message',
  );
}

Future<void> _pumpGuidedChat(
  WidgetTester tester,
  _GuidedProjectApiClient apiClient,
) async {
  final controller = ChatController(
    apiClient: apiClient,
    notificationService: const NoopChatNotificationService(),
  );
  addTearDown(controller.dispose);

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
}

Future<void> _openNewProjectIntake(
  WidgetTester tester, {
  required String name,
  required String adminEmail,
}) async {
  await tester.tap(find.byTooltip('New project'));
  await tester.pumpAndSettle();

  final fields = find.descendant(
    of: find.byType(AlertDialog),
    matching: find.byType(TextField),
  );
  await tester.enterText(fields.at(0), name);
  await tester.enterText(fields.at(1), adminEmail);
  await tester.tap(find.byTooltip('Add admin email'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Start'));
  await tester.pumpAndSettle();
}

Future<void> _answerGuidedIntakeQuestion(WidgetTester tester) async {
  await tester.ensureVisible(find.byType(ActionChip).first);
  await tester.pumpAndSettle();
  await tester.tap(find.byType(ActionChip).first);
  await tester.pumpAndSettle();
}

Future<void> _sendComposerMessage(WidgetTester tester, String message) async {
  await tester.enterText(_composerField(), message);
  await tester.testTextInput.receiveAction(TextInputAction.send);
  await tester.pumpAndSettle();
}

Future<void> _tapOkDaleProjectFactoryButton(
  WidgetTester tester, {
  bool requireVisible = true,
}) async {
  final button =
      find.byKey(const ValueKey<String>('project-factory-ok-dale-button'));
  if (requireVisible) {
    await tester.ensureVisible(button);
  }
  tester.widget<FilledButton>(button).onPressed?.call();
  await tester.pumpAndSettle();
}

Future<void> _pumpDeferredDomainFactoryStart(WidgetTester tester) async {
  await tester.pumpAndSettle(const Duration(milliseconds: 10));
}

ProjectFactoryInitJob _initJob({
  required String status,
  String currentPhase = 'init_preflight',
  bool readyForBusinessLlm = false,
  bool canContinueWithBlockedContext = false,
  bool retryAvailable = false,
  String? workspacePath,
  String? generatedWorkspacePath,
  List<ProjectFactoryInitPhase> phases = const <ProjectFactoryInitPhase>[
    ProjectFactoryInitPhase(
      name: 'init_preflight',
      status: 'completed',
      message: '',
      blockers: <Map<String, dynamic>>[],
      commandEvidence: <Map<String, dynamic>>[],
      artifacts: <Map<String, dynamic>>[],
    ),
  ],
  List<Map<String, dynamic>> blockers = const <Map<String, dynamic>>[],
}) {
  return ProjectFactoryInitJob(
    initJobId: 'pf-init-1',
    draftId: 'pf-draft-1',
    chatSessionId: 'created-session',
    createdAt: _GuidedProjectApiClient._timestamp.toIso8601String(),
    updatedAt: _GuidedProjectApiClient._timestamp.toIso8601String(),
    status: status,
    currentPhase: currentPhase,
    workspacePath: workspacePath,
    generatedWorkspacePath: generatedWorkspacePath,
    phases: phases,
    remoteResources: const <Map<String, dynamic>>[],
    blockers: blockers,
    readyForBusinessLlm: readyForBusinessLlm,
    canContinueWithBlockedContext: canContinueWithBlockedContext,
    retryAvailable: retryAvailable,
  );
}

class _GuidedProjectApiClient extends ApiClient {
  _GuidedProjectApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 7, 9);

  ProjectFactoryDraftRequest? lastDraftRequest;
  String? lastCreatedSessionTitle;
  String? lastInitWorkspacePath;
  int createDraftCalls = 0;
  int answerCalls = 0;
  int previewCalls = 0;
  int confirmCalls = 0;
  int getIntakeCalls = 0;
  int listDraftCalls = 0;
  int listInitJobCalls = 0;
  int startInitCalls = 0;
  int getInitJobCalls = 0;
  int retryInitCalls = 0;
  int sendMessageCalls = 0;
  int domainFactoryStarts = 0;
  bool includeGeneratorReadyMessage = false;
  bool exposePersistedDraftSummary = false;
  String persistedDraftName = 'Untitled project';
  Object? initPollError;
  List<ProjectFactoryInitJob> initPollJobs = <ProjectFactoryInitJob>[];
  List<ProjectFactoryInitJob> retryInitJobs = <ProjectFactoryInitJob>[];
  List<ProjectFactoryInitJob> initPollAfterRetryJobs =
      <ProjectFactoryInitJob>[];
  List<ProjectFactoryInitJob> persistedInitJobs = <ProjectFactoryInitJob>[];
  final List<String> sentMessages = <String>[];
  final List<String?> domainFactoryWorkspacePaths = <String?>[];
  final List<String> createdDraftNames = <String>[];
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
    listDraftCalls += 1;
    if (createDraftCalls == 0 && !exposePersistedDraftSummary) {
      return const <ProjectFactoryDraftSummary>[];
    }
    return <ProjectFactoryDraftSummary>[
      ProjectFactoryDraftSummary(
        id: 'pf-draft-1',
        draftId: 'pf-draft-1',
        name: persistedDraftName,
        slug: persistedDraftName.toLowerCase().replaceAll(' ', '-'),
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
    createdDraftNames.add(request.name);
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
    lastInitWorkspacePath = workspacePath;
    return _initJob(status: 'queued', workspacePath: workspacePath);
  }

  @override
  Future<ProjectFactoryInitJob> getProjectFactoryInitJob(
      String initJobId) async {
    getInitJobCalls += 1;
    final error = initPollError;
    if (error != null) {
      throw error;
    }
    if (initPollJobs.isNotEmpty) {
      return initPollJobs.removeAt(0);
    }
    if (initPollAfterRetryJobs.isNotEmpty) {
      return initPollAfterRetryJobs.removeAt(0);
    }
    return _initJob(status: 'running');
  }

  @override
  Future<List<ProjectFactoryInitJob>> listProjectFactoryInitJobs({
    String? draftId,
    int limit = 20,
  }) async {
    listInitJobCalls += 1;
    return persistedInitJobs.take(limit).toList(growable: false);
  }

  @override
  Future<ProjectFactoryInitJob> retryProjectFactoryInitJob(
      String initJobId) async {
    retryInitCalls += 1;
    if (retryInitJobs.isNotEmpty) {
      return retryInitJobs.removeAt(0);
    }
    return _initJob(status: 'running');
  }

  @override
  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    lastCreatedSessionTitle = title;
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
      messages: includeGeneratorReadyMessage
          ? <ChatMessage>[
              ChatMessage(
                id: 'generator-ready',
                text:
                    'El contrato esta listo.\n$kProjectFactoryReadyForBuildMarker',
                isUser: false,
                authorType: ChatMessageAuthorType.assistant,
                agentId: AgentId.generator,
                status: ChatMessageStatus.completed,
                createdAt: _timestamp,
                updatedAt: _timestamp,
              ),
            ]
          : const <ChatMessage>[],
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
    sentMessages.add(text);
    return JobStatusResponse(
      jobId: 'job-${DateTime.now().microsecondsSinceEpoch}',
      sessionId: sessionId ?? 'created-session',
      status: 'completed',
      elapsedSeconds: 0,
    );
  }

  @override
  Future<DomainFactoryStart> startDomainFactoryMode(
    String sessionId, {
    String? workspacePath,
  }) async {
    domainFactoryStarts += 1;
    domainFactoryWorkspacePaths.add(workspacePath);
    final current = _sessions[sessionId]!;
    return DomainFactoryStart(
      status: 'ready',
      session: current,
      firstMessageId: 'domain-factory-start',
      statePath: '.codex/factory/domain-factory-state.json',
      specRoot: 'specs/019-domain-factory-session-a',
    );
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[];
  }

  void seedProjectFactorySession({
    required String id,
    required String title,
    AgentConfiguration? agentConfiguration,
    List<ChatMessage> messages = const <ChatMessage>[],
  }) {
    _sessions[id] = SessionDetail(
      id: id,
      title: title,
      workspacePath: '/workspace/a',
      workspaceName: 'A',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration: agentConfiguration ??
          buildProjectFactoryIntakeConfiguration(kDefaultAgentConfiguration),
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: messages,
    );
  }

  void setReadyForReviewIntake() {
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
          'name': 'Clinica Norte',
          'platforms': <String>['ios', 'android', 'web'],
        },
        'defaults': <String, dynamic>{
          'previewUrl': 'https://preview.nienfos.com/clinica-norte',
        },
      },
      readyForConfirmation: true,
    );
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
