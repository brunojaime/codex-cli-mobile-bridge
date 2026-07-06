import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('dev wrapper returns child unchanged when disabled', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: CodexBridgeDevModeWrapper(
          enabled: false,
          bridgeUrl: 'http://bridge.test',
          child: Text('normal app'),
        ),
      ),
    );

    expect(find.text('normal app'), findsOneWidget);
    expect(find.byTooltip('Open SDD Explorer'), findsNothing);
  });

  testWidgets('dev wrapper exposes workbench entry when enabled', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: CodexBridgeDevModeWrapper(
          enabled: true,
          bridgeUrl: 'http://bridge.test',
          child: Text('normal app'),
        ),
      ),
    );

    expect(find.text('normal app'), findsOneWidget);
    expect(find.byTooltip('Open SDD Explorer'), findsOneWidget);
  });

  testWidgets(
    'dev wrapper does not invent API config when bridge URL is empty',
    (tester) async {
      String? receivedBridgeUrl;
      await _pumpWorkbench(
        tester,
        bridgeUrl: '',
        loader: (bridgeUrl) async {
          receivedBridgeUrl = bridgeUrl;
          return null;
        },
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();

      expect(receivedBridgeUrl, '');
      expect(find.text('No SDD project found'), findsOneWidget);
    },
  );

  test('SDD client requests the configured workspace path', () async {
    final client = SddExplorerClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        expect(request.url.path, '/sdd/project');
        expect(
          request.url.queryParameters['workspace_path'],
          '/workspace/sat-catalogo-ropa',
        );
        return http.Response(jsonEncode(_projectJson()), 200);
      }),
    );

    final project = await client.getProject('/workspace/sat-catalogo-ropa');

    expect(project.workspaceName, 'Codex Bridge');
  });

  test('SDD project model parses spec SCM metadata', () {
    final project = SddProject.fromJson(_projectJson());
    final spec = project.specs.single;

    expect(spec.description, 'Read-only inspection for Bridge SDD artifacts.');
    expect(spec.lifecycleStatus, 'active');
    expect(spec.traceabilityStatus, 'linked');
    expect(spec.updatedAt, '2026-07-06T10:15:00Z');
    expect(spec.taskTotal, 2);
    expect(spec.taskCompleted, 1);
    expect(spec.taskPending, 1);
    expect(spec.lastRunState, 'queued');
    expect(spec.metadataStatus, 'stale');
    expect(spec.metadataStalePaths, contains('tasks.md'));
  });

  test('SDD client uploads intake media as multipart', () async {
    final client = SddExplorerClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sdd/specs/intake/media');
        expect(
          request.headers['content-type'],
          contains('multipart/form-data'),
        );
        expect(request.body, contains('workspace_path'));
        expect(request.body, contains('/workspace/project'));
        expect(request.body, contains('mime_type'));
        expect(request.body, contains('image/png'));
        expect(request.body, contains('screen.png'));
        return http.Response(
          jsonEncode(<String, Object?>{
            'status': 'staged',
            'workspace_path': '/workspace/project',
            'intake_item': <String, Object?>{
              'kind': 'image',
              'mime_type': 'image/png',
              'byte_size': 5,
              'filename': 'screen.png',
              'sha256':
                  '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
              'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
            },
            'staged_path': '.codex-bridge/sdd-media/abc-screen.png',
            'metadata_path': '.codex-bridge/sdd-media/abc-screen.png.json',
            'blocked': <String>[],
            'cleanup': <String>[],
            'next_actions': <String>[
              'Run visual extraction before relying on image content.',
            ],
          }),
          200,
        );
      }),
    );

    final staged = await client.uploadSpecMedia(
      workspacePath: '/workspace/project',
      attachment: const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3, 4, 5],
      ),
    );

    expect(staged.status, 'staged');
    expect(staged.filename, 'screen.png');
    expect(staged.stagedPath, '.codex-bridge/sdd-media/abc-screen.png');
    expect(staged.previewBytes, <int>[1, 2, 3, 4, 5]);
  });

  test('SDD client deletes staged intake media', () async {
    final client = SddExplorerClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sdd/specs/intake/media/delete');
        expect(request.body, contains('workspacePath'));
        expect(request.body, contains('stagedPath'));
        return http.Response(
          jsonEncode(<String, Object?>{
            'status': 'deleted',
            'workspace_path': '/workspace/project',
            'staged_path': '.codex-bridge/sdd-media/abc-screen.png',
            'lifecycle': 'deleted',
            'deleted': <String>[
              '.codex-bridge/sdd-media/abc-screen.png',
              '.codex-bridge/sdd-media/abc-screen.png.json',
            ],
            'would_delete': <String>[],
            'blocked': <String>[],
            'cleanup': <String>[],
            'next_actions': <String>[],
          }),
          200,
        );
      }),
    );

    final result = await client.deleteSpecMedia(
      workspacePath: '/workspace/project',
      stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
    );

    expect(result.status, 'deleted');
    expect(result.deleted, contains('.codex-bridge/sdd-media/abc-screen.png'));
  });

  testWidgets('workbench shows loading, error, empty, and project states', (
    tester,
  ) async {
    final pending = Completer<SddProject?>();
    await _pumpWorkbench(tester, loader: (_) => pending.future);
    _openWorkbench(tester);
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    pending.completeError(Exception('bridge unavailable'));
    await tester.pumpAndSettle();
    expect(find.textContaining('bridge unavailable'), findsOneWidget);

    await _pumpWorkbench(tester, loader: (_) async => null);
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    expect(find.text('No SDD project found'), findsOneWidget);

    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    expect(find.text('SDD Workbench'), findsOneWidget);
    expect(find.text('Overview'), findsOneWidget);
    expect(find.text('Dashboard'), findsNothing);
    expect(find.text('SDD files'), findsNothing);
    expect(find.text('Current Project Dashboard'), findsNothing);
    expect(find.text('Audit SDD'), findsNothing);
    expect(find.text('Codex Bridge'), findsWidgets);
  });

  testWidgets('workbench uses bottom navigation on narrow layout', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();

    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('Inside this spec'), findsNothing);

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    expect(find.text('Bridge Contract'), findsOneWidget);
  });

  testWidgets('workbench renders diagram source and preview fallback', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.failure('invalid Mermaid syntax'),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').last);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.textContaining('architecture/components.mmd'), findsOneWidget);
    await tester.tap(find.text('UML component diagram').first);
    await tester.pumpAndSettle();
    expect(find.text('Diagram preview failed'), findsOneWidget);
    expect(find.text('invalid Mermaid syntax'), findsOneWidget);
    expect(find.textContaining('flowchart LR'), findsOneWidget);
  });

  testWidgets('workbench opens diagram previews in full screen', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').last);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.text('UML component diagram'), findsOneWidget);
    expect(
      find.textContaining('rendered architecture/components.mmd'),
      findsNothing,
    );

    await tester.tap(find.text('UML component diagram').first);
    await tester.pumpAndSettle();

    expect(find.byTooltip('Close full screen diagram'), findsOneWidget);
    expect(
      find.textContaining('rendered architecture/components.mmd'),
      findsWidgets,
    );

    await tester.tap(find.text('Source').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('flowchart LR'), findsOneWidget);

    await tester.tap(find.text('Preview').first);
    await tester.pumpAndSettle();
    expect(
      find.textContaining('rendered architecture/components.mmd'),
      findsWidgets,
    );
  });

  testWidgets('specs tab exposes trace navigation across plans and tasks', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectWithTraceJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    expect(find.text('2/3'), findsOneWidget);

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();

    expect(find.text('SAT Catalog Flow'), findsOneWidget);
    expect(find.text('Inside this spec'), findsNothing);

    await tester.tap(find.text('SAT Catalog Flow').first);
    await tester.pumpAndSettle();

    expect(find.text('Inside this spec'), findsOneWidget);
    expect(find.text('Spec trace'), findsOneWidget);
    expect(find.text('Artifact'), findsNothing);
    await tester.tap(find.text('Spec trace').first);
    await tester.pumpAndSettle();
    expect(find.text('Plan: design-plan.md'), findsWidgets);
    expect(find.text('Plan: build-plan.md'), findsWidgets);
    expect(find.text('Tasks: design-tasks.md'), findsNothing);
    expect(find.text('Tasks: build-tasks.md'), findsNothing);

    await tester.tap(find.text('Plan: build-plan.md').first);
    await tester.pumpAndSettle();
    expect(find.text('Build Plan'), findsWidgets);
    expect(find.text('2 stages'), findsOneWidget);
    expect(find.text('Build the catalog shell'), findsWidgets);
    expect(find.text('Show details'), findsWidgets);
    expect(find.textContaining('# Build Plan'), findsNothing);
    expect(find.text('Tasks in this plan'), findsOneWidget);
    expect(find.text('1/2 tasks complete'), findsOneWidget);
    expect(find.text('Plan: build-plan.md'), findsWidgets);
    expect(find.text('Build Tasks'), findsWidgets);
    expect(find.text('Done'), findsWidgets);
    expect(find.text('Planned'), findsWidgets);
    expect(find.textContaining('# Build Tasks'), findsNothing);
  });

  testWidgets('spec tree switches task lists when selecting different plans', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectWithTreeJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('SAT Stock Reservation').first);
    await tester.pumpAndSettle();

    expect(find.text('Inside this spec'), findsOneWidget);
    expect(find.text('Spec'), findsWidgets);
    expect(find.text('Plan 1'), findsOneWidget);
    expect(find.text('Task 1'), findsNWidgets(2));
    expect(find.text('Task 3'), findsOneWidget);

    await tester.tap(find.text('Plan 1').first);
    await tester.pumpAndSettle();
    expect(find.text('Plan 1: Catalog readiness'), findsWidgets);
    expect(find.text('Task 1: Normalize catalog variants'), findsWidgets);
    expect(find.text('Task 2: Validate stock thresholds'), findsWidgets);
    expect(find.text('Task 3: Persist reservation audit'), findsNothing);

    await tester.tap(find.text('Plan 2').first);
    await tester.pumpAndSettle();
    expect(find.text('Plan 2: Checkout reservation'), findsWidgets);
    expect(find.text('Task 1: Reserve cart units'), findsWidgets);
    expect(find.text('Task 2: Reconcile payment expiry'), findsWidgets);
    expect(find.text('Task 3: Persist reservation audit'), findsWidgets);
    expect(find.text('Task 1: Normalize catalog variants'), findsNothing);
  });

  testWidgets('spec tree fallback marks incomplete trees as incomplete', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async =>
          SddProject.fromJson(_projectWithIncompleteTreeJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Governance').last);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('active · incomplete · 1 plan(s), 0 task(s)'),
      findsOneWidget,
    );
  });

  testWidgets(
    'unlinked task files remain reachable and show missing plan metadata',
    (tester) async {
      final project = _projectWithTraceJson();
      final spec = (project['specs']! as List<Map<String, dynamic>>).single;
      final taskFiles = spec['task_files']! as List<Map<String, dynamic>>;
      taskFiles.insert(0, <String, dynamic>{
        'path': 'specs/001/ops-tasks.md',
        'size_bytes': 50,
        'content': '# Ops Tasks\n\n- [ ] Wire deployment checks',
      });

      await _pumpWorkbench(
        tester,
        loader: (_) async => SddProject.fromJson(project),
        diagramRenderer: _FakeMermaidRenderer.success(),
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specs').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('SAT Catalog Flow').first);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Spec trace').first);
      await tester.pumpAndSettle();

      expect(find.text('Tasks: build-tasks.md'), findsNothing);
      expect(find.text('Tasks needing plan: ops-tasks.md'), findsOneWidget);

      await tester.tap(find.text('Tasks needing plan: ops-tasks.md').first);
      await tester.pumpAndSettle();

      expect(find.text('Ops Tasks'), findsWidgets);
      expect(find.text('Plan: Needs metadata'), findsWidgets);
      expect(find.text('0/1 tasks complete'), findsOneWidget);
    },
  );

  testWidgets(
    'named task files beside generic plans still require plan metadata',
    (tester) async {
      final project = _projectWithTraceJson();
      final spec = (project['specs']! as List<Map<String, dynamic>>).single;
      spec['plans'] = <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001/plan.md',
          'size_bytes': 50,
          'content': '# Generic Plan\n\n1. Plan the main flow.',
        },
      ];
      spec['task_files'] = <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001/ops-tasks.md',
          'size_bytes': 50,
          'content': '# Ops Tasks\n\n- [ ] Wire deployment checks',
        },
        <String, dynamic>{
          'path': 'specs/001/tasks.md',
          'size_bytes': 50,
          'content': '# Generic Tasks\n\n- [ ] Follow generic plan',
        },
      ];

      await _pumpWorkbench(
        tester,
        loader: (_) async => SddProject.fromJson(project),
        diagramRenderer: _FakeMermaidRenderer.success(),
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specs').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('SAT Catalog Flow').first);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Spec trace').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Plan: plan.md').first);
      await tester.pumpAndSettle();

      expect(find.text('Follow generic plan'), findsWidgets);
      expect(find.text('Ops Tasks'), findsNothing);

      await tester.tap(find.text('Spec trace').first);
      await tester.pumpAndSettle();
      expect(find.text('Tasks needing plan: ops-tasks.md'), findsOneWidget);

      await tester.tap(find.text('Tasks needing plan: ops-tasks.md').first);
      await tester.pumpAndSettle();

      expect(find.text('Ops Tasks'), findsWidgets);
      expect(find.text('Plan: Needs metadata'), findsWidgets);
    },
  );

  testWidgets('spec detail keeps one title and switches common spec sections', (
    tester,
  ) async {
    final project = _projectWithTraceJson();
    final spec = (project['specs']! as List<Map<String, dynamic>>).single;
    spec['title'] = 'SAT Catalog Domain';
    final specFile = spec['spec']! as Map<String, dynamic>;
    specFile['title'] = 'SAT Catalog Domain';
    specFile['content'] =
        '---\nstatus: planned\n---\n\n'
        '# SAT Catalog Domain\n\n'
        '## Intent\n\n'
        'Keep catalog data aligned with SAT fields.\n\n'
        '## Scope\n\n'
        'Cover product browsing, filtering, and checkout handoff.\n\n'
        '## Non-Goals\n\n'
        'Do not include supplier inventory sync in this spec.\n\n'
        '## Functional Requirements\n\n'
        'Product filters keep color and size options available.\n\n'
        '## Domain Rules\n\n'
        'Every garment keeps one canonical SKU.\n\n'
        '## Acceptance Criteria\n\n'
        'Catalog edits preserve existing products.';

    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(project),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('SAT Catalog Domain').first);
    await tester.pumpAndSettle();

    expect(find.text('SAT Catalog Domain'), findsOneWidget);
    expect(find.text('spec.md'), findsOneWidget);
    expect(find.text('Intent'), findsOneWidget);
    expect(find.text('Scope'), findsOneWidget);
    expect(find.text('Non-Goals'), findsOneWidget);
    expect(find.text('Functional Requirements'), findsOneWidget);
    expect(find.text('Domain Rules'), findsOneWidget);
    expect(find.text('Acceptance Criteria'), findsOneWidget);
    expect(
      find.text('Keep catalog data aligned with SAT fields.'),
      findsOneWidget,
    );
    expect(
      find.text('Cover product browsing, filtering, and checkout handoff.'),
      findsNothing,
    );

    await tester.tap(find.text('Scope'));
    await tester.pumpAndSettle();

    expect(
      find.text('Keep catalog data aligned with SAT fields.'),
      findsNothing,
    );
    expect(
      find.text('Cover product browsing, filtering, and checkout handoff.'),
      findsOneWidget,
    );
    expect(
      find.text('Do not include supplier inventory sync in this spec.'),
      findsNothing,
    );
    expect(
      find.text('Product filters keep color and size options available.'),
      findsNothing,
    );

    await tester.tap(find.text('Non-Goals'));
    await tester.pumpAndSettle();

    expect(
      find.text('Cover product browsing, filtering, and checkout handoff.'),
      findsNothing,
    );
    expect(
      find.text('Do not include supplier inventory sync in this spec.'),
      findsOneWidget,
    );
    expect(
      find.text('Product filters keep color and size options available.'),
      findsNothing,
    );

    await tester.tap(find.text('Functional Requirements'));
    await tester.pumpAndSettle();

    expect(
      find.text('Do not include supplier inventory sync in this spec.'),
      findsNothing,
    );
    expect(
      find.text('Product filters keep color and size options available.'),
      findsOneWidget,
    );
  });

  testWidgets('artifact fallbacks stay readable and heading plans do not repeat', (
    tester,
  ) async {
    final project = _projectWithTraceJson();
    final spec = (project['specs']! as List<Map<String, dynamic>>).single;
    final plans = spec['plans']! as List<Map<String, dynamic>>;
    final tasks = spec['task_files']! as List<Map<String, dynamic>>;
    plans[1]['content'] =
        '# Build Plan\n\n'
        '## Describe the app components\n\n'
        'Describe product catalog, product detail, cart, checkout, and loyalty.';
    tasks[1]['content'] =
        '# Build Tasks\n\n'
        'Review generated tasks with the implementation team.';

    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(project),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('SAT Catalog Flow').first);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Spec trace').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Plan: build-plan.md').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Show details').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('# Build Plan'), findsNothing);
    expect(
      find.text(
        'Describe product catalog, product detail, cart, checkout, and loyalty.',
      ),
      findsOneWidget,
    );

    expect(find.textContaining('# Build Tasks'), findsNothing);
    expect(
      find.text('Review generated tasks with the implementation team.'),
      findsOneWidget,
    );
  });

  testWidgets('spec diagram detail shows list before full screen preview', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectWithGovernanceJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('SAT Catalog Flow').first);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Spec trace').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').last);
    await tester.pumpAndSettle();

    expect(find.text('Diagrams in this spec'), findsOneWidget);
    expect(find.text('UML class diagram'), findsOneWidget);
    expect(find.byTooltip('Close full screen diagram'), findsNothing);
    expect(
      find.textContaining(
        'rendered specs/001-sat-catalog-flow/diagrams/domain-impact.mmd',
      ),
      findsNothing,
    );

    await tester.tap(find.text('UML class diagram').first);
    await tester.pumpAndSettle();

    expect(find.byTooltip('Close full screen diagram'), findsOneWidget);
    expect(
      find.textContaining(
        'rendered specs/001-sat-catalog-flow/diagrams/domain-impact.mmd',
      ),
      findsWidgets,
    );
  });

  testWidgets('specs tab shows SCM metadata and task progress list', (
    tester,
  ) async {
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();

    expect(find.text('Specs'), findsWidgets);
    expect(find.text('Inside this spec'), findsNothing);
    expect(find.text('Bridge Contract'), findsWidgets);
    expect(
      find.text('Read-only inspection for Bridge SDD artifacts.'),
      findsOneWidget,
    );
    expect(find.text('Active'), findsOneWidget);
    expect(find.text('1/2 tasks'), findsOneWidget);
    expect(find.text('Linked'), findsOneWidget);
    expect(find.text('2026-07-06'), findsOneWidget);
    expect(find.text('last run: queued'), findsOneWidget);
    expect(find.text('metadata stale'), findsOneWidget);

    await tester.tap(find.text('Bridge Contract').first);
    await tester.pumpAndSettle();
    expect(find.text('Inside this spec'), findsOneWidget);
    expect(find.byTooltip('Back to specs'), findsOneWidget);
  });

  testWidgets('spec intake previews and creates a text-first new spec', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'dry-run',
        specId: '005-product-export',
        metadataTitle: 'Product Export',
        metadataDescription: 'Export product catalog.',
        plannedFiles: <String>[
          'specs/005-product-export/spec.md',
          'specs/005-product-export/tasks.md',
        ],
        nextActions: <String>['Review generated spec artifacts.'],
      ),
      applyResult: const SddSpecIntakeApplyResult(
        status: 'applied',
        specId: '005-product-export',
        plannedFiles: <String>['specs/005-product-export/spec.md'],
        nextActions: <String>['Run SDD doctor before committing.'],
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Request'),
      'Necesito exportar productos',
    );
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(intakeClient.lastDraft?.mode, SddSpecIntakeMode.newSpec);
    expect(intakeClient.lastDraft?.specId, isNull);
    expect(find.widgetWithText(TextField, 'Spec id'), findsNothing);
    expect(find.widgetWithText(TextField, 'Workspace'), findsNothing);
    expect(find.text('Preview'), findsWidgets);
    expect(find.text('status: dry-run'), findsOneWidget);
    expect(find.text('title: Product Export'), findsOneWidget);

    final createButton = find.widgetWithText(FilledButton, 'Create');
    await tester.ensureVisible(createButton);
    await tester.tap(createButton);
    await tester.pumpAndSettle();

    expect(find.text('Apply'), findsOneWidget);
    expect(find.text('status: applied'), findsOneWidget);
    expect(find.textContaining('Run SDD doctor'), findsOneWidget);
  });

  testWidgets('spec intake explains unavailable media pickers', (tester) async {
    tester.view.physicalSize = const Size(360, 780);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: _FakeSpecIntakeClient(
        dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Audio'));
    expect(
      find.textContaining('Audio capture is not configured'),
      findsOneWidget,
    );
    expect(tester.getSize(find.text('Attachments')).width, greaterThan(80));

    await _tapVisible(tester, find.text('Image'));
    expect(
      find.textContaining('Image upload is not configured'),
      findsOneWidget,
    );

    await _tapVisible(tester, find.text('Structured'));
    expect(
      find.textContaining('Structured media is not configured'),
      findsOneWidget,
    );
  });

  testWidgets('spec intake stages image attachment before preview', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'dry-run',
        specId: '005-image-spec',
        plannedFiles: <String>['specs/005-image-spec/spec.md'],
        nextActions: <String>['Review generated spec artifacts.'],
      ),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
        intakeItem: <String, Object?>{
          'kind': 'image',
          'mime_type': 'image/png',
          'byte_size': 5,
          'filename': 'screen.png',
          'sha256':
              '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
          'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
        },
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3, 4, 5],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();
    expect(find.textContaining('screen.png'), findsWidgets);

    await tester.enterText(
      find.widgetWithText(TextField, 'Request'),
      'Usar la captura para describir el cambio',
    );
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(
      intakeClient.uploadedWorkspacePath,
      '/workspace/codex-cli-mobile-bridge',
    );
    expect(intakeClient.uploadedAttachment?.filename, 'screen.png');
    expect(intakeClient.lastDraft?.attachments, hasLength(1));
    expect(
      intakeClient.lastDraft?.toJson()['intakeItems'].toString(),
      contains('payload_ref'),
    );
  });

  testWidgets('spec intake marks a rectangular region on an image attachment', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
        previewBytes: <int>[1, 2, 3, 4, 5],
        intakeItem: <String, Object?>{
          'kind': 'image',
          'mime_type': 'image/png',
          'byte_size': 5,
          'filename': 'screen.png',
          'sha256':
              '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
          'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
        },
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3, 4, 5],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.byTooltip('Mark region screen.png'));
    await tester.pumpAndSettle();
    await tester.drag(
      find.byKey(const Key('sdd-media-region-canvas')),
      const Offset(80, 64),
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('sdd-media-region-apply')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Request'),
      'Usar region marcada',
    );
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    final attachments = intakeClient.lastDraft?.attachments;
    expect(attachments, hasLength(2));
    expect(attachments?.last.mediaKind, 'marked_region');
    expect(
      attachments?.last.intakeItem['source_ref'],
      attachments?.first.stagedPath,
    );
    expect(
      attachments?.last.intakeItem['payload_ref'],
      attachments?.first.stagedPath,
    );
    expect(
      attachments?.last.intakeItem['region'].toString(),
      contains('width'),
    );
    expect(
      find.textContaining('pixel crop generation is pending'),
      findsOneWidget,
    );
  });

  testWidgets(
    'spec intake generates and stages a real cropped image artifact',
    (tester) async {
      const imageBytes = <int>[1, 2, 3, 4, 5];
      final intakeClient = _FakeSpecIntakeClient(
        dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
        stagedMedia: SddStagedMediaAttachment(
          status: 'staged',
          stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
          previewBytes: imageBytes,
          intakeItem: const <String, Object?>{
            'kind': 'image',
            'mime_type': 'image/png',
            'byte_size': 5,
            'filename': 'screen.png',
            'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
          },
        ),
      );
      await _pumpWorkbench(
        tester,
        loader: (_) async => SddProject.fromJson(_projectJson()),
        diagramRenderer: _FakeMermaidRenderer.success(),
        specIntakeClient: intakeClient,
        imageCropper: (source, selection) async =>
            const SddMediaAttachmentDraft(
              filename: 'screen-crop.png',
              mimeType: 'image/png',
              bytes: <int>[137, 80, 78, 71, 1, 2, 3],
            ),
        mediaAttachmentPicker: () async => SddMediaAttachmentDraft(
          filename: 'screen.png',
          mimeType: 'image/png',
          bytes: imageBytes,
        ),
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specs').first);
      await tester.pumpAndSettle();
      await _openSpecIntake(tester);
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Image'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byTooltip('Mark region screen.png'));
      await tester.pumpAndSettle();
      await tester.drag(
        find.byKey(const Key('sdd-media-region-canvas')),
        const Offset(70, 50),
      );
      await tester.pump();
      await tester.tap(find.byKey(const Key('sdd-media-crop-apply')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextField, 'Request'),
        'Usar crop generado',
      );
      await tester.pump();
      final previewButton = find.widgetWithText(FilledButton, 'Preview');
      await tester.ensureVisible(previewButton);
      await tester.tap(previewButton);
      await tester.pumpAndSettle();

      final attachments = intakeClient.lastDraft?.attachments;
      expect(intakeClient.uploadedKind, 'crop');
      expect(intakeClient.uploadedAttachment?.filename, 'screen-crop.png');
      expect(intakeClient.uploadedAttachment?.mimeType, 'image/png');
      expect(intakeClient.uploadedAttachment?.bytes, isNotEmpty);
      expect(
        intakeClient.uploadedSourceRef,
        '.codex-bridge/sdd-media/abc-screen.png',
      );
      expect(intakeClient.uploadedRegion, containsPair('width', isA<int>()));
      expect(attachments, hasLength(2));
      expect(attachments?.last.mediaKind, 'crop');
      expect(
        attachments?.last.intakeItem['source_ref'],
        attachments?.first.stagedPath,
      );
      expect(find.textContaining('screen-crop.png'), findsWidgets);
    },
  );

  testWidgets(
    'spec intake blocks region selection without image preview bytes',
    (tester) async {
      final intakeClient = _FakeSpecIntakeClient(
        dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
        stagedMedia: const SddStagedMediaAttachment(
          status: 'staged',
          stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
          intakeItem: <String, Object?>{
            'kind': 'image',
            'mime_type': 'image/png',
            'byte_size': 5,
            'filename': 'screen.png',
            'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
          },
        ),
      );
      await _pumpWorkbench(
        tester,
        loader: (_) async => SddProject.fromJson(_projectJson()),
        diagramRenderer: _FakeMermaidRenderer.success(),
        specIntakeClient: intakeClient,
        mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
          filename: 'screen.png',
          mimeType: 'image/png',
          bytes: <int>[1, 2, 3],
        ),
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specs').first);
      await tester.pumpAndSettle();
      await _openSpecIntake(tester);
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Image'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byTooltip('Mark region screen.png'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('blocked: image preview unavailable'),
        findsOneWidget,
      );
    },
  );

  testWidgets('spec intake validates empty native region before submit', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
        previewBytes: <int>[1, 2, 3, 4, 5],
        intakeItem: <String, Object?>{
          'kind': 'image',
          'mime_type': 'image/png',
          'byte_size': 5,
          'filename': 'screen.png',
          'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
        },
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.byTooltip('Mark region screen.png'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sdd-media-region-apply')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('sdd-media-region-error')), findsOneWidget);
    expect(find.textContaining('Draw a non-empty region'), findsOneWidget);
  });

  testWidgets('spec intake can remove a staged attachment from the draft', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
        intakeItem: <String, Object?>{
          'kind': 'image',
          'mime_type': 'image/png',
          'byte_size': 5,
          'filename': 'screen.png',
          'sha256':
              '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
          'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
        },
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3, 4, 5],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.byTooltip('Remove attachment screen.png'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'x');
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(intakeClient.lastDraft?.attachments, isEmpty);
    expect(find.textContaining('deleted: screen.png'), findsOneWidget);
  });

  testWidgets('spec intake keeps attachment visible when backend delete blocks', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-screen.png',
        intakeItem: <String, Object?>{
          'kind': 'image',
          'mime_type': 'image/png',
          'byte_size': 5,
          'filename': 'screen.png',
          'sha256':
              '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
          'payload_ref': '.codex-bridge/sdd-media/abc-screen.png',
        },
      ),
      deleteError: Exception('staged media has already been consumed'),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.png',
        mimeType: 'image/png',
        bytes: <int>[1, 2, 3, 4, 5],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.byTooltip('Remove attachment screen.png'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('staged media has already been consumed'),
      findsOneWidget,
    );
    expect(find.textContaining('screen.png'), findsWidgets);
  });

  testWidgets('spec intake stages audio attachment before preview', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      stagedMedia: const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/abc-note.m4a',
        intakeItem: <String, Object?>{
          'kind': 'audio',
          'mime_type': 'audio/mp4',
          'byte_size': 5,
          'filename': 'note.m4a',
          'duration_ms': 1000,
          'sha256':
              '2d4566582844690f8634a8b2534ea5221560038c6c0650c99140759bad603ae2',
          'payload_ref': '.codex-bridge/sdd-media/abc-note.m4a',
        },
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      audioAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'note.m4a',
        mimeType: 'audio/mp4',
        bytes: <int>[1, 2, 3, 4, 5],
        durationMs: 1000,
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Audio'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'Audio');
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(intakeClient.uploadedKind, 'audio');
    expect(intakeClient.uploadedAttachment?.durationMs, 1000);
    expect(intakeClient.lastDraft?.attachments.single.mediaKind, 'audio');
  });

  testWidgets('spec intake accepts host-injected structured attachment', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      structuredAttachmentPicker: () async => const SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/marked.png',
        intakeItem: <String, Object?>{
          'kind': 'marked_region',
          'mime_type': 'image/png',
          'byte_size': 6,
          'filename': 'marked.png',
          'source_ref': '.codex-bridge/sdd-media/source.png',
          'payload_ref': '.codex-bridge/sdd-media/marked.png',
          'region': <String, Object?>{
            'x': 1,
            'y': 2,
            'width': 30,
            'height': 40,
          },
        },
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.text('Structured'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'Region');
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(
      intakeClient.lastDraft?.attachments.single.mediaKind,
      'marked_region',
    );
    expect(
      intakeClient.lastDraft?.toJson()['intakeItems'].toString(),
      contains('source_ref'),
    );
  });

  testWidgets('spec intake carries host-injected image sequence attachments', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      structuredAttachmentPicker: () async => const SddStagedMediaAttachment(
        status: 'staged',
        intakeItem: <String, Object?>{
          'kind': 'image_sequence',
          'mime_type': 'application/json',
          'byte_size': 0,
          'filename': 'walkthrough-sequence.json',
          'frame_count': 2,
          'audio_track_count': 1,
          'references': <String>[
            '.codex-bridge/sdd-media/frame-001.png',
            '.codex-bridge/sdd-media/frame-002.png',
            '.codex-bridge/sdd-media/narration.m4a',
          ],
          'timeline_ms': <int>[0, 1200],
        },
        nextActions: <String>[
          'Sequence metadata is ready for dry-run validation.',
        ],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.text('Structured'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Request'),
      'Crear spec desde walkthrough',
    );
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(find.textContaining('walkthrough-sequence.json'), findsWidgets);
    expect(
      intakeClient.lastDraft?.attachments.single.mediaKind,
      'image_sequence',
    );
    expect(
      intakeClient.lastDraft?.toJson()['intakeItems'].toString(),
      contains('timeline_ms'),
    );
  });

  testWidgets('spec intake renders media upload errors', (tester) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(status: 'dry-run'),
      uploadError: Exception('unsupported_image_mime_type'),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
      mediaAttachmentPicker: () async => const SddMediaAttachmentDraft(
        filename: 'screen.gif',
        mimeType: 'image/gif',
        bytes: <int>[1, 2, 3],
      ),
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.text('Image'));
    await tester.pumpAndSettle();

    expect(find.textContaining('unsupported_image_mime_type'), findsOneWidget);
  });

  testWidgets('spec intake queues reviews and applies existing spec job', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'dry-run',
        specId: '001-codex-bridge-sdd-wrapper',
        selectedArtifact: 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
        plannedFiles: <String>['specs/001-codex-bridge-sdd-wrapper/tasks.md'],
        nextActions: <String>['Queue a sandboxed Codex job.'],
      ),
      applyResult: const SddSpecIntakeApplyResult(
        status: 'queued',
        specId: '001-codex-bridge-sdd-wrapper',
        job: SddCodexJobStatus(
          id: 'sddjob-001',
          status: 'queued',
          targetArtifact: 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
          sandboxRoot: '.codex-bridge/sdd-jobs/sddjob-001/sandbox',
          activity: SddActivitySnapshot(
            state: 'queued',
            events: <SddActivityEvent>[
              SddActivityEvent(
                state: 'queued',
                status: 'active',
                label: 'Job queued',
              ),
            ],
          ),
        ),
      ),
      runJob: const SddCodexJobStatus(
        id: 'sddjob-001',
        status: 'completed',
        targetArtifact: 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
      ),
      review: const SddCodexJobReview(
        status: 'ready',
        validationStatus: 'pass',
        changedFiles: <SddGeneratedChange>[
          SddGeneratedChange(
            path: 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
            changeType: 'modified',
            patchPath: '.codex-bridge/sdd-jobs/sddjob-001/review/tasks.diff',
          ),
        ],
        nextActions: <String>['Apply reviewed generated changes when ready.'],
      ),
      applyJob: const SddCodexJobApplyResult(
        status: 'applied',
        applied: <String>['specs/001-codex-bridge-sdd-wrapper/tasks.md'],
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Existing').first);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Request'),
      'Actualizar tasks',
    );
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();
    final queueButton = find.widgetWithText(FilledButton, 'Queue job');
    await tester.ensureVisible(queueButton);
    await tester.tap(queueButton);
    await tester.pumpAndSettle();

    expect(intakeClient.lastDraft?.mode, SddSpecIntakeMode.existingSpec);
    expect(find.text('status: queued'), findsWidgets);
    expect(find.text('Activity · queued'), findsOneWidget);

    await _tapIntakeJobAction(tester, 'Run job');
    expect(find.text('status: completed'), findsOneWidget);

    await _tapIntakeJobAction(tester, 'Review');
    expect(find.text('validation: pass'), findsOneWidget);

    await _tapIntakeJobAction(tester, 'Apply reviewed');
    expect(find.text('Reviewed apply'), findsOneWidget);
    expect(find.text('status: applied'), findsWidgets);
  });

  testWidgets('spec intake refreshes and cancels queued activity', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'dry-run',
        specId: '001-codex-bridge-sdd-wrapper',
        selectedArtifact: 'specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
      applyResult: const SddSpecIntakeApplyResult(
        status: 'queued',
        specId: '001-codex-bridge-sdd-wrapper',
        job: SddCodexJobStatus(
          id: 'sddjob-activity',
          status: 'queued',
          activity: SddActivitySnapshot(
            state: 'queued',
            events: <SddActivityEvent>[
              SddActivityEvent(
                state: 'queued',
                status: 'active',
                label: 'Job queued',
              ),
            ],
          ),
        ),
      ),
      activity: const SddActivitySnapshot(
        state: 'running-codex',
        jobId: 'sddjob-activity',
        events: <SddActivityEvent>[
          SddActivityEvent(
            state: 'running-codex',
            status: 'active',
            label: 'Codex running',
          ),
        ],
      ),
      cancelJob: const SddCodexJobStatus(
        id: 'sddjob-activity',
        status: 'cancelled',
        activity: SddActivitySnapshot(
          state: 'cancelled',
          events: <SddActivityEvent>[
            SddActivityEvent(
              state: 'cancelled',
              status: 'blocked',
              label: 'Job cancelled',
            ),
          ],
        ),
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Existing').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'Editar');
    await tester.pump();
    await _tapVisible(tester, find.widgetWithText(FilledButton, 'Preview'));
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.widgetWithText(FilledButton, 'Queue job'));
    await tester.pumpAndSettle();

    expect(find.text('Activity · queued'), findsOneWidget);
    await _tapIntakeJobAction(tester, 'Refresh');
    expect(intakeClient.activityRequests, 1);
    expect(find.text('Activity · running-codex'), findsOneWidget);
    expect(find.text('Codex running'), findsOneWidget);

    await _tapIntakeJobAction(tester, 'Cancel');
    expect(intakeClient.cancelRequests, 1);
    expect(find.text('Activity · cancelled'), findsOneWidget);
  });

  testWidgets('spec intake retries a failed sandbox job as a new queued job', (
    tester,
  ) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'dry-run',
        specId: '001-codex-bridge-sdd-wrapper',
        selectedArtifact: 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
      ),
      applyResult: const SddSpecIntakeApplyResult(
        status: 'queued',
        specId: '001-codex-bridge-sdd-wrapper',
        job: SddCodexJobStatus(id: 'sddjob-retry', status: 'queued'),
      ),
      runJob: const SddCodexJobStatus(
        id: 'sddjob-retry',
        status: 'failed',
        blockedReasons: <String>['Codex CLI exited with code 2.'],
        activity: SddActivitySnapshot(
          state: 'failed',
          events: <SddActivityEvent>[
            SddActivityEvent(
              state: 'failed',
              status: 'failed',
              label: 'Failed',
            ),
          ],
        ),
      ),
      retryJob: const SddCodexJobRetryResult(
        status: 'queued',
        originalJobId: 'sddjob-retry',
        retryJobId: 'sddjob-retry-01',
        retryEligible: true,
        copiedReferences: <String>['request.json', 'context-pack.json'],
        job: SddCodexJobStatus(
          id: 'sddjob-retry-01',
          status: 'queued',
          activity: SddActivitySnapshot(
            state: 'queued',
            jobId: 'sddjob-retry-01',
            events: <SddActivityEvent>[
              SddActivityEvent(
                state: 'retry-created',
                status: 'completed',
                label: 'Retry job created',
              ),
              SddActivityEvent(
                state: 'queued',
                status: 'active',
                label: 'Retry queued',
              ),
            ],
          ),
        ),
        activity: SddActivitySnapshot(
          state: 'queued',
          jobId: 'sddjob-retry-01',
          events: <SddActivityEvent>[
            SddActivityEvent(
              state: 'retry-created',
              status: 'completed',
              label: 'Retry job created',
            ),
            SddActivityEvent(
              state: 'queued',
              status: 'active',
              label: 'Retry queued',
            ),
          ],
        ),
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Existing').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'Editar');
    await tester.pump();
    await _tapVisible(tester, find.widgetWithText(FilledButton, 'Preview'));
    await tester.pumpAndSettle();
    await _tapVisible(tester, find.widgetWithText(FilledButton, 'Queue job'));
    await tester.pumpAndSettle();
    await _tapIntakeJobAction(tester, 'Run job');

    expect(find.text('Activity · failed'), findsOneWidget);
    await _tapIntakeJobAction(tester, 'Retry');

    expect(intakeClient.retryRequests, 1);
    expect(find.text('Activity · queued'), findsOneWidget);
    expect(find.text('Retry job created'), findsOneWidget);
    expect(find.text('status: queued'), findsWidgets);
  });

  testWidgets('spec intake renders blocked dry-run errors', (tester) async {
    final intakeClient = _FakeSpecIntakeClient(
      dryRunPlan: const SddSpecIntakePlan(
        status: 'blocked',
        blocked: <String>['spec_target.spec_id: invalid_spec_id'],
        rejectedMedia: <String>['intake_items[0]: missing text'],
        nextActions: <String>['Fix validation errors before writing.'],
      ),
    );
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      specIntakeClient: intakeClient,
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await _openSpecIntake(tester);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Request'), 'x');
    await tester.pump();
    final previewButton = find.widgetWithText(FilledButton, 'Preview');
    await tester.ensureVisible(previewButton);
    await tester.tap(previewButton);
    await tester.pumpAndSettle();

    expect(find.text('status: blocked'), findsOneWidget);
    expect(find.text('spec_target.spec_id: invalid_spec_id'), findsOneWidget);
    expect(find.text('intake_items[0]: missing text'), findsOneWidget);
  });

  testWidgets(
    'workbench exposes governance baselines traceability and impact',
    (tester) async {
      await _pumpWorkbench(
        tester,
        loader: (_) async => SddProject.fromJson(_projectWithGovernanceJson()),
        diagramRenderer: _FakeMermaidRenderer.success(),
      );
      _openWorkbench(tester);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Specs').first);
      await tester.pumpAndSettle();

      await tester.tap(find.text('SAT Catalog Flow').first);
      await tester.pumpAndSettle();

      expect(find.text('Planned'), findsOneWidget);
      expect(find.text('Linked'), findsOneWidget);

      await tester.tap(find.text('Governance').first);
      await tester.pumpAndSettle();

      expect(
        find.text('Architecture, domain, and data baselines'),
        findsOneWidget,
      );
      expect(find.text('Traceability matrix'), findsOneWidget);
      expect(
        find.text('Architecture, domain, and data impact queue'),
        findsOneWidget,
      );
      expect(find.textContaining('architecture/components.mmd'), findsWidgets);
      expect(
        find.textContaining('Domain baseline files are not loaded'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Data baseline files are not loaded'),
        findsOneWidget,
      );
      expect(find.textContaining('domain-impact'), findsOneWidget);
    },
  );

  test('SDD spec model parses plural plan and task history', () {
    final project = SddProject.fromJson(_projectWithTraceJson());
    final spec = project.specs.single;

    expect(spec.allPlanFiles.map((file) => file.path), <String>[
      'specs/001-sat-catalog-flow/design-plan.md',
      'specs/001-sat-catalog-flow/build-plan.md',
    ]);
    expect(spec.allTaskFiles.map((file) => file.path), <String>[
      'specs/001-sat-catalog-flow/design-tasks.md',
      'specs/001-sat-catalog-flow/build-tasks.md',
    ]);
  });

  test('feedback target metadata is scoped to SDD artifact context', () {
    const target = SddFeedbackTarget(
      workspacePath: '/workspace/project',
      artifactType: 'diagram',
      artifactPath: 'architecture/components.mmd',
      artifactTitle: 'components',
      sourceExcerpt: 'flowchart LR\nA --> B',
      diagramType: 'flowchart',
      diagramScope: 'architecture',
    );

    expect(target.feedbackKind, 'sdd.diagram');
    expect(
      target.toContextMetadata()['sdd'],
      isA<Map<String, Object?>>()
          .having(
            (value) => value['workspacePath'],
            'workspace',
            '/workspace/project',
          )
          .having(
            (value) => value['targetWorkspacePath'],
            'target workspace',
            '/workspace/project',
          )
          .having(
            (value) => value['invocationSource'],
            'invocation source',
            'codex_bridge_workbench',
          )
          .having(
            (value) => value['releaseTarget'],
            'release target',
            'target_workspace',
          )
          .having(
            (value) => value['artifactPath'],
            'path',
            'architecture/components.mmd',
          )
          .having((value) => value['diagramScope'], 'scope', 'architecture'),
    );
  });

  test('Codex action prompt includes action, context, and linked feedback', () {
    final prompt = buildSddCodexActionPrompt(
      const SddCodexActionRequest(
        kind: SddCodexActionKind.addressFeedback,
        linkedFeedbackIds: <String>['feedback-1'],
        target: SddFeedbackTarget(
          workspacePath: '/workspace/project',
          artifactType: 'spec',
          artifactPath: 'specs/001/spec.md',
          artifactTitle: 'Spec',
          sourceExcerpt: '# Spec',
          specId: '001',
          specTitle: 'Spec',
        ),
      ),
    );

    expect(prompt, contains('Action kind: sdd.address_feedback'));
    expect(prompt, contains('workspace_path: /workspace/project'));
    expect(prompt, contains('target_workspace_path: /workspace/project'));
    expect(prompt, contains('release_target: target_workspace'));
    expect(
      prompt,
      contains(
        'For release, deploy, publish, or installable build requests, use '
        'target_workspace_path as the target repository by default.',
      ),
    );
    expect(
      prompt,
      contains(
        'Do not release the Bridge/Workbench host repository unless the user '
        'explicitly asks for that host app.',
      ),
    );
    expect(prompt, contains('artifact_path: specs/001/spec.md'));
    expect(prompt, contains('linked_feedback_ids:'));
    expect(prompt, contains('feedback-1'));
  });

  test('Codex action draft defaults to target workspace', () {
    const request = SddCodexActionRequest(
      kind: SddCodexActionKind.auditSdd,
      target: SddFeedbackTarget(
        workspacePath: '/workspace/project',
        artifactType: 'workspace',
        artifactPath: 'codex-bridge.yaml',
        artifactTitle: 'Project SDD',
        sourceExcerpt: '',
      ),
    );

    final defaultDraft = SddCodexActionDraft(
      request: request,
      prompt: 'Audit SDD',
    );
    final metaDraft = SddCodexActionDraft(
      request: request,
      prompt: 'Audit Workbench',
      executionWorkspacePath: '/workspace/codex-cli-mobile-bridge',
      executionWorkspaceLabel: 'Codex Bridge Workbench',
    );

    expect(defaultDraft.executionWorkspacePath, '/workspace/project');
    expect(
      metaDraft.executionWorkspacePath,
      '/workspace/codex-cli-mobile-bridge',
    );
    expect(metaDraft.executionWorkspaceLabel, 'Codex Bridge Workbench');
  });

  testWidgets('Codex action composer can route execution to meta workspace', (
    tester,
  ) async {
    SddCodexActionDraft? submittedDraft;
    await _pumpWorkbench(
      tester,
      loader: (_) async => SddProject.fromJson(_projectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      metaWorkspacePath: '/workspace/codex-cli-mobile-bridge',
      actionSubmitter: (_, draft) async {
        submittedDraft = draft;
        return const SddCodexActionSubmissionResult(
          jobId: 'job-1',
          sessionId: 'session-1',
        );
      },
    );
    _openWorkbench(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Bridge Contract').first);
    await tester.pumpAndSettle();

    final codexButton = find.text('Codex').first;
    await tester.ensureVisible(codexButton);
    await tester.tap(codexButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Refine spec.md').first);
    await tester.pumpAndSettle();
    expect(find.text('Run against Workbench platform repo'), findsOneWidget);
    expect(find.text('Execution target: Current project'), findsOneWidget);

    await tester.tap(find.byType(SwitchListTile).first);
    await tester.pumpAndSettle();
    expect(
      find.text('Execution target: Codex Bridge Workbench'),
      findsOneWidget,
    );

    await tester.tap(find.text('Submit to Codex'));
    await tester.pumpAndSettle();

    expect(
      submittedDraft?.executionWorkspacePath,
      '/workspace/codex-cli-mobile-bridge',
    );
  });

  testWidgets('production Mermaid renderer uses package-local asset path', (
    tester,
  ) async {
    final result =
        await WebViewMermaidDiagramRenderer(
          assetBundle: _FakeMermaidAssetBundle('''
window.mermaid = {
  initialize: function() {},
  render: async function() { return { svg: '<svg></svg>' }; }
};
'''),
        ).render(
          const SddDiagram(
            path: 'architecture/components.mmd',
            sizeBytes: 22,
            diagramType: 'flowchart',
            scope: 'architecture',
            content: 'flowchart LR\nA --> B',
          ),
        );

    expect(result.isSuccess, isTrue);
    expect(result.preview, isA<MermaidWebViewPreview>());
  });

  test('Mermaid preview HTML base64-encodes suspicious diagram source', () {
    const maliciousSource = '''
flowchart LR
  A["</script><script>window.pwned = true</script>"]
  B["<img src=x onerror=alert(1)>"]
  C["quotes ' \\" ` and unicode ñ"]
  A --> B
  click B "https://example.com" "external"
''';

    final html = buildMermaidPreviewHtml(
      mermaidJs: 'window.mermaid = {};',
      source: maliciousSource,
    );

    expect(html, contains(base64Encode(utf8.encode(maliciousSource))));
    expect(html, isNot(contains(maliciousSource)));
    expect(html, isNot(contains('</script><script>window.pwned')));
    expect(html, isNot(contains('<img src=x onerror=alert(1)>')));
    expect(html, isNot(contains('https://example.com')));
    expect(html, contains("securityLevel: 'strict'"));
    expect(html, contains("connect-src 'none'"));
  });

  test(
    'custom UML component renderer emits integrated vector notation',
    () async {
      const source = '''
flowchart LR
  Browser["<<component>> Client UI"]
  subgraph Core["Dominio de catalogo y administracion"]
    direction LR
    Api["<<component>> Catalog API"]
    Admin["<<component>> Admin Console"]
  end
  Db[("MySQL")]
  Browser -->|HTTPS API| Api
  Api -->|TCP/IP| Db
  %% uml-interface: HTTPS API consumer=Browser provider=Api
''';

      final html = buildMermaidPreviewHtml(
        mermaidJs: _mermaidFallbackStub,
        source: source,
        diagramPath: 'architecture/components.mmd',
        diagramType: 'flowchart',
      );
      final result = await _renderPreviewHtmlWithNode(html);
      final svg = result.diagramHtml;

      expect(result.usedMermaidFallback, isFalse);
      expect(result.errorText, isEmpty);
      expect(svg, contains('<svg class="uml-canvas"'));
      expect(svg, contains('Dominio de catalogo y administracion'));
      expect(svg, contains('Client UI'));
      expect(svg, contains('Catalog API'));
      expect(svg, contains('Admin Console'));
      expect(svg, contains('MySQL'));
      expect(svg, contains('class="component-glyph"'));
      expect(svg, isNot(contains('class="uml-component-glyph"')));
      expect(svg, isNot(contains('<image')));
      expect(svg, contains('class="uml-interface"'));
      expect(svg, contains('<circle cx="-9" cy="0" r="8"'));
      expect(svg, contains('<path d="M 14 -9 A 9 9 0 1 0 14 9"'));
      expect(svg, contains('HTTPS API'));

      final browser = _svgRectForNode(svg, 'Browser');
      final api = _svgRectForNode(svg, 'Api');
      final browserGlyph = _svgGlyphForNode(svg, 'Browser');
      expect(api.x, greaterThan(browser.x + browser.width));
      expect(browserGlyph.x, greaterThan(browser.x));
      expect(browserGlyph.x + 24, lessThan(browser.x + browser.width));
      expect(browserGlyph.y, greaterThan(browser.y));
      expect(browserGlyph.y + 22, lessThan(browser.y + browser.height));
    },
  );

  test(
    'non-component Mermaid diagrams use the Mermaid fallback path',
    () async {
      const source = '''
sequenceDiagram
  participant Client
  participant API
  Client->>API: HTTPS
''';

      final html = buildMermaidPreviewHtml(
        mermaidJs: _mermaidFallbackStub,
        source: source,
        diagramPath: 'architecture/sequence.mmd',
        diagramType: 'sequence',
      );
      final result = await _renderPreviewHtmlWithNode(html);

      expect(result.usedMermaidFallback, isTrue);
      expect(result.errorText, isEmpty);
      expect(result.diagramHtml, contains('<svg class="fallback-mermaid"'));
      expect(result.diagramHtml, isNot(contains('class="uml-canvas"')));
    },
  );

  test('SAT-sized component diagram renders as responsive UML SVG', () async {
    final html = buildMermaidPreviewHtml(
      mermaidJs: _mermaidFallbackStub,
      source: _satSizedComponentDiagramSource,
      diagramPath: 'architecture/components.mmd',
      diagramType: 'flowchart',
    );
    final result = await _renderPreviewHtmlWithNode(html, viewportWidth: 375);
    final svg = result.diagramHtml;
    final svgTag = RegExp(
      r'<svg class="uml-canvas"[^>]+>',
    ).firstMatch(svg)?.group(0);
    final svgSize = _svgRootSize(svg);

    expect(result.usedMermaidFallback, isFalse);
    expect(result.errorText, isEmpty);
    expect(svgTag, isNotNull);
    expect(svgTag, contains('viewBox="0 0 '));
    expect(svgSize.width, lessThan(900));
    expect(svgSize.height, greaterThan(svgSize.width));
    expect(svg, contains('Sistema SAT Catalogo Ropa'));
    expect(svg, contains('Comprador SAT'));
    expect(svg, contains('Sistema externo:'));
    expect(svg, contains('WhatsApp'));
    expect(svg, isNot(contains('mantenimiento catalogo')));
    expect(_svgClassCount(svg, 'component-glyph'), 10);
    expect(_svgClassCount(svg, 'uml-interface'), 12);
    expect(_svgClassCount(svg, 'uml-edge-label'), 0);
    _expectComponentTextFits(svg);
    expect(html, contains('#diagram svg.uml-canvas'));
    expect(html, contains('max-width: 100%;'));
    expect(html, contains('width: 100%;'));
    expect(html, isNot(contains('width: 100vw;')));
    expect(html, isNot(contains('max-width: none;')));
    expect(html, isNot(contains('width: auto;')));
  });

  test(
    'SAT-sized component diagram preserves edge labels on wide layouts',
    () async {
      final html = buildMermaidPreviewHtml(
        mermaidJs: _mermaidFallbackStub,
        source: _satSizedComponentDiagramSource,
        diagramPath: 'architecture/components.mmd',
        diagramType: 'flowchart',
      );
      final result = await _renderPreviewHtmlWithNode(
        html,
        viewportWidth: 1366,
      );
      final svg = result.diagramHtml;
      final svgSize = _svgRootSize(svg);

      expect(result.usedMermaidFallback, isFalse);
      expect(result.errorText, isEmpty);
      expect(svgSize.width, greaterThan(900));
      expect(svgSize.width, greaterThan(svgSize.height));
      expect(_svgClassCount(svg, 'component-glyph'), 10);
      expect(_svgClassCount(svg, 'uml-interface'), 12);
      expect(_svgClassCount(svg, 'uml-edge-label'), greaterThanOrEqualTo(12));
      expect(svg, contains('mantenimiento catalogo'));
      expect(svg, contains('HTTP preview checkout'));
      _expectComponentTextFits(svg);
    },
  );
}

const _mermaidFallbackStub = '''
globalThis.mermaidFallbackUsed = false;
globalThis.mermaid = {
  initialize: function() {},
  render: async function() {
    globalThis.mermaidFallbackUsed = true;
    return { svg: '<svg class="fallback-mermaid"><text>fallback</text></svg>' };
  }
};
''';

const _satSizedComponentDiagramSource = '''
flowchart LR
    Customer["Comprador SAT"]
    StaffUser["Personal SAT"]
    WhatsApp["Sistema externo: WhatsApp"]

    subgraph SATSystem["Sistema SAT Catalogo Ropa"]
        direction LR

        subgraph MobileBoundary["App catalogo Flutter"]
            direction TB
            CatalogUI["<<component>> Navegacion de catalogo"]
            ProductDetail["<<component>> Ficha de producto"]
            CartState["<<component>> Carrito y totales"]
            CheckoutClient["<<component>> Preparacion de pedido"]
            AdminConsole["<<component>> Panel interno SAT"]
        end

        subgraph DomainBoundary["Dominio de catalogo y administracion"]
            direction TB
            ProductCatalog["<<component>> Catalogo de prendas"]
            StaffAccounts["<<component>> Usuarios y roles"]
            LoyaltyRules["<<component>> Reglas de puntos y promociones"]
        end

        subgraph BackendBoundary["API SAT"]
            direction TB
            ProductApi["<<component>> Consulta de productos"]
            CheckoutApi["<<component>> Vista previa de checkout"]
        end

        subgraph PersistenceBoundary["Persistencia SAT"]
            direction TB
            CatalogDatabase[("Base de datos SAT\\nclientes, productos, carrito y pedidos")]
        end
    end

    Customer -->|usa catalogo| CatalogUI
    StaffUser -->|administra| AdminConsole
    CatalogUI -->|seleccion de prenda| ProductDetail
    CatalogUI -->|consulta de catalogo local| ProductCatalog
    ProductDetail -->|agregar item| CartState
    CartState -->|preparar pedido| CheckoutClient
    CheckoutClient -->|HTTP preview checkout| CheckoutApi
    CheckoutClient -->|HTTPS deep link| WhatsApp
    ProductApi -->|consulta de catalogo| ProductCatalog
    ProductApi -->|TCP/IP catalogo persistido| CatalogDatabase
    CheckoutApi -->|TCP/IP pedido persistido| CatalogDatabase
    AdminConsole -->|mantenimiento catalogo| ProductCatalog
    AdminConsole -->|gestion de usuarios| StaffAccounts
    AdminConsole -->|gestion de promociones| LoyaltyRules

    %% uml-interface: seleccion de prenda consumer=CatalogUI provider=ProductDetail
    %% uml-interface: consulta de catalogo local consumer=CatalogUI provider=ProductCatalog
    %% uml-interface: agregar item consumer=ProductDetail provider=CartState
    %% uml-interface: preparar pedido consumer=CartState provider=CheckoutClient
    %% uml-interface: HTTP preview checkout consumer=CheckoutClient provider=CheckoutApi
    %% uml-interface: HTTPS deep link consumer=CheckoutClient provider=WhatsApp
    %% uml-interface: consulta de catalogo consumer=ProductApi provider=ProductCatalog
    %% uml-interface: TCP/IP catalogo persistido consumer=ProductApi provider=CatalogDatabase
    %% uml-interface: TCP/IP pedido persistido consumer=CheckoutApi provider=CatalogDatabase
    %% uml-interface: mantenimiento catalogo consumer=AdminConsole provider=ProductCatalog
    %% uml-interface: gestion de usuarios consumer=AdminConsole provider=StaffAccounts
    %% uml-interface: gestion de promociones consumer=AdminConsole provider=LoyaltyRules
''';

Future<_RenderedPreview> _renderPreviewHtmlWithNode(
  String html, {
  int viewportWidth = 1024,
}) async {
  final nodeCheck = await Process.run('node', const <String>['--version']);
  if (nodeCheck.exitCode != 0) {
    markTestSkipped('Node.js is required to execute the generated renderer.');
  }

  final scripts = RegExp(
    r'<script>\s*([\s\S]*?)\s*</script>',
  ).allMatches(html).map((match) => match.group(1)!).toList();
  expect(scripts, hasLength(2));

  final tempDir = await Directory.systemTemp.createTemp(
    'codex_workbench_renderer_test_',
  );
  final scriptFile = File('${tempDir.path}/render_preview.js');
  try {
    await scriptFile.writeAsString('''
const { TextDecoder } = require('util');
const scripts = ${jsonEncode(scripts)};
const elementChildren = [];
const diagramElement = {
  style: {},
  innerHTML: '',
  querySelector: function() { return null; }
};
const errorElement = {
  style: {},
  textContent: ''
};

globalThis.window = globalThis;
globalThis.innerWidth = $viewportWidth;
globalThis.TextDecoder = TextDecoder;
globalThis.atob = function(value) {
  return Buffer.from(value, 'base64').toString('binary');
};
globalThis.document = {
  getElementById: function(id) {
    return id === 'diagram' ? diagramElement : errorElement;
  },
  createElementNS: function(_namespace, name) {
    return {
      name,
      attributes: {},
      children: [],
      textContent: '',
      setAttribute: function(key, value) {
        this.attributes[key] = String(value);
      },
      appendChild: function(child) {
        this.children.push(child);
        elementChildren.push(child);
      },
      querySelector: function() { return null; },
      querySelectorAll: function() { return []; }
    };
  }
};

(async () => {
  for (const script of scripts) {
    (0, eval)(script);
  }
  await new Promise((resolve) => setTimeout(resolve, 30));
  process.stdout.write(JSON.stringify({
    diagramHtml: diagramElement.innerHTML,
    errorText: errorElement.textContent,
    usedMermaidFallback: globalThis.mermaidFallbackUsed === true
  }));
})().catch((error) => {
  process.stderr.write(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
''');

    final run = await Process.run('node', <String>[scriptFile.path]);
    if (run.exitCode != 0) {
      fail('Node renderer failed:\n${run.stderr}\n${run.stdout}');
    }
    final output = (run.stdout as String).trim();
    expect(output, isNotEmpty);
    return _RenderedPreview.fromJson(
      jsonDecode(output) as Map<String, Object?>,
    );
  } finally {
    await tempDir.delete(recursive: true);
  }
}

_SvgRect _svgRectForNode(String svg, String id) {
  final match = RegExp(
    '<g id="uml-node-${RegExp.escape(id)}">[\\s\\S]*?'
    '<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"',
  ).firstMatch(svg);
  expect(match, isNotNull, reason: 'Expected SVG rect for node $id.');
  return _SvgRect(
    x: double.parse(match!.group(1)!),
    y: double.parse(match.group(2)!),
    width: double.parse(match.group(3)!),
    height: double.parse(match.group(4)!),
  );
}

_SvgPoint _svgGlyphForNode(String svg, String id) {
  final match = RegExp(
    '<g id="uml-node-${RegExp.escape(id)}">[\\s\\S]*?'
    '<g class="component-glyph" transform="translate\\(([^ ]+) ([^)]+)\\)"',
  ).firstMatch(svg);
  expect(match, isNotNull, reason: 'Expected component glyph for node $id.');
  return _SvgPoint(
    x: double.parse(match!.group(1)!),
    y: double.parse(match.group(2)!),
  );
}

_SvgSize _svgRootSize(String svg) {
  final match = RegExp(
    r'<svg class="uml-canvas"[^>]* width="([^"]+)" height="([^"]+)"',
  ).firstMatch(svg);
  expect(match, isNotNull, reason: 'Expected root UML SVG dimensions.');
  return _SvgSize(
    width: double.parse(match!.group(1)!),
    height: double.parse(match.group(2)!),
  );
}

int _svgClassCount(String svg, String className) {
  return RegExp('class="${RegExp.escape(className)}"').allMatches(svg).length;
}

void _expectComponentTextFits(String svg) {
  final componentPattern = RegExp(
    r'<g id="uml-node-([^"]+)">'
    r'<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"[^>]*class="uml-node uml-node-component"/>'
    r'<text[^>]*>([\s\S]*?)</text>',
  );
  final components = componentPattern.allMatches(svg).toList();
  expect(components, hasLength(10));
  for (final component in components) {
    final id = component.group(1)!;
    final rectX = double.parse(component.group(2)!);
    final rectWidth = double.parse(component.group(4)!);
    final text = component.group(6)!;
    for (final line in RegExp(
      r'<tspan x="([^"]+)" y="[^"]+">([^<]*)</tspan>',
    ).allMatches(text)) {
      final textX = double.parse(line.group(1)!);
      final label = line.group(2)!;
      final estimatedRight = textX + label.length * 8;
      expect(
        estimatedRight,
        lessThanOrEqualTo(rectX + rectWidth - 44),
        reason: 'Component text may clip into the UML glyph for $id: $label',
      );
    }
  }
}

class _RenderedPreview {
  const _RenderedPreview({
    required this.diagramHtml,
    required this.errorText,
    required this.usedMermaidFallback,
  });

  factory _RenderedPreview.fromJson(Map<String, Object?> json) {
    return _RenderedPreview(
      diagramHtml: json['diagramHtml']! as String,
      errorText: json['errorText']! as String,
      usedMermaidFallback: json['usedMermaidFallback']! as bool,
    );
  }

  final String diagramHtml;
  final String errorText;
  final bool usedMermaidFallback;
}

class _SvgRect {
  const _SvgRect({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  final double x;
  final double y;
  final double width;
  final double height;
}

class _SvgPoint {
  const _SvgPoint({required this.x, required this.y});

  final double x;
  final double y;
}

class _SvgSize {
  const _SvgSize({required this.width, required this.height});

  final double width;
  final double height;
}

void _openWorkbench(WidgetTester tester) {
  tester
      .widget<FloatingActionButton>(find.byType(FloatingActionButton))
      .onPressed!();
}

Future<void> _openSpecIntake(WidgetTester tester) async {
  final action = find.byTooltip('New functionality').first;
  await tester.ensureVisible(action);
  await tester.pumpAndSettle();
  await tester.tap(action);
  await tester.pumpAndSettle();
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await Scrollable.ensureVisible(
    tester.element(finder),
    alignment: 0.5,
    duration: Duration.zero,
  );
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _tapIntakeJobAction(WidgetTester tester, String label) async {
  final menu = find.text('Job actions');
  await tester.ensureVisible(menu);
  await tester.tap(menu);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

Future<void> _pumpWorkbench(
  WidgetTester tester, {
  required Future<SddProject?> Function(String bridgeUrl) loader,
  String bridgeUrl = 'http://bridge.test',
  String? metaWorkspacePath,
  MermaidDiagramRenderer? diagramRenderer,
  SddCodexActionSubmitter? actionSubmitter,
  SddExplorerClient? specIntakeClient,
  SddMediaAttachmentPicker? mediaAttachmentPicker,
  SddMediaAttachmentPicker? audioAttachmentPicker,
  SddStructuredAttachmentPicker? structuredAttachmentPicker,
  SddImageCropper? imageCropper,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CodexBridgeDevModeWrapper(
        enabled: true,
        bridgeUrl: bridgeUrl,
        metaWorkspacePath: metaWorkspacePath,
        explorerLoader: loader,
        diagramRenderer: diagramRenderer,
        specIntakeClient: specIntakeClient,
        mediaAttachmentPicker: mediaAttachmentPicker,
        audioAttachmentPicker: audioAttachmentPicker,
        structuredAttachmentPicker: structuredAttachmentPicker,
        imageCropper: imageCropper,
        sddActionSubmitter: actionSubmitter,
        child: const Text('normal app'),
      ),
    ),
  );
}

Map<String, dynamic> _projectJson() {
  return <String, dynamic>{
    'kind': 'codex.sddProject',
    'version': 1,
    'workspace_name': 'Codex Bridge',
    'workspace_path': '/workspace/codex-cli-mobile-bridge',
    'required': true,
    'manifest': <String, dynamic>{
      'path': 'codex-bridge.yaml',
      'size_bytes': 40,
      'content': 'kind: codex.bridge.project',
    },
    'constitution': <String, dynamic>{
      'path': '.specify/memory/constitution.md',
      'title': 'Constitution',
      'size_bytes': 120,
      'content': '# Constitution',
    },
    'architecture_diagrams': <Map<String, dynamic>>[
      <String, dynamic>{
        'path': 'architecture/components.mmd',
        'size_bytes': 42,
        'content': 'flowchart LR\nA --> B',
        'diagram_type': 'flowchart',
        'scope': 'architecture',
      },
    ],
    'specs': <Map<String, dynamic>>[
      <String, dynamic>{
        'id': '001-codex-bridge-sdd-wrapper',
        'title': 'Bridge Contract',
        'description': 'Read-only inspection for Bridge SDD artifacts.',
        'path': 'specs/001-codex-bridge-sdd-wrapper',
        'lifecycle_status': 'active',
        'traceability_status': 'linked',
        'created_at': '2026-07-01T09:00:00Z',
        'updated_at': '2026-07-06T10:15:00Z',
        'generated_title': false,
        'generated_description': true,
        'user_pinned_title': true,
        'user_pinned_description': false,
        'task_total': 2,
        'task_completed': 1,
        'task_pending': 1,
        'last_run_state': 'queued',
        'metadata_status': 'stale',
        'metadata_warnings': <String>[
          'metadata.yaml source digests are stale.',
        ],
        'metadata_stale_paths': <String>['tasks.md'],
        'missing': <String>[],
        'spec': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/spec.md',
          'title': 'Bridge Contract',
          'size_bytes': 80,
          'content': '# Bridge Contract',
        },
        'plan': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/plan.md',
          'size_bytes': 50,
          'content': '# Plan',
        },
        'tasks': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
          'size_bytes': 50,
          'content': '# Tasks\n\n- [x] Done\n- [ ] Pending',
        },
        'slice_docs': <Map<String, dynamic>>[],
        'diagrams': <Map<String, dynamic>>[],
      },
    ],
    'missing_required': <String>[],
  };
}

Map<String, dynamic> _projectWithTraceJson() {
  final project = _projectJson();
  project['specs'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'id': '001-sat-catalog-flow',
      'title': 'SAT Catalog Flow',
      'path': 'specs/001-sat-catalog-flow',
      'missing': <String>[],
      'spec': <String, dynamic>{
        'path': 'specs/001-sat-catalog-flow/spec.md',
        'title': 'SAT Catalog Flow',
        'size_bytes': 80,
        'content': '---\nstatus: planned\n---\n\n# SAT Catalog Flow',
      },
      'plans': <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001-sat-catalog-flow/design-plan.md',
          'size_bytes': 50,
          'content': '# Design Plan\n\n1. Map the current catalog flow.',
        },
        <String, dynamic>{
          'path': 'specs/001-sat-catalog-flow/build-plan.md',
          'size_bytes': 50,
          'content':
              '# Build Plan\n\n'
              '1. Build the catalog shell.\n'
              '2. Validate checkout totals.',
        },
      ],
      'task_files': <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001-sat-catalog-flow/design-tasks.md',
          'size_bytes': 50,
          'content': '# Design Tasks\n\n- [x] Done',
        },
        <String, dynamic>{
          'path': 'specs/001-sat-catalog-flow/build-tasks.md',
          'size_bytes': 50,
          'content':
              '# Build Tasks\n\n'
              '- [status: done] Done\n'
              '- [status: planned] Pending',
        },
      ],
      'slice_docs': <Map<String, dynamic>>[],
      'diagrams': <Map<String, dynamic>>[],
    },
  ];
  return project;
}

