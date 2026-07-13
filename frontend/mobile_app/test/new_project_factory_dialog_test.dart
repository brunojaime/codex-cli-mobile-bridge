import 'package:codex_mobile_frontend/src/models/project_factory.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('new project factory dialog returns a draft', (tester) async {
    NewProjectFactoryDraft? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  result = await showDialog<NewProjectFactoryDraft>(
                    context: context,
                    builder: (context) => Dialog(
                      child: NewProjectFactoryDialog(
                        options: const ProjectFactoryOptions(
                          defaultPlatforms: <String>['ios', 'android', 'web'],
                          platforms: <String>['ios', 'android', 'web'],
                          defaultBackend: 'fastapi',
                          backends: <String>['fastapi', 'go', 'none'],
                          logoModes: <String>['generate', 'upload'],
                          businessTypes: <String>['medical_appointments'],
                          creationWorkflow: <String, dynamic>{
                            'generator_runs': 20,
                            'reviewer_runs': 20,
                          },
                        ),
                      ),
                    ),
                  );
                },
                child: const Text('Open'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(0), 'Clinica Norte');
    await tester.enterText(
      find.byType(TextField).at(1),
      'Pacientes reservan turnos',
    );
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();

    expect(result, isNotNull);
    expect(result!.name, 'Clinica Norte');
    expect(result!.businessType, 'medical_appointments');
    expect(result!.backend, 'fastapi');
    expect(result!.frontendStrategy, 'flutter');
    expect(result!.referenceImages, isEmpty);
  });

  testWidgets('new project factory dialog blocks svelte with android selected',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Dialog(
            child: NewProjectFactoryDialog(
              options: const ProjectFactoryOptions(
                defaultPlatforms: <String>['ios', 'android', 'web'],
                platforms: <String>['ios', 'android', 'web'],
                defaultBackend: 'fastapi',
                backends: <String>['fastapi'],
                defaultFrontendStrategy: 'flutter',
                frontendStrategies: <Map<String, dynamic>>[
                  <String, dynamic>{
                    'id': 'flutter',
                    'display_name': 'Flutter',
                  },
                  <String, dynamic>{
                    'id': 'svelte',
                    'display_name': 'Svelte',
                  },
                ],
                logoModes: <String>['generate'],
                businessTypes: <String>['medical_appointments'],
                creationWorkflow: <String, dynamic>{},
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Flutter'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Svelte').last);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Svelte is web-only for now'),
      findsOneWidget,
    );
    final create = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Create'),
    );
    expect(create.onPressed, isNull);
  });

  testWidgets('project factory progress dialog polls until ready',
      (tester) async {
    var pollCount = 0;
    ProjectFactoryJob? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  result = await showDialog<ProjectFactoryJob>(
                    context: context,
                    builder: (context) => ProjectFactoryProgressDialog(
                      initialJob: _job(status: 'running', progress: 20),
                      pollInterval: const Duration(milliseconds: 10),
                      pollJob: (_) async {
                        pollCount += 1;
                        return _job(status: 'ready', progress: 100);
                      },
                    ),
                  );
                },
                child: const Text('Progress'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Progress'));
    await tester.pump();
    expect(find.text('running'), findsWidgets);
    await tester.pump(const Duration(milliseconds: 20));
    await tester.pumpAndSettle();
    expect(find.text('Open project'), findsOneWidget);
    await tester.tap(find.text('Open project'));
    await tester.pumpAndSettle();

    expect(pollCount, greaterThanOrEqualTo(1));
    expect(result!.status, 'ready');
  });

  testWidgets('project factory progress shows running preview release state',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  await showDialog<ProjectFactoryJob>(
                    context: context,
                    builder: (context) => ProjectFactoryProgressDialog(
                      initialJob: _job(
                        status: 'running',
                        progress: 60,
                        preview: _previewRelease(status: 'running'),
                      ),
                      pollInterval: const Duration(minutes: 1),
                      pollJob: (_) async =>
                          _job(status: 'running', progress: 60),
                    ),
                  );
                },
                child: const Text('Running preview'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Running preview'));
    await tester.pump();

    expect(find.textContaining('Initial Preview: running'), findsOneWidget);
    expect(find.text('API URL: https://preview.nienfos.com/clinica-norte/api'),
        findsOneWidget);
    expect(find.text('D1 persistence: Cloudflare preview'), findsOneWidget);
    expect(find.text('Production release: pending / not requested'),
        findsOneWidget);
  });

  testWidgets('project factory progress dialog treats interrupted as terminal',
      (tester) async {
    ProjectFactoryJob? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  result = await showDialog<ProjectFactoryJob>(
                    context: context,
                    builder: (context) => ProjectFactoryProgressDialog(
                      initialJob: _job(status: 'interrupted', progress: 40),
                      pollInterval: const Duration(milliseconds: 10),
                      pollJob: (_) async =>
                          _job(status: 'ready', progress: 100),
                    ),
                  );
                },
                child: const Text('Interrupted'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Interrupted'));
    await tester.pumpAndSettle();
    expect(find.text('interrupted'), findsWidgets);
    expect(find.text('Close'), findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    expect(result!.status, 'interrupted');
  });

  testWidgets('project factory progress dialog treats blocked as terminal',
      (tester) async {
    ProjectFactoryJob? result;
    var polled = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  result = await showDialog<ProjectFactoryJob>(
                    context: context,
                    builder: (context) => ProjectFactoryProgressDialog(
                      initialJob: _job(status: 'blocked', progress: 100),
                      pollInterval: const Duration(milliseconds: 10),
                      pollJob: (_) async {
                        polled = true;
                        return _job(status: 'ready', progress: 100);
                      },
                    ),
                  );
                },
                child: const Text('Blocked'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Blocked'));
    await tester.pumpAndSettle();
    expect(find.text('blocked'), findsWidgets);
    expect(find.text('Close'), findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    expect(polled, isFalse);
    expect(result!.status, 'blocked');
  });

  testWidgets('project factory progress shows blocked preview release blockers',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  await showDialog<ProjectFactoryJob>(
                    context: context,
                    builder: (context) => ProjectFactoryProgressDialog(
                      initialJob: _job(
                        status: 'blocked',
                        progress: 100,
                        preview: _previewRelease(
                          status: 'blocked',
                          blockerText: 'Bridge registration missing',
                        ),
                      ),
                      pollJob: (_) async =>
                          _job(status: 'ready', progress: 100),
                    ),
                  );
                },
                child: const Text('Blocked preview'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Blocked preview'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Initial Preview: blocked'), findsOneWidget);
    expect(find.text('Bridge registration missing'), findsOneWidget);
    expect(find.text('scripts/register_installable_app.sh'), findsOneWidget);
    expect(find.text('Close'), findsOneWidget);
  });

  testWidgets('project factory history shows empty state', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[],
            getJob: (_) async => _job(status: 'running', progress: 10),
            onOpenProjectPath: (_) async {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('No project factory history'), findsOneWidget);
  });

  testWidgets('project factory history opens running job progress',
      (tester) async {
    var detailCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[
              _jobSummary(status: 'running', progress: 25),
            ],
            getJob: (_) async {
              detailCalls += 1;
              return detailCalls == 1
                  ? _job(status: 'running', progress: 25)
                  : _job(status: 'ready', progress: 100);
            },
            onOpenProjectPath: (_) async {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    await tester.tap(find.text('Details'));
    await tester.pump();
    expect(find.text('running'), findsWidgets);
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text('Open project'), findsOneWidget);
  });

  testWidgets('project factory history opens completed project',
      (tester) async {
    String? openedPath;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[
              _jobSummary(status: 'ready', progress: 100),
            ],
            getJob: (_) async => _job(status: 'ready', progress: 100),
            onOpenProjectPath: (path) async {
              openedPath = path;
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(openedPath, '/projects/clinica-norte');
  });

  testWidgets('project factory history shows ready preview release action',
      (tester) async {
    String? openedPreview;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[
              _jobSummary(
                status: 'ready',
                progress: 100,
                preview: _previewRelease(status: 'ready'),
              ),
            ],
            getJob: (_) async => _job(status: 'ready', progress: 100),
            onOpenProjectPath: (_) async {},
            onOpenWebPreviewUrl: (url) async {
              openedPreview = url;
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.textContaining('Initial Preview: ready'), findsOneWidget);
    expect(find.text('Preview URL: https://preview.nienfos.com/clinica-norte'),
        findsOneWidget);
    expect(find.text('Production release: pending / not requested'),
        findsOneWidget);
    await tester.ensureVisible(find.text('Open preview'));
    await tester.tap(find.text('Open preview'));
    await tester.pumpAndSettle();
    expect(openedPreview, 'https://preview.nienfos.com/clinica-norte');
  });

  testWidgets('project factory history shows failed and interrupted errors',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[
              _jobSummary(status: 'failed', progress: 40, error: 'Failed run'),
              _jobSummary(
                status: 'interrupted',
                progress: 50,
                error: 'Restarted',
              ),
            ],
            getJob: (_) async => _job(status: 'failed', progress: 40),
            onOpenProjectPath: (_) async {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('Failed run'), findsOneWidget);
    await tester.ensureVisible(find.text('Restarted'));
    expect(find.text('Restarted'), findsOneWidget);
  });

  testWidgets('project factory history opens active web preview',
      (tester) async {
    String? openedUrl;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectFactoryHistoryDialog(
            listJobs: () async => <ProjectFactoryJobSummary>[],
            getJob: (_) async => _job(status: 'running', progress: 10),
            onOpenProjectPath: (_) async {},
            listWebPreviews: () async => <WebPreview>[
              _webPreview(status: 'active'),
            ],
            onOpenWebPreviewUrl: (url) async {
              openedUrl = url;
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Web previews'));
    await tester.pumpAndSettle();

    expect(find.text('clinica-norte'), findsOneWidget);
    expect(find.text('active'), findsOneWidget);
    await tester.tap(find.text('Open preview'));
    await tester.pumpAndSettle();

    expect(openedUrl, 'https://preview.nienfos.com/clinica-norte');
  });

  testWidgets('web preview open creates invite access link', (tester) async {
    String? openedUrl;
    var createdNonSingleUse = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WebPreviewPanelDialog(
            listWebPreviews: () async => <WebPreview>[
              _webPreview(status: 'active'),
            ],
            listInvites: (_) async => <WebPreviewInvite>[],
            createInvite: (
              previewId, {
              int? ttlSeconds,
              bool singleUse = true,
              String? email,
              String role = 'admin',
            }) async {
              createdNonSingleUse = previewId == 'wp-clinica-norte' &&
                  ttlSeconds == 604800 &&
                  singleUse == false &&
                  role == 'admin';
              return _webPreviewInvite(
                inviteUrl:
                    'https://preview.nienfos.com/clinica-norte/__preview/access?token=abc',
              );
            },
            onOpenUrl: (url) async {
              openedUrl = url;
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    await tester.tap(find.text('Open preview'));
    await tester.pumpAndSettle();

    expect(createdNonSingleUse, isTrue);
    expect(
      openedUrl,
      'https://preview.nienfos.com/clinica-norte/__preview/access?token=abc',
    );
  });

  testWidgets('web preview panel shows disabled and failed states',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WebPreviewPanelDialog(
            listWebPreviews: () async => <WebPreview>[
              _webPreview(status: 'planned'),
              _webPreview(status: 'apply_disabled', sourceApp: 'disabled-app'),
              _webPreview(
                status: 'failed',
                sourceApp: 'failed-app',
                error: 'D1 unavailable',
              ),
            ],
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('planned'), findsOneWidget);
    expect(find.text('apply_disabled'), findsOneWidget);
    expect(find.textContaining('Configure and enable web preview apply'),
        findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -260));
    await tester.pumpAndSettle();
    expect(find.text('D1 unavailable'), findsOneWidget);
  });

  testWidgets('web preview panel supports preview lifecycle actions',
      (tester) async {
    var disabled = false;
    var expired = false;
    var extended = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WebPreviewPanelDialog(
            listWebPreviews: () async => <WebPreview>[
              _webPreview(status: 'active'),
            ],
            disablePreview: ({required previewId, ttlSeconds, reason}) async {
              disabled = true;
              return _webPreview(status: 'disabled');
            },
            expirePreview: ({required previewId, ttlSeconds, reason}) async {
              expired = true;
              return _webPreview(status: 'expired');
            },
            extendPreview: ({required previewId, ttlSeconds, reason}) async {
              extended = ttlSeconds == 604800;
              return _webPreview(status: 'active');
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('Copy URL'), findsOneWidget);

    await tester.tap(find.text('Extend 7d'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Expire'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Disable'));
    await tester.pumpAndSettle();

    expect(extended, isTrue);
    expect(expired, isTrue);
    expect(disabled, isTrue);
  });

  testWidgets('web preview invites create revoke and retry sync',
      (tester) async {
    final invites = <WebPreviewInvite>[];
    var revoked = false;
    var retried = false;
    var resent = false;
    var expired = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WebPreviewInvitesDialog(
            preview: _webPreview(status: 'active'),
            listInvites: (_) async => invites,
            createInvite: (
              previewId, {
              int? ttlSeconds,
              bool singleUse = true,
              String? email,
              String role = 'admin',
            }) async {
              final invite = _webPreviewInvite(
                inviteUrl:
                    'https://preview.nienfos.com/clinica-norte/__preview/access?token=abc',
              );
              invites.add(invite);
              return invite;
            },
            revokeInvite: ({required previewId, required inviteId}) async {
              revoked = true;
              invites
                ..clear()
                ..add(_webPreviewInvite(revokedAt: '2026-07-07T00:05:00Z'));
              return invites.single;
            },
            syncInvite: ({required previewId, required inviteId}) async {
              retried = true;
              invites
                ..clear()
                ..add(_webPreviewInvite(syncStatus: 'synced'));
              return invites.single;
            },
            resendInvite: ({required previewId, required inviteId}) async {
              resent = true;
              invites
                ..clear()
                ..add(_webPreviewInvite(resendCount: 1));
              return invites.single;
            },
            expireInvite: ({required previewId, required inviteId}) async {
              expired = true;
              invites
                ..clear()
                ..add(_webPreviewInvite(expiredAt: '2026-07-07T00:06:00Z'));
              return invites.single;
            },
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('No preview invites'), findsOneWidget);

    await tester.tap(find.text('Create invite'));
    await tester.pumpAndSettle();
    expect(find.text('Invite link created'), findsOneWidget);
    expect(find.text('wpi-1'), findsOneWidget);

    await tester.ensureVisible(find.text('Retry sync'));
    await tester.tap(find.text('Retry sync'));
    await tester.pumpAndSettle();
    expect(retried, isTrue);
    expect(find.text('Sync: synced'), findsOneWidget);

    await tester.ensureVisible(find.text('Resend'));
    await tester.tap(find.text('Resend'));
    await tester.pumpAndSettle();
    expect(resent, isTrue);
    expect(find.text('Resends: 1'), findsOneWidget);

    await tester.ensureVisible(find.text('Expire'));
    await tester.tap(find.text('Expire'));
    await tester.pumpAndSettle();
    expect(expired, isTrue);
    expect(find.textContaining('Expired:'), findsOneWidget);

    await tester.ensureVisible(find.text('Revoke'));
    await tester.tap(find.text('Revoke'));
    await tester.pumpAndSettle();
    expect(revoked, isTrue);
    expect(find.textContaining('Revoked:'), findsOneWidget);
  });
}

ProjectFactoryJob _job({
  required String status,
  required int progress,
  InitialPreviewRelease? preview,
}) {
  return ProjectFactoryJob(
    jobId: 'pf-job-1',
    draftId: 'pf-draft-1',
    status: status,
    currentStep: status,
    currentPhase: status,
    progress: progress,
    message: status,
    manifestPlan: const <String, dynamic>{
      'target_path': '/projects/clinica-norte',
    },
    stepLogs: const <Map<String, dynamic>>[],
    initialPreviewRelease: preview ?? InitialPreviewRelease.empty,
    generationResult: status == 'ready'
        ? const <String, dynamic>{'target_path': '/projects/clinica-norte'}
        : null,
  );
}

ProjectFactoryJobSummary _jobSummary({
  required String status,
  required int progress,
  String? error,
  InitialPreviewRelease? preview,
}) {
  return ProjectFactoryJobSummary(
    id: 'pf-job-1',
    jobId: 'pf-job-1',
    draftId: 'pf-draft-1',
    name: 'Clinica Norte',
    slug: 'clinica-norte',
    status: status,
    currentPhase: status,
    progress: progress,
    createdAt: '2026-07-07T00:00:00Z',
    completedAt: status == 'ready' ? '2026-07-07T00:01:00Z' : null,
    projectPath: status == 'ready' ? '/projects/clinica-norte' : null,
    targetPath: '/projects/clinica-norte',
    error: error,
    message: status,
    manualNextStep: status == 'ready' ? null : 'Inspect logs',
    initialPreviewRelease: preview ?? InitialPreviewRelease.empty,
  );
}

InitialPreviewRelease _previewRelease({
  required String status,
  String? blockerText,
}) {
  return InitialPreviewRelease(
    sourceApp: 'clinica-norte',
    previewUrl: 'https://preview.nienfos.com/clinica-norte',
    apiBaseUrl: 'https://preview.nienfos.com/clinica-norte/api',
    runtimeProfile: 'preview',
    apiRuntime: 'cloudflare_preview',
    releaseChannel: 'prerelease',
    releaseTagPattern: 'android-preview-v*',
    productionReady: false,
    mockOrDemo: false,
    status: status,
    currentPhase: status == 'blocked' ? 'publish_verification' : status,
    blockerText: blockerText,
    phaseStatuses: <String, InitialPreviewReleasePhaseStatus>{
      'publish_verification': InitialPreviewReleasePhaseStatus(
        status: status == 'ready' ? 'completed' : status,
        message: blockerText ?? status,
        command: const <String>[
          'bash',
          'scripts/validate_initial_preview_release.sh',
        ],
      ),
    },
    manualCommandHints: const <String>[
      'scripts/register_installable_app.sh',
    ],
  );
}

WebPreview _webPreview({
  required String status,
  String sourceApp = 'clinica-norte',
  String? error,
}) {
  return WebPreview(
    previewId: 'wp-$sourceApp',
    sourceApp: sourceApp,
    status: status,
    previewUrl: 'https://preview.nienfos.com/$sourceApp',
    healthUrl: 'https://preview.nienfos.com/$sourceApp/__preview/health',
    plannedResources: const <Map<String, dynamic>>[
      <String, dynamic>{'kind': 'worker_script', 'status': 'planned'},
    ],
    appliedResources: status == 'active'
        ? const <Map<String, dynamic>>[
            <String, dynamic>{'kind': 'd1_database', 'status': 'created'},
          ]
        : const <Map<String, dynamic>>[],
    logs: const <Map<String, dynamic>>[],
    createdAt: '2026-07-07T00:00:00Z',
    error: error,
    inviteSyncSummary: const <String, dynamic>{
      'synced': 1,
      'failed': 0,
      'pending': 0,
      'not_deployed': 0,
    },
  );
}

WebPreviewInvite _webPreviewInvite({
  String syncStatus = 'failed',
  String? revokedAt,
  String? expiredAt,
  String? inviteUrl,
  int resendCount = 0,
}) {
  return WebPreviewInvite(
    inviteId: 'wpi-1',
    previewId: 'wp-clinica-norte',
    sourceApp: 'clinica-norte',
    appSlug: 'clinica-norte',
    createdAt: '2026-07-07T00:00:00Z',
    expiresAt: '2026-07-14T00:00:00Z',
    singleUse: true,
    syncStatus: syncStatus,
    tokenSha256: 'abc123',
    revokedAt: revokedAt,
    expiredAt: expiredAt,
    resendCount: resendCount,
    syncedAt: syncStatus == 'synced' ? '2026-07-07T00:01:00Z' : null,
    syncError: syncStatus == 'failed' ? 'D1 unavailable' : null,
    inviteUrl: inviteUrl,
  );
}
