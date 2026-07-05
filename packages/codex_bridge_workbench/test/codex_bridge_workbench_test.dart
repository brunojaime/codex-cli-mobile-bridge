import 'dart:async';
import 'dart:convert';

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
    expect(find.text('Codex Bridge'), findsWidgets);
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
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.textContaining('architecture/components.mmd'), findsOneWidget);
    await tester.tap(find.text('flowchart diagram').first);
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
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.text('flowchart diagram'), findsOneWidget);
    expect(
      find.textContaining('rendered architecture/components.mmd'),
      findsNothing,
    );

    await tester.tap(find.text('flowchart diagram').first);
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

    expect(find.text('SDD trace'), findsOneWidget);
    expect(find.text('2 plans'), findsOneWidget);
    expect(find.text('2 task files'), findsOneWidget);
    expect(find.text('design-plan.md'), findsWidgets);
    expect(find.text('build-plan.md'), findsWidgets);

    await tester.tap(find.text('build-plan.md').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Build Plan'), findsOneWidget);

    await tester.tap(find.text('build-tasks.md').first);
    await tester.pumpAndSettle();
    expect(find.text('1/2 tasks complete'), findsOneWidget);
  });

  test('SDD spec model parses plural plan and task history', () {
    final project = SddProject.fromJson(_projectWithTraceJson());
    final spec = project.specs.single;

    expect(spec.allPlanFiles.map((file) => file.path), <String>[
      'specs/001/design-plan.md',
      'specs/001/build-plan.md',
    ]);
    expect(spec.allTaskFiles.map((file) => file.path), <String>[
      'specs/001/design-tasks.md',
      'specs/001/build-tasks.md',
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

    await tester.tap(find.text('Audit SDD').first);
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
}

void _openWorkbench(WidgetTester tester) {
  tester
      .widget<FloatingActionButton>(find.byType(FloatingActionButton))
      .onPressed!();
}

Future<void> _pumpWorkbench(
  WidgetTester tester, {
  required Future<SddProject?> Function(String bridgeUrl) loader,
  String bridgeUrl = 'http://bridge.test',
  String? metaWorkspacePath,
  MermaidDiagramRenderer? diagramRenderer,
  SddCodexActionSubmitter? actionSubmitter,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CodexBridgeDevModeWrapper(
        enabled: true,
        bridgeUrl: bridgeUrl,
        metaWorkspacePath: metaWorkspacePath,
        explorerLoader: loader,
        diagramRenderer: diagramRenderer,
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
        'path': 'specs/001-codex-bridge-sdd-wrapper',
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
      'id': '001-sat-sdd-onboarding',
      'title': 'SAT SDD Onboarding',
      'path': 'specs/001-sat-sdd-onboarding',
      'missing': <String>[],
      'spec': <String, dynamic>{
        'path': 'specs/001/spec.md',
        'title': 'SAT SDD Onboarding',
        'size_bytes': 80,
        'content': '# SAT SDD Onboarding',
      },
      'plans': <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001/design-plan.md',
          'size_bytes': 50,
          'content': '# Design Plan',
        },
        <String, dynamic>{
          'path': 'specs/001/build-plan.md',
          'size_bytes': 50,
          'content': '# Build Plan',
        },
      ],
      'task_files': <Map<String, dynamic>>[
        <String, dynamic>{
          'path': 'specs/001/design-tasks.md',
          'size_bytes': 50,
          'content': '# Design Tasks\n\n- [x] Done',
        },
        <String, dynamic>{
          'path': 'specs/001/build-tasks.md',
          'size_bytes': 50,
          'content': '# Build Tasks\n\n- [x] Done\n- [ ] Pending',
        },
      ],
      'slice_docs': <Map<String, dynamic>>[],
      'diagrams': <Map<String, dynamic>>[],
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