Map<String, dynamic> _projectWithTreeJson() {
  final project = _projectJson();
  project['specs'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'id': '001-sat-stock-reservation',
      'title': 'SAT Stock Reservation',
      'description':
          'Reserve available stock while a customer completes checkout.',
      'path': 'specs/001-sat-stock-reservation',
      'lifecycle_status': 'active',
      'traceability_status': 'linked',
      'task_total': 5,
      'task_completed': 1,
      'task_pending': 4,
      'missing': <String>[],
      'spec': <String, dynamic>{
        'path': 'specs/001-sat-stock-reservation/spec.md',
        'title': 'SAT Stock Reservation',
        'size_bytes': 80,
        'content': '# SAT Stock Reservation',
      },
      'tree': <String, dynamic>{
        'file': <String, dynamic>{
          'path': 'specs/001-sat-stock-reservation/spec.md',
          'title': 'SAT Stock Reservation',
          'size_bytes': 80,
          'content': '# SAT Stock Reservation',
        },
        'diagrams': <Map<String, dynamic>>[
          <String, dynamic>{
            'path': 'specs/001-sat-stock-reservation/diagrams/spec-flow.mmd',
            'size_bytes': 42,
            'content': 'flowchart LR\nCatalog --> Checkout',
            'diagram_type': 'flowchart',
            'scope': '001-sat-stock-reservation',
          },
        ],
        'plans': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'plan-1',
            'title': 'Catalog readiness',
            'number': 1,
            'status': 'done',
            'description': 'Prepare inventory data before reservations.',
            'file': <String, dynamic>{
              'path':
                  'specs/001-sat-stock-reservation/plans/01-catalog/plan.md',
              'title': 'Catalog readiness',
              'size_bytes': 50,
              'content': '# Catalog readiness\n\n1. Prepare stock inputs.',
            },
            'diagrams': <Map<String, dynamic>>[],
            'tasks': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'plan-1-task-1',
                'title': 'Normalize catalog variants',
                'number': 1,
                'status': 'done',
                'file': <String, dynamic>{
                  'path':
                      'specs/001-sat-stock-reservation/tasks/plan-1-task-1/task.md',
                  'title': 'Normalize catalog variants',
                  'size_bytes': 60,
                  'content': '# Normalize catalog variants\n\n- [x] Done',
                },
                'diagrams': <Map<String, dynamic>>[],
              },
              <String, dynamic>{
                'id': 'plan-1-task-2',
                'title': 'Validate stock thresholds',
                'number': 2,
                'status': 'done',
                'file': <String, dynamic>{
                  'path':
                      'specs/001-sat-stock-reservation/tasks/plan-1-task-2/task.md',
                  'title': 'Validate stock thresholds',
                  'size_bytes': 60,
                  'content': '# Validate stock thresholds\n\n- [x] Done',
                },
                'diagrams': <Map<String, dynamic>>[],
              },
            ],
          },
          <String, dynamic>{
            'id': 'plan-2',
            'title': 'Checkout reservation',
            'number': 2,
            'status': 'in_progress',
            'description': 'Reserve cart units during checkout.',
            'file': <String, dynamic>{
              'path':
                  'specs/001-sat-stock-reservation/plans/02-checkout/plan.md',
              'title': 'Checkout reservation',
              'size_bytes': 50,
              'content': '# Checkout reservation\n\n1. Hold stock.',
            },
            'diagrams': <Map<String, dynamic>>[],
            'tasks': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'plan-2-task-1',
                'title': 'Reserve cart units',
                'number': 1,
                'status': 'in_progress',
                'file': <String, dynamic>{
                  'path':
                      'specs/001-sat-stock-reservation/tasks/plan-2-task-1/task.md',
                  'title': 'Reserve cart units',
                  'size_bytes': 60,
                  'content': '# Reserve cart units\n\n- [ ] Reserve units',
                },
                'diagrams': <Map<String, dynamic>>[],
              },
              <String, dynamic>{
                'id': 'plan-2-task-2',
                'title': 'Reconcile payment expiry',
                'number': 2,
                'status': 'planned',
                'file': <String, dynamic>{
                  'path':
                      'specs/001-sat-stock-reservation/tasks/plan-2-task-2/task.md',
                  'title': 'Reconcile payment expiry',
                  'size_bytes': 60,
                  'content': '# Reconcile payment expiry\n\n- [ ] Expire hold',
                },
                'diagrams': <Map<String, dynamic>>[],
              },
              <String, dynamic>{
                'id': 'plan-2-task-3',
                'title': 'Persist reservation audit',
                'number': 3,
                'status': 'planned',
                'file': <String, dynamic>{
                  'path':
                      'specs/001-sat-stock-reservation/tasks/plan-2-task-3/task.md',
                  'title': 'Persist reservation audit',
                  'size_bytes': 60,
                  'content': '# Persist reservation audit\n\n- [ ] Audit',
                },
                'diagrams': <Map<String, dynamic>>[],
              },
            ],
          },
        ],
      },
      'slice_docs': <Map<String, dynamic>>[],
      'diagrams': <Map<String, dynamic>>[],
    },
  ];
  return project;
}

