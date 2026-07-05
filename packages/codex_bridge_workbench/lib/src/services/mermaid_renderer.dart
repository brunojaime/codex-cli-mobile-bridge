import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../models/sdd_project.dart';

abstract class MermaidDiagramRenderer {
  Future<MermaidRenderResult> render(SddDiagram diagram);
}

class MermaidRenderResult {
  const MermaidRenderResult._({required this.kind, this.preview, this.error});

  factory MermaidRenderResult.success({
    required String kind,
    required Widget preview,
  }) {
    return MermaidRenderResult._(kind: kind, preview: preview);
  }

  factory MermaidRenderResult.failure(String error) {
    return MermaidRenderResult._(kind: 'unknown', error: error);
  }

  final String kind;
  final Widget? preview;
  final String? error;

  bool get isSuccess => preview != null && error == null;
}

class WebViewMermaidDiagramRenderer implements MermaidDiagramRenderer {
  const WebViewMermaidDiagramRenderer({
    this.assetBundle,
    this.previewWidth = 720,
    this.previewHeight = 300,
  });

  static const mermaidAssetPath =
      'packages/codex_bridge_workbench/assets/vendor/mermaid/mermaid.min.js';
  static const assetLoadTimeout = Duration(seconds: 10);
  static const diagramRenderTimeout = Duration(seconds: 8);

  final AssetBundle? assetBundle;
  final double previewWidth;
  final double previewHeight;

  @override
  Future<MermaidRenderResult> render(SddDiagram diagram) async {
    final source = diagram.content?.trim();
    if (source == null || source.isEmpty) {
      return MermaidRenderResult.failure('Diagram source is empty.');
    }

    try {
      final mermaidJs = await (assetBundle ?? rootBundle)
          .loadString(mermaidAssetPath)
          .timeout(assetLoadTimeout);
      return MermaidRenderResult.success(
        kind: 'mermaid',
        preview: MermaidWebViewPreview(
          mermaidJs: mermaidJs,
          source: source,
          renderTimeout: diagramRenderTimeout,
          width: previewWidth,
          height: previewHeight,
        ),
      );
    } on Object catch (error) {
      return MermaidRenderResult.failure(
        'Could not load bundled Mermaid renderer: $error',
      );
    }
  }
}

class MermaidWebViewPreview extends StatefulWidget {
  const MermaidWebViewPreview({
    super.key,
    required this.mermaidJs,
    required this.source,
    this.renderTimeout = WebViewMermaidDiagramRenderer.diagramRenderTimeout,
    this.width = 720,
    this.height = 300,
  });

  final String mermaidJs;
  final String source;
  final Duration renderTimeout;
  final double width;
  final double height;

  @override
  State<MermaidWebViewPreview> createState() => _MermaidWebViewPreviewState();
}

class _MermaidWebViewPreviewState extends State<MermaidWebViewPreview> {
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (request) {
            final url = request.url;
            if (url == 'about:blank' || url.startsWith('data:text/html')) {
              return NavigationDecision.navigate;
            }
            return NavigationDecision.prevent;
          },
        ),
      )
      ..enableZoom(true);
    _hardenPlatformController(_controller);
    _loadHtml();
  }

  @override
  void didUpdateWidget(MermaidWebViewPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.source != widget.source ||
        oldWidget.mermaidJs != widget.mermaidJs ||
        oldWidget.renderTimeout != widget.renderTimeout ||
        oldWidget.width != widget.width ||
        oldWidget.height != widget.height) {
      _loadHtml();
    }
  }

  void _loadHtml() {
    _controller.loadHtmlString(
      buildMermaidPreviewHtml(
        mermaidJs: widget.mermaidJs,
        source: widget.source,
        renderTimeout: widget.renderTimeout,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final maxScreenWidth = math.max(280.0, screenWidth - 48);
    final effectiveWidth = widget.width.isFinite
        ? math.min(widget.width, maxScreenWidth)
        : maxScreenWidth;
    return SizedBox(
      width: effectiveWidth,
      height: widget.height,
      child: WebViewWidget(controller: _controller),
    );
  }
}

void _hardenPlatformController(WebViewController controller) {
  final platform = controller.platform;
  if (platform is! AndroidWebViewController) return;

  unawaited(platform.setAllowFileAccess(false));
  unawaited(platform.setAllowContentAccess(false));
  unawaited(platform.setGeolocationEnabled(false));
  unawaited(platform.setMixedContentMode(MixedContentMode.neverAllow));
}

@visibleForTesting
String buildMermaidPreviewHtml({
  required String mermaidJs,
  required String source,
  Duration renderTimeout = WebViewMermaidDiagramRenderer.diagramRenderTimeout,
}) {
  final encodedSource = jsonEncode(base64Encode(utf8.encode(source)));
  final renderTimeoutMs = renderTimeout.inMilliseconds;
  return '''
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none';">
  <style>
    html, body {
      margin: 0;
      padding: 0;
      background: #0b1426;
      color: #dde7f7;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: auto;
    }
    #diagram {
      width: 100vw;
      min-width: 0;
      min-height: 240px;
      padding: 12px;
      box-sizing: border-box;
    }
    #diagram svg {
      max-width: 100%;
      width: 100%;
      height: auto;
      background: #0b1426;
    }
    #error {
      display: none;
      margin: 16px;
      padding: 12px;
      border: 1px solid rgba(255, 200, 87, 0.45);
      border-radius: 8px;
      background: #221b16;
      color: #ffc857;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div id="diagram" aria-label="Rendered Mermaid diagram">Rendering Mermaid diagram...</div>
  <pre id="error" aria-label="Mermaid render error"></pre>
  <script>
$mermaidJs
  </script>
  <script>
    const encodedSource = $encodedSource;
    const diagram = document.getElementById('diagram');
    const errorBox = document.getElementById('error');
    let finished = false;

    function decodeUtf8Base64(value) {
      const binary = atob(value);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return new TextDecoder('utf-8').decode(bytes);
    }

    function showError(message) {
      if (finished) return;
      finished = true;
      diagram.style.display = 'none';
      errorBox.style.display = 'block';
      errorBox.textContent = message;
    }

    async function renderDiagram() {
      const timeout = window.setTimeout(function() {
        showError('Mermaid render timed out after $renderTimeoutMs ms.');
      }, $renderTimeoutMs);
      try {
        const source = decodeUtf8Base64(encodedSource);
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'strict',
          htmlLabels: false,
          flowchart: {
            htmlLabels: false
          }
        });
        const id = 'sdd-diagram-' + Date.now().toString(36);
        const result = await mermaid.render(id, source);
        if (finished) return;
        finished = true;
        window.clearTimeout(timeout);
        diagram.innerHTML = result.svg;
      } catch (error) {
        window.clearTimeout(timeout);
        showError(error && error.message ? error.message : String(error));
      }
    }

    renderDiagram();
  </script>
</body>
</html>
''';
}
