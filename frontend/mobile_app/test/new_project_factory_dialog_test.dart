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
    expect(result!.referenceImages, isEmpty);
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
    expect(find.text('Restarted'), findsOneWidget);
  });
}

ProjectFactoryJob _job({required String status, required int progress}) {
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
    generationResult: status == 'ready'
        ? const <String, dynamic>{'target_path': '/projects/clinica-norte'}
        : null,
  );
}

ProjectFactoryJobSummary _jobSummary({
  required String status,
  required int progress,
  String? error,
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
  );
}