Map<String, dynamic> _projectWithIncompleteTreeJson() {
  final project = _projectWithTreeJson();
  final spec = (project['specs']! as List<Map<String, dynamic>>).single;
  spec.remove('traceability_status');
  spec['metadata_status'] = 'present';
  final tree = spec['tree']! as Map<String, dynamic>;
  tree.remove('complete');
  tree['missing'] = <String>[];
  tree['plans'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'id': 'plan-1',
      'title': 'Incomplete plan',
      'number': 1,
      'status': 'planned',
      'file': <String, dynamic>{
        'path': 'specs/001-sat-stock-reservation/plans/01-plan/plan.md',
        'size_bytes': 40,
        'content': '# Incomplete plan',
      },
      'diagrams': <Map<String, dynamic>>[],
      'tasks': <Map<String, dynamic>>[],
    },
  ];
  return project;
}

Map<String, dynamic> _projectWithGovernanceJson() {
  final project = _projectWithTraceJson();
  final specs = project['specs']! as List<Map<String, dynamic>>;
  specs.single['diagrams'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'path': 'specs/001-sat-catalog-flow/diagrams/domain-impact.mmd',
      'size_bytes': 42,
      'content': 'classDiagram\nCatalog --> Product',
      'diagram_type': 'domain-impact',
      'scope': '001-sat-catalog-flow',
    },
  ];
  return project;
}

