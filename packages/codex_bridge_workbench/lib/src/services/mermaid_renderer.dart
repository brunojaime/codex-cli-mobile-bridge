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
          diagramPath: diagram.path,
          diagramType: diagram.diagramType,
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
    required this.diagramPath,
    required this.diagramType,
    this.renderTimeout = WebViewMermaidDiagramRenderer.diagramRenderTimeout,
    this.width = 720,
    this.height = 300,
  });

  final String mermaidJs;
  final String source;
  final String diagramPath;
  final String diagramType;
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
        diagramPath: widget.diagramPath,
        diagramType: widget.diagramType,
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
  String diagramPath = '',
  String diagramType = '',
  Duration renderTimeout = WebViewMermaidDiagramRenderer.diagramRenderTimeout,
}) {
  final encodedSource = jsonEncode(base64Encode(utf8.encode(source)));
  final encodedDiagramPath = jsonEncode(diagramPath);
  final encodedDiagramType = jsonEncode(diagramType);
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
    const diagramPath = $encodedDiagramPath;
    const diagramType = $encodedDiagramType;
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

    function isComponentDiagramSource(source) {
      const normalizedPath = String(diagramPath || '').toLowerCase();
      const normalizedType = String(diagramType || '').toLowerCase();
      return normalizedPath.endsWith('/components.mmd') ||
        normalizedPath === 'components.mmd' ||
        normalizedPath.endsWith('/component.mmd') ||
        normalizedType.includes('component') ||
        /<<\\s*component\\s*>>/i.test(source);
    }

    function parseUmlInterfaceAnnotations(source) {
      const annotations = [];
      const pattern = /^\\s*%%\\s*uml-interface:\\s*(.*?)\\s+consumer=([A-Za-z0-9_.:-]+)\\s+provider=([A-Za-z0-9_.:-]+)\\s*\$/gm;
      let match;
      while ((match = pattern.exec(source)) !== null) {
        annotations.push({
          label: match[1].trim(),
          consumer: match[2].trim(),
          provider: match[3].trim()
        });
      }
      return annotations;
    }

    function svgElement(name) {
      return document.createElementNS('http://www.w3.org/2000/svg', name);
    }

    function appendRect(parent, attrs) {
      const rect = svgElement('rect');
      for (const key of Object.keys(attrs)) {
        rect.setAttribute(key, attrs[key]);
      }
      parent.appendChild(rect);
      return rect;
    }

    function componentNodeShape(node) {
      return node.querySelector(':scope > rect, :scope > path, :scope > polygon');
    }

    function nodeText(node) {
      return Array.from(node.querySelectorAll('text, tspan'))
        .map((item) => item.textContent || '')
        .join(' ');
    }

    function isExplicitComponentNode(node) {
      const classes = (node.getAttribute('class') || '').split(/\\s+/);
      return classes.includes('component') ||
        /<<\\s*component\\s*>>/i.test(nodeText(node));
    }

    function stripComponentStereotype(node) {
      for (const text of node.querySelectorAll('text, tspan')) {
        text.textContent = (text.textContent || '')
          .replace(/<<\\s*component\\s*>>\\s*/gi, '')
          .trim();
      }
    }

    function addComponentGlyph(node) {
      if (node.querySelector('.uml-component-glyph')) return;
      const shape = componentNodeShape(node);
      if (!shape || typeof shape.getBBox !== 'function') return;

      let box;
      try {
        box = shape.getBBox();
      } catch (_) {
        return;
      }
      if (!Number.isFinite(box.width) || box.width < 32) return;

      const group = svgElement('g');
      group.setAttribute('class', 'uml-component-glyph');
      group.setAttribute(
        'transform',
        'translate(' + (box.x + box.width - 28) + ' ' + (box.y + 8) + ')'
      );

      appendRect(group, {
        x: '7',
        y: '0',
        width: '14',
        height: '20',
        fill: 'none',
        stroke: '#9ca3af',
        'stroke-width': '1.8'
      });
      appendRect(group, {
        x: '0',
        y: '3',
        width: '11',
        height: '5',
        fill: '#0b1426',
        stroke: '#9ca3af',
        'stroke-width': '1.8'
      });
      appendRect(group, {
        x: '0',
        y: '12',
        width: '11',
        height: '5',
        fill: '#0b1426',
        stroke: '#9ca3af',
        'stroke-width': '1.8'
      });
      node.appendChild(group);
    }

    function applyUmlComponentNodes(svg, source) {
      if (!isComponentDiagramSource(source)) return;
      const nodes = Array.from(svg.querySelectorAll('g.node'));
      const explicitNodes = nodes.filter(isExplicitComponentNode);
      const targetNodes = explicitNodes.length > 0
        ? explicitNodes
        : nodes.filter((node) => componentNodeShape(node) !== null);

      for (const node of targetNodes) {
        stripComponentStereotype(node);
        addComponentGlyph(node);
      }
    }

    function classTokens(element) {
      return (element.getAttribute('class') || '').split(/\\s+/);
    }

    function findEdge(svg, consumer, provider) {
      const direct = Array.from(svg.querySelectorAll('g.edgePath')).find((edge) => {
        const classes = classTokens(edge);
        return classes.includes('LS-' + consumer) && classes.includes('LE-' + provider);
      });
      if (direct) return direct;

      return Array.from(svg.querySelectorAll('g.edgePath')).find((edge) => {
        const classes = classTokens(edge);
        return classes.includes('LS-' + provider) && classes.includes('LE-' + consumer);
      });
    }

    function drawInterfaceSymbol(layer, path) {
      if (!path || typeof path.getTotalLength !== 'function') return;

      let length;
      try {
        length = path.getTotalLength();
      } catch (_) {
        return;
      }
      if (!Number.isFinite(length) || length <= 0) return;

      const center = path.getPointAtLength(length / 2);
      const before = path.getPointAtLength(Math.max(0, length / 2 - 18));
      const after = path.getPointAtLength(Math.min(length, length / 2 + 18));
      const angle = Math.atan2(after.y - before.y, after.x - before.x) * 180 / Math.PI;
      const group = svgElement('g');
      group.setAttribute('class', 'uml-interface-symbol');
      group.setAttribute(
        'transform',
        'translate(' + center.x + ' ' + center.y + ') rotate(' + angle + ')'
      );

      const bridge = svgElement('line');
      bridge.setAttribute('x1', '-24');
      bridge.setAttribute('y1', '0');
      bridge.setAttribute('x2', '24');
      bridge.setAttribute('y2', '0');
      bridge.setAttribute('stroke', '#9ca3af');
      bridge.setAttribute('stroke-width', '2');
      group.appendChild(bridge);

      const consumerCircle = svgElement('circle');
      consumerCircle.setAttribute('cx', '-8');
      consumerCircle.setAttribute('cy', '0');
      consumerCircle.setAttribute('r', '7');
      consumerCircle.setAttribute('fill', '#0b1426');
      consumerCircle.setAttribute('stroke', '#cbd5e1');
      consumerCircle.setAttribute('stroke-width', '2');
      group.appendChild(consumerCircle);

      const providerSocket = svgElement('path');
      providerSocket.setAttribute('d', 'M 13 -8 A 8 8 0 1 0 13 8');
      providerSocket.setAttribute('fill', 'none');
      providerSocket.setAttribute('stroke', '#cbd5e1');
      providerSocket.setAttribute('stroke-width', '2');
      providerSocket.setAttribute('stroke-linecap', 'round');
      group.appendChild(providerSocket);

      layer.appendChild(group);
    }

    function applyUmlInterfaces(svg, source) {
      const annotations = parseUmlInterfaceAnnotations(source);
      if (annotations.length === 0) return;

      const layer = svgElement('g');
      layer.setAttribute('class', 'uml-interface-layer');
      svg.appendChild(layer);

      for (const annotation of annotations) {
        const edge = findEdge(svg, annotation.consumer, annotation.provider);
        const path = edge ? edge.querySelector('path') : null;
        drawInterfaceSymbol(layer, path);
      }
    }

    function applyUmlComponentNotation(source) {
      const svg = diagram.querySelector('svg');
      if (!svg) return;
      applyUmlComponentNodes(svg, source);
      applyUmlInterfaces(svg, source);
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
        applyUmlComponentNotation(source);
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
