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
    await tester.tap(find.text('Diagrams').first);
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
      expect(find.text('status: planned'), findsOneWidget);
      expect(find.text('trace: linked'), findsOneWidget);

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

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Codex').first);
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
        'content': '---\nstatus: planned\n---\n\n# SAT SDD Onboarding',
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

Map<String, dynamic> _projectWithGovernanceJson() {
  final project = _projectWithTraceJson();
  final specs = project['specs']! as List<Map<String, dynamic>>;
  specs.single['diagrams'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'path': 'specs/001/diagrams/domain-impact.mmd',
      'size_bytes': 42,
      'content': 'classDiagram\nCatalog --> Product',
      'diagram_type': 'domain-impact',
      'scope': '001-sat-sdd-onboarding',
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