class _FakeMermaidRenderer implements MermaidDiagramRenderer {
  _FakeMermaidRenderer(this._render);

  factory _FakeMermaidRenderer.success() {
    return _FakeMermaidRenderer((diagram) async {
      return MermaidRenderResult.success(
        kind: 'fake',
        preview: SizedBox(
          width: 420,
          height: 160,
          child: Text('rendered ${diagram.path}'),
        ),
      );
    });
  }

  factory _FakeMermaidRenderer.failure(String message) {
    return _FakeMermaidRenderer((_) async {
      return MermaidRenderResult.failure(message);
    });
  }

  final Future<MermaidRenderResult> Function(SddDiagram diagram) _render;

  @override
  Future<MermaidRenderResult> render(SddDiagram diagram) {
    return _render(diagram);
  }
}

class _FakeSpecIntakeClient extends SddExplorerClient {
  _FakeSpecIntakeClient({
    required this.dryRunPlan,
    this.applyResult,
    this.stagedMedia,
    this.uploadError,
    this.deleteError,
    this.runJob,
    this.review,
    this.applyJob,
    this.activity,
    this.cancelJob,
    this.retryJob,
  }) : super(baseUrl: 'http://bridge.test');

  final SddSpecIntakePlan dryRunPlan;
  final SddSpecIntakeApplyResult? applyResult;
  final SddStagedMediaAttachment? stagedMedia;
  final Object? uploadError;
  final Object? deleteError;
  final SddCodexJobStatus? runJob;
  final SddCodexJobReview? review;
  final SddCodexJobApplyResult? applyJob;
  final SddActivitySnapshot? activity;
  final SddCodexJobStatus? cancelJob;
  final SddCodexJobRetryResult? retryJob;
  SddSpecIntakeDraft? lastDraft;
  String? uploadedWorkspacePath;
  SddMediaAttachmentDraft? uploadedAttachment;
  String? uploadedKind;
  String? uploadedSourceRef;
  Map<String, Object?>? uploadedRegion;
  String? deletedStagedPath;
  int activityRequests = 0;
  int cancelRequests = 0;
  int retryRequests = 0;

