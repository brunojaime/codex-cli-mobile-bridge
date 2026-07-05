import 'package:flutter/material.dart';

import '../services/mermaid_renderer.dart';
import 'sdd_explorer_panel.dart';

class CodexBridgeDevModeWrapper extends StatefulWidget {
  const CodexBridgeDevModeWrapper({
    super.key,
    required this.enabled,
    required this.bridgeUrl,
    required this.child,
    this.workspacePath,
    this.metaWorkspacePath,
    this.metaWorkspaceLabel = 'Codex Bridge Workbench',
    this.diagramRenderer,
    this.explorerLoader,
    this.sddFeedbackSubmitter,
    this.sddActionSubmitter,
  });

  final bool enabled;
  final String bridgeUrl;
  final String? workspacePath;
  final String? metaWorkspacePath;
  final String metaWorkspaceLabel;
  final Widget child;
  final MermaidDiagramRenderer? diagramRenderer;
  final SddExplorerLoader? explorerLoader;
  final SddFeedbackSubmitter? sddFeedbackSubmitter;
  final SddCodexActionSubmitter? sddActionSubmitter;

  @override
  State<CodexBridgeDevModeWrapper> createState() =>
      _CodexBridgeDevModeWrapperState();
}

class _CodexBridgeDevModeWrapperState extends State<CodexBridgeDevModeWrapper> {
  bool _explorerOpen = false;

  void _openExplorer() {
    setState(() {
      _explorerOpen = true;
    });
  }

  void _closeExplorer() {
    setState(() {
      _explorerOpen = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return widget.child;
    }
    return Stack(
      children: <Widget>[
        Banner(
          message: 'CODEX DEV',
          location: BannerLocation.topEnd,
          color: const Color(0xFF55D6BE),
          textStyle: const TextStyle(
            color: Color(0xFF07131D),
            fontSize: 10,
            fontWeight: FontWeight.w800,
          ),
          child: widget.child,
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            heroTag: 'sdd-explorer-entry',
            tooltip: 'Open SDD Explorer',
            onPressed: _openExplorer,
            icon: const Icon(Icons.account_tree_outlined),
            label: const Text('SDD'),
          ),
        ),
        if (_explorerOpen) ...[
          Positioned.fill(
            child: GestureDetector(
              onTap: _closeExplorer,
              child: Container(color: const Color(0x99000000)),
            ),
          ),
          Positioned.fill(
            child: SddExplorerPanel(
              bridgeUrl: widget.bridgeUrl,
              workspacePath: widget.workspacePath,
              metaWorkspacePath: widget.metaWorkspacePath,
              metaWorkspaceLabel: widget.metaWorkspaceLabel,
              diagramRenderer:
                  widget.diagramRenderer ??
                  const WebViewMermaidDiagramRenderer(),
              loader: widget.explorerLoader,
              feedbackSubmitter: widget.sddFeedbackSubmitter,
              actionSubmitter: widget.sddActionSubmitter,
              onClose: _closeExplorer,
            ),
          ),
        ],
      ],
    );
  }
}
