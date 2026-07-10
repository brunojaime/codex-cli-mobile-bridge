import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';
import 'package:codex_mobile_frontend/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('SDD SVG diagram actions select the diagram MCP server', () {
    final draft = SddCodexActionDraft(
      request: SddCodexActionRequest(
        kind: SddCodexActionKind.updateDiagram,
        target: const SddFeedbackTarget(
          workspacePath: '/workspace/demo',
          artifactType: 'diagram',
          artifactPath: 'specs/016/diagrams/browser-gateway.svg',
          artifactTitle: 'Browser Gateway',
          sourceExcerpt: '<svg></svg>',
          diagramType: 'uml-component-svg',
          diagramScope: '016',
          diagramSelectionMetadata: <String, Object?>{
            'renderer': 'diagram-mcp-rendering-engine',
            'sourceFormat': 'svg',
            'renderedFormat': 'svg',
          },
        ),
      ),
      prompt: 'Update diagram',
    );

    final options = codexRunOptionsForSddAction(draft);

    expect(options, isNotNull);
    expect(options!.mcpServerIds, <String>['diagram-mcp-rendering-engine']);
  });
}