  @override
  Future<SddSpecIntakePlan> dryRunSpecIntake(SddSpecIntakeDraft draft) async {
    lastDraft = draft;
    return dryRunPlan;
  }

  @override
  Future<SddSpecIntakeApplyResult> applySpecIntake(
    SddSpecIntakeDraft draft,
  ) async {
    lastDraft = draft;
    return applyResult ?? const SddSpecIntakeApplyResult(status: 'blocked');
  }

  @override
  Future<SddStagedMediaAttachment> uploadSpecMedia({
    required String workspacePath,
    required SddMediaAttachmentDraft attachment,
    String kind = 'image',
    String? sourceRef,
    Map<String, Object?>? region,
  }) async {
    uploadedWorkspacePath = workspacePath;
    uploadedAttachment = attachment;
    uploadedKind = kind;
    uploadedSourceRef = sourceRef;
    uploadedRegion = region;
    final error = uploadError;
    if (error != null) {
      throw error;
    }
    if (kind == 'crop') {
      return SddStagedMediaAttachment(
        status: 'staged',
        stagedPath: '.codex-bridge/sdd-media/crop.png',
        previewBytes: attachment.bytes,
        intakeItem: <String, Object?>{
          'kind': 'crop',
          'mime_type': attachment.mimeType,
          'byte_size': attachment.bytes.length,
          'filename': attachment.filename,
          'sha256':
              'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
          'source_ref': sourceRef,
          'payload_ref': '.codex-bridge/sdd-media/crop.png',
          'region': region,
        },
      );
    }
    return stagedMedia ??
        const SddStagedMediaAttachment(
          status: 'staged',
          intakeItem: <String, Object?>{
            'kind': 'image',
            'mime_type': 'image/png',
            'byte_size': 0,
            'filename': 'image.png',
            'sha256':
                'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            'payload_ref': '.codex-bridge/sdd-media/image.png',
          },
        );
  }

