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
    #diagram svg.uml-canvas {
      max-width: none;
      width: auto;
      background: #f8fbff;
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

    function cleanLabel(value) {
      return String(value || '')
        .replace(/\\\\n/g, '\\n')
        .replace(/<<\\s*component\\s*>>\\s*/gi, '')
        .trim();
    }

    function stripQuotes(value) {
      const text = String(value || '').trim();
      if ((text.startsWith('"') && text.endsWith('"')) ||
          (text.startsWith("'") && text.endsWith("'"))) {
        return text.substring(1, text.length - 1);
      }
      return text;
    }

    function parseNodeLabel(definition) {
      const trimmed = definition.trim();
      let match = trimmed.match(/^\\[\\("([\\s\\S]*)"\\)\\]\$/);
      if (match) return { label: match[1], kind: 'database' };
      match = trimmed.match(/^\\["([\\s\\S]*)"\\]\$/);
      if (match) return { label: match[1], kind: 'node' };
      match = trimmed.match(/^\\[([\\s\\S]*)\\]\$/);
      if (match) return { label: stripQuotes(match[1]), kind: 'node' };
      return null;
    }

    function parseComponentFlowchart(source) {
      const root = {
        id: 'root',
        label: '',
        direction: 'LR',
        children: [],
        parent: null
      };
      const groups = new Map([['root', root]]);
      const nodes = new Map();
      const edges = [];
      const interfaces = parseUmlInterfaceAnnotations(source);
      const stack = [root];

      function currentGroup() {
        return stack[stack.length - 1];
      }

      function addChild(group, item) {
        if (!group.children.some((child) => child.type === item.type && child.id === item.id)) {
          group.children.push(item);
        }
      }

      function ensureNode(id, rawLabel, kind) {
        if (!nodes.has(id)) {
          const node = {
            id,
            rawLabel: rawLabel || id,
            label: cleanLabel(rawLabel || id),
            kind: kind || 'node',
            classes: new Set(),
            group: currentGroup().id,
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            lines: []
          };
          nodes.set(id, node);
          addChild(currentGroup(), { type: 'node', id });
        } else if (rawLabel && rawLabel !== id) {
          const node = nodes.get(id);
          node.rawLabel = rawLabel;
          node.label = cleanLabel(rawLabel);
          if (kind) node.kind = kind;
        }
        return nodes.get(id);
      }

      const lines = source.split(/\\r?\\n/);
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || line.startsWith('%%')) continue;

        let match = line.match(/^flowchart\\s+(LR|RL|TB|BT)/i);
        if (match) {
          root.direction = match[1].toUpperCase();
          continue;
        }

        match = line.match(/^direction\\s+(LR|RL|TB|BT)/i);
        if (match) {
          currentGroup().direction = match[1].toUpperCase();
          continue;
        }

        match = line.match(/^subgraph\\s+([A-Za-z0-9_.:-]+)(?:\\s*\\["([^"]+)"\\])?/);
        if (match) {
          const id = match[1];
          const group = {
            id,
            label: cleanLabel(match[2] || id),
            direction: 'TB',
            children: [],
            parent: currentGroup().id,
            x: 0,
            y: 0,
            width: 0,
            height: 0
          };
          groups.set(id, group);
          addChild(currentGroup(), { type: 'group', id });
          stack.push(group);
          continue;
        }

        if (/^end\\b/i.test(line)) {
          if (stack.length > 1) stack.pop();
          continue;
        }

        match = line.match(/^class\\s+(.+?)\\s+([A-Za-z0-9_-]+)\\s*;?\$/);
        if (match) {
          for (const id of match[1].split(',')) {
            const node = nodes.get(id.trim());
            if (node) node.classes.add(match[2]);
          }
          continue;
        }

        match = line.match(/^([A-Za-z0-9_.:-]+)\\s*(\\[\\([\\s\\S]+?\\)\\]|\\[[\\s\\S]+?\\])/);
        if (match) {
          const parsed = parseNodeLabel(match[2]);
          if (parsed) {
            const isComponent = /<<\\s*component\\s*>>/i.test(parsed.label);
            ensureNode(
              match[1],
              parsed.label,
              parsed.kind === 'database' ? 'database' : isComponent ? 'component' : 'node'
            );
          }
        }

        match = line.match(/^([A-Za-z0-9_.:-]+)\\s*[-.]+>\\|([^|]*)\\|\\s*([A-Za-z0-9_.:-]+)/) ||
          line.match(/^([A-Za-z0-9_.:-]+)\\s*[-.]+>\\s*([A-Za-z0-9_.:-]+)/);
        if (match) {
          const from = match[1];
          const label = match.length === 4 ? cleanLabel(match[2]) : '';
          const to = match.length === 4 ? match[3] : match[2];
          ensureNode(from, from, 'node');
          ensureNode(to, to, 'node');
          edges.push({ from, to, label });
        }
      }

      for (const node of nodes.values()) {
        if (node.classes.has('component')) node.kind = 'component';
        if (node.classes.has('database')) node.kind = 'database';
        if (node.classes.has('external') && node.kind !== 'component') node.kind = 'external';
        if (/<<\\s*component\\s*>>/i.test(node.rawLabel)) node.kind = 'component';
      }

      return { root, groups, nodes, edges, interfaces };
    }

    function wrapWords(text, maxChars) {
      const explicitLines = String(text || '').split('\\n');
      const result = [];
      for (const explicitLine of explicitLines) {
        const words = explicitLine.trim().split(/\\s+/).filter(Boolean);
        let line = '';
        for (const word of words) {
          if (!line) {
            line = word;
          } else if ((line + ' ' + word).length <= maxChars) {
            line += ' ' + word;
          } else {
            result.push(line);
            line = word;
          }
        }
        if (line) result.push(line);
      }
      return result.length > 0 ? result : [''];
    }

    function measureComponentDiagram(model) {
      const nodeGap = 52;
      const groupGap = 96;
      const paddingX = 42;
      const paddingY = 50;
      const titleHeight = 30;

      for (const node of model.nodes.values()) {
        node.lines = wrapWords(node.label, node.kind === 'component' ? 28 : 24);
        const longest = node.lines.reduce((max, line) => Math.max(max, line.length), 0);
        node.width = Math.max(
          node.kind === 'component' ? 300 : 170,
          Math.min(420, longest * 8 + (node.kind === 'component' ? 84 : 48))
        );
        node.height = Math.max(64, 36 + node.lines.length * 18);
        if (node.kind === 'database') {
          node.width = Math.max(node.width, 220);
          node.height += 12;
        }
      }

      function measureGroup(group) {
        const children = group.children;
        if (children.length === 0) {
          group.width = 240;
          group.height = 120;
          return group;
        }

        const childBoxes = children.map((child) => {
          return child.type === 'node'
            ? model.nodes.get(child.id)
            : measureGroup(model.groups.get(child.id));
        }).filter(Boolean);
        const isHorizontal = group.direction === 'LR' || group.direction === 'RL';
        if (isHorizontal) {
          group.width = childBoxes.reduce((sum, box) => sum + box.width, 0) +
            groupGap * Math.max(0, childBoxes.length - 1) +
            paddingX * 2;
          group.height = Math.max(...childBoxes.map((box) => box.height)) + paddingY * 2 + titleHeight;
        } else {
          group.width = Math.max(...childBoxes.map((box) => box.width)) + paddingX * 2;
          group.height = childBoxes.reduce((sum, box) => sum + box.height, 0) +
            nodeGap * Math.max(0, childBoxes.length - 1) +
            paddingY * 2 + titleHeight;
        }
        return group;
      }

      measureGroup(model.root);
    }

    function placeComponentDiagram(model) {
      const nodeGap = 52;
      const groupGap = 96;
      const paddingX = 42;
      const paddingY = 50;
      const titleHeight = 30;

      function placeGroup(group, x, y) {
        group.x = x;
        group.y = y;
        const children = group.children
          .map((child) => child.type === 'node' ? model.nodes.get(child.id) : model.groups.get(child.id))
          .filter(Boolean);
        const isHorizontal = group.direction === 'LR' || group.direction === 'RL';
        if (isHorizontal) {
          let cursorX = x + paddingX;
          const baseY = y + paddingY + titleHeight;
          for (const child of children) {
            const childY = baseY + (group.height - paddingY * 2 - titleHeight - child.height) / 2;
            if (model.nodes.has(child.id)) {
              child.x = cursorX;
              child.y = childY;
            } else {
              placeGroup(child, cursorX, childY);
            }
            cursorX += child.width + groupGap;
          }
        } else {
          let cursorY = y + paddingY + titleHeight;
          for (const child of children) {
            const childX = x + (group.width - child.width) / 2;
            if (model.nodes.has(child.id)) {
              child.x = childX;
              child.y = cursorY;
            } else {
              placeGroup(child, childX, cursorY);
            }
            cursorY += child.height + nodeGap;
          }
        }
      }

      placeGroup(model.root, 24, 24);
    }

    function escapeXml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function componentGlyph(x, y) {
      return '<g class="component-glyph" transform="translate(' + x + ' ' + y + ')">' +
        '<rect x="8" y="0" width="16" height="22" fill="none" stroke="#52627a" stroke-width="2"/>' +
        '<rect x="0" y="4" width="12" height="6" fill="#f8fbff" stroke="#52627a" stroke-width="2"/>' +
        '<rect x="0" y="14" width="12" height="6" fill="#f8fbff" stroke="#52627a" stroke-width="2"/>' +
        '</g>';
    }

    function renderNode(node) {
      const classes = ['uml-node', 'uml-node-' + node.kind].join(' ');
      let shape = '';
      if (node.kind === 'database') {
        shape =
          '<path d="M ' + node.x + ' ' + (node.y + 14) +
          ' C ' + node.x + ' ' + (node.y - 4) + ' ' + (node.x + node.width) + ' ' + (node.y - 4) + ' ' + (node.x + node.width) + ' ' + (node.y + 14) +
          ' L ' + (node.x + node.width) + ' ' + (node.y + node.height - 14) +
          ' C ' + (node.x + node.width) + ' ' + (node.y + node.height + 4) + ' ' + node.x + ' ' + (node.y + node.height + 4) + ' ' + node.x + ' ' + (node.y + node.height - 14) +
          ' Z" class="' + classes + '"/>' +
          '<path d="M ' + node.x + ' ' + (node.y + 14) + ' C ' + node.x + ' ' + (node.y + 32) + ' ' + (node.x + node.width) + ' ' + (node.y + 32) + ' ' + (node.x + node.width) + ' ' + (node.y + 14) + '" class="uml-db-top"/>';
      } else {
        shape = '<rect x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="0" class="' + classes + '"/>';
      }

      const textX = node.x + (node.kind === 'component' ? 22 : node.width / 2);
      const textAnchor = node.kind === 'component' ? 'start' : 'middle';
      const totalTextHeight = node.lines.length * 18;
      let textY = node.y + (node.height - totalTextHeight) / 2 + 14;
      let text = '<text class="uml-label" text-anchor="' + textAnchor + '">';
      for (const line of node.lines) {
        text += '<tspan x="' + textX + '" y="' + textY + '">' + escapeXml(line) + '</tspan>';
        textY += 18;
      }
      text += '</text>';

      const glyph = node.kind === 'component'
        ? componentGlyph(node.x + node.width - 34, node.y + 12)
        : '';
      return '<g id="uml-node-' + escapeXml(node.id) + '">' + shape + text + glyph + '</g>';
    }

    function renderGroups(model) {
      const groups = Array.from(model.groups.values())
        .filter((group) => group.id !== 'root')
        .sort((a, b) => b.width * b.height - a.width * a.height);
      return groups.map((group) => {
        return '<g class="uml-group">' +
          '<rect x="' + group.x + '" y="' + group.y + '" width="' + group.width + '" height="' + group.height + '" rx="0"/>' +
          '<text class="uml-group-title" x="' + (group.x + group.width / 2) + '" y="' + (group.y + 26) + '" text-anchor="middle">' + escapeXml(group.label) + '</text>' +
          '</g>';
      }).join('');
    }

    function nodeAnchor(node, target) {
      const cx = node.x + node.width / 2;
      const cy = node.y + node.height / 2;
      const tx = target.x + target.width / 2;
      const ty = target.y + target.height / 2;
      const dx = tx - cx;
      const dy = ty - cy;
      if (Math.abs(dx) >= Math.abs(dy)) {
        return { x: dx >= 0 ? node.x + node.width : node.x, y: cy };
      }
      return { x: cx, y: dy >= 0 ? node.y + node.height : node.y };
    }

    function interfaceFor(model, edge) {
      return model.interfaces.find((item) => {
        return item.consumer === edge.from && item.provider === edge.to;
      });
    }

    function renderInterfaceSymbol(midX, midY, angle) {
      return '<g class="uml-interface" transform="translate(' + midX + ' ' + midY + ') rotate(' + angle + ')">' +
        '<circle cx="-9" cy="0" r="8" />' +
        '<path d="M 14 -9 A 9 9 0 1 0 14 9" />' +
        '</g>';
    }

    function renderEdges(model) {
      const marker = '<defs><marker id="uml-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#52627a"/></marker></defs>';
      const rendered = model.edges.map((edge) => {
        const from = model.nodes.get(edge.from);
        const to = model.nodes.get(edge.to);
        if (!from || !to) return '';
        const start = nodeAnchor(from, to);
        const end = nodeAnchor(to, from);
        const midX = (start.x + end.x) / 2;
        const midY = (start.y + end.y) / 2;
        const angle = Math.atan2(end.y - start.y, end.x - start.x) * 180 / Math.PI;
        const iface = interfaceFor(model, edge);
        const markerEnd = iface ? '' : ' marker-end="url(#uml-arrow)"';
        const label = edge.label
          ? '<text class="uml-edge-label" x="' + midX + '" y="' + (midY - 24) + '" text-anchor="middle">' + escapeXml(edge.label) + '</text>'
          : '';
        const symbol = iface ? renderInterfaceSymbol(midX, midY, angle) : '';
        return '<g class="uml-edge">' +
          '<line x1="' + start.x + '" y1="' + start.y + '" x2="' + end.x + '" y2="' + end.y + '"' + markerEnd + '/>' +
          label + symbol + '</g>';
      }).join('');
      return marker + rendered;
    }

    function renderUmlComponentDiagram(source) {
      const model = parseComponentFlowchart(source);
      measureComponentDiagram(model);
      placeComponentDiagram(model);
      const width = Math.ceil(model.root.width + 48);
      const height = Math.ceil(model.root.height + 48);
      const style = '<style>' +
        '.uml-canvas{background:#f8fbff;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}' +
        '.uml-group rect{fill:none;stroke:#94a3b8;stroke-width:1.8;stroke-dasharray:7 7;}' +
        '.uml-group-title{font-size:17px;font-weight:700;fill:#273244;}' +
        '.uml-node{fill:#eef6ff;stroke:#52627a;stroke-width:2;}' +
        '.uml-node-external{fill:#fff7ed;stroke:#9a5b23;stroke-dasharray:6 4;}' +
        '.uml-node-database{fill:#f8fafc;stroke:#52627a;}' +
        '.uml-db-top{fill:none;stroke:#52627a;stroke-width:2;}' +
        '.uml-label{font-size:15px;font-weight:650;fill:#1f2937;}' +
        '.uml-edge line{stroke:#52627a;stroke-width:2.2;}' +
        '.uml-edge-label{font-size:13px;font-weight:650;fill:#273244;paint-order:stroke;stroke:#f8fbff;stroke-width:5px;stroke-linejoin:round;}' +
        '.uml-interface circle{fill:#f8fbff;stroke:#52627a;stroke-width:2.2;}' +
        '.uml-interface path{fill:none;stroke:#52627a;stroke-width:2.2;stroke-linecap:round;}' +
        '</style>';
      return '<svg class="uml-canvas" xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">' +
        style + renderEdges(model) + renderGroups(model) +
        Array.from(model.nodes.values()).map(renderNode).join('') +
        '</svg>';
    }

    async function renderDiagram() {
      const timeout = window.setTimeout(function() {
        showError('Mermaid render timed out after $renderTimeoutMs ms.');
      }, $renderTimeoutMs);
      try {
        const source = decodeUtf8Base64(encodedSource);
        if (isComponentDiagramSource(source)) {
          try {
            diagram.innerHTML = renderUmlComponentDiagram(source);
            finished = true;
            window.clearTimeout(timeout);
            return;
          } catch (componentError) {
            console.warn('UML component renderer fell back to Mermaid', componentError);
          }
        }
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
