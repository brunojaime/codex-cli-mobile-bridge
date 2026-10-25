import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../models/session_file.dart';
import '../services/api_client.dart';
import '../services/html_document.dart';

class HtmlFilePreview extends StatefulWidget {
  const HtmlFilePreview(
      {super.key,
      required this.file,
      required this.apiClient,
      required this.sessionId,
      required this.onLink});
  final SessionFile file;
  final ApiClient apiClient;
  final String sessionId;
  final Future<void> Function(String) onLink;
  @override
  State<HtmlFilePreview> createState() => _HtmlFilePreviewState();
}

class _HtmlFilePreviewState extends State<HtmlFilePreview> {
  WebViewController? _controller;
  String? _source;
  String? _error;
  int _missing = 0;
  bool _code = false;
  bool _loading = true;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (widget.file.sizeBytes > maxHtmlBytes) {
        throw StateError(
            'El HTML supera el límite de vista previa de 5 MB. Podés descargarlo.');
      }
      final source = !widget.file.truncated && widget.file.text != null
          ? widget.file.text!
          : utf8.decode(
              await widget.apiClient
                  .downloadSessionFile(widget.sessionId, widget.file.path),
              allowMalformed: true);
      _source = source;
      if (kIsWeb ||
          !const {
            TargetPlatform.android,
            TargetPlatform.iOS,
            TargetPlatform.macOS
          }.contains(defaultTargetPlatform)) {
        throw StateError(
            'La vista HTML está disponible en la app Android. Podés ver el código o descargarlo.');
      }
      final prepared = await HtmlDocumentBuilder((path) async {
        final metadata =
            await widget.apiClient.getSessionFile(widget.sessionId, path);
        if (metadata.sizeBytes > maxHtmlBytes) throw StateError('Asset limit');
        return widget.apiClient
            .downloadSessionFile(widget.sessionId, metadata.path);
      }).build(source, widget.file.path).timeout(const Duration(seconds: 45));
      if (!mounted) return;
      final base = htmlDocumentUri(widget.file.path);
      final controller = WebViewController();
      await controller.setJavaScriptMode(JavaScriptMode.disabled);
      await controller.setBackgroundColor(Colors.white);
      await controller.setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: (request) {
          final uri = Uri.tryParse(request.url);
          if (uri == null) return NavigationDecision.prevent;
          if (uri.removeFragment() == base || request.url == 'about:blank') {
            return NavigationDecision.navigate;
          }
          if (const {'http', 'https'}.contains(uri.scheme) &&
              uri.origin == htmlPreviewOrigin) {
            // Reuse the file screen's server-side path resolution.
            final target = Uri.decodeComponent(uri.path.substring(1));
            widget.onLink('bridge-workspace:$target');
          } else if (const {'https', 'http', 'mailto', 'tel'}
              .contains(uri.scheme)) {
            widget.onLink(request.url);
          }
          return NavigationDecision.prevent;
        },
        onWebResourceError: (error) {
          if (mounted && error.isForMainFrame == true) {
            setState(() => _error =
                'No se pudo mostrar el HTML. Podés reintentar o ver el código.');
          }
        },
      ));
      await controller.loadHtmlString(prepared.html, baseUrl: base.toString());
      if (mounted) {
        setState(() {
          _controller = controller;
          _missing = prepared.unavailableAssets;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error is StateError
            ? error.message.toString()
            : 'No se pudo cargar el HTML. Intentá de nuevo.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(children: [
        Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Row(children: [
              const Expanded(
                  child: Text('HTML',
                      style: TextStyle(fontWeight: FontWeight.bold))),
              TextButton.icon(
                  onPressed: () => setState(() => _code = !_code),
                  icon: Icon(_code ? Icons.preview_outlined : Icons.code),
                  label: Text(_code ? 'Vista previa' : 'Ver código')),
            ])),
        if (!_code && !_loading && _error == null)
          Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
              child: Text(
                  _missing > 0
                      ? 'Vista sin scripts · Algunos recursos no están disponibles.'
                      : 'Vista sin scripts',
                  style: Theme.of(context).textTheme.bodySmall)),
        Expanded(
            child: _code
                ? SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: SelectableText(_source ?? widget.file.text ?? '',
                        style: const TextStyle(fontFamily: 'monospace')))
                : _loading
                    ? const Center(child: CircularProgressIndicator())
                    : _error != null
                        ? Center(
                            child: Padding(
                                padding: const EdgeInsets.all(24),
                                child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(_error!),
                                      TextButton(
                                          onPressed: _load,
                                          child: const Text('Reintentar'))
                                    ])))
                        : WebViewWidget(controller: _controller!)),
      ]);
}