  @override
  Future<SddMediaLifecycleResult> deleteSpecMedia({
    required String workspacePath,
    required String stagedPath,
  }) async {
    deletedStagedPath = stagedPath;
    final error = deleteError;
    if (error != null) {
      throw error;
    }
    return SddMediaLifecycleResult(
      status: 'deleted',
      lifecycle: 'deleted',
      stagedPath: stagedPath,
      deleted: <String>[stagedPath],
    );
  }

  @override
  Future<SddCodexJobStatus> runCodexJob(String jobId) async {
    return runJob ?? SddCodexJobStatus(id: jobId, status: 'blocked');
  }

  @override
  Future<SddActivitySnapshot> getCodexJobActivity(String jobId) async {
    activityRequests += 1;
    return activity ??
        SddActivitySnapshot(
          state: 'queued',
          jobId: jobId,
          events: const <SddActivityEvent>[
            SddActivityEvent(
              state: 'queued',
              status: 'active',
              label: 'Job queued',
            ),
          ],
        );
  }

  @override
  Future<SddCodexJobStatus> cancelCodexJob(String jobId) async {
    cancelRequests += 1;
    return cancelJob ??
        SddCodexJobStatus(
          id: jobId,
          status: 'cancelled',
          activity: SddActivitySnapshot(
            state: 'cancelled',
            jobId: jobId,
            events: const <SddActivityEvent>[
              SddActivityEvent(
                state: 'cancelled',
                status: 'blocked',
                label: 'Job cancelled',
              ),
            ],
          ),
        );
  }

  @override
  Future<SddCodexJobRetryResult> retryCodexJob(String jobId) async {
    retryRequests += 1;
    return retryJob ??
        SddCodexJobRetryResult(
          status: 'queued',
          originalJobId: jobId,
          retryJobId: '$jobId-retry-01',
          retryEligible: true,
          copiedReferences: const <String>['request.json', 'context-pack.json'],
          job: SddCodexJobStatus(
            id: '$jobId-retry-01',
            status: 'queued',
            activity: SddActivitySnapshot(
              state: 'queued',
              jobId: '$jobId-retry-01',
              events: const <SddActivityEvent>[
                SddActivityEvent(
                  state: 'retry-created',
                  status: 'completed',
                  label: 'Retry job created',
                ),
                SddActivityEvent(
                  state: 'queued',
                  status: 'active',
                  label: 'Retry queued',
                ),
              ],
            ),
          ),
          activity: SddActivitySnapshot(
            state: 'queued',
            jobId: '$jobId-retry-01',
            events: const <SddActivityEvent>[
              SddActivityEvent(
                state: 'retry-created',
                status: 'completed',
                label: 'Retry job created',
              ),
              SddActivityEvent(
                state: 'queued',
                status: 'active',
                label: 'Retry queued',
              ),
            ],
          ),
        );
  }

  @override
  Future<SddCodexJobReview> reviewCodexJob(String jobId) async {
    return review ??
        const SddCodexJobReview(status: 'blocked', validationStatus: 'not_run');
  }

  @override
  Future<SddCodexJobApplyResult> applyCodexJob(String jobId) async {
    return applyJob ?? const SddCodexJobApplyResult(status: 'blocked');
  }
}

class _FakeMermaidAssetBundle extends CachingAssetBundle {
  _FakeMermaidAssetBundle(this.asset);

  final String asset;

  @override
  Future<ByteData> load(String key) async {
    expect(key, WebViewMermaidDiagramRenderer.mermaidAssetPath);
    final bytes = Uint8List.fromList(utf8.encode(asset));
    return ByteData.view(bytes.buffer);
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    expect(key, WebViewMermaidDiagramRenderer.mermaidAssetPath);
    return asset;
  }
}
