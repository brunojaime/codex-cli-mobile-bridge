import 'dart:typed_data';

import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../models/session_file.dart';
import '../services/api_client.dart';

typedef SaveSessionFile = Future<void> Function(
    Uint8List bytes, SessionFile file);

class SessionFileScreen extends StatefulWidget {
  const SessionFileScreen({
    super.key,
    required this.apiClient,
    required this.sessionId,
    required this.target,
    required this.onExternalLink,
    this.relativeTo,
    this.onSave,
  });

  final ApiClient apiClient;
  final String sessionId;
  final String target;
  final String? relativeTo;
  final Future<void> Function(String) onExternalLink;
  final SaveSessionFile? onSave;

  @override
  State<SessionFileScreen> createState() => _SessionFileScreenState();
}

class _SessionFileScreenState extends State<SessionFileScreen> {
  SessionFile? _file;
  String? _error;
  bool _loading = true;
  bool _saving = false;

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
      final file = await widget.apiClient.getSessionFile(
        widget.sessionId,
        widget.target,
        relativeTo: widget.relativeTo,
      );
      if (mounted) setState(() => _file = file);
    } catch (error) {
      if (mounted) {
        setState(() => _error = '$error'.replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(String target, {bool fromRoot = false}) async {
    if (target.startsWith('#')) return;
    if (!isServerFileLink(target)) {
      await widget.onExternalLink(target);
      return;
    }
    await Navigator.of(context).push<void>(MaterialPageRoute(
      builder: (_) => SessionFileScreen(
        apiClient: widget.apiClient,
        sessionId: widget.sessionId,
        target: target,
        relativeTo: fromRoot ? null : _file?.path,
        onExternalLink: widget.onExternalLink,
        onSave: widget.onSave,
      ),
    ));
  }

  Future<void> _save() async {
    final file = _file;
    if (file == null || _saving) return;
    setState(() => _saving = true);
    try {
      final bytes = await widget.apiClient
          .downloadSessionFile(widget.sessionId, file.path);
      if (!mounted) return;
      if (widget.onSave != null) {
        await widget.onSave!(bytes, file);
      } else {
        final dot = file.name.lastIndexOf('.');
        final saved = await FileSaver.instance.saveAs(
          name: dot < 0 ? file.name : file.name.substring(0, dot),
          fileExtension: dot < 0 ? '' : file.name.substring(dot + 1),
          bytes: bytes,
          mimeType: MimeType.custom,
          customMimeType: file.contentType,
        );
        if (saved == null) return;
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Archivo guardado.')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content:
                  Text('No se pudo guardar el archivo. Intentá de nuevo.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(_file?.name ?? 'Archivo del proyecto'),
          actions: [
            if (_file != null && _file!.kind != 'directory')
              IconButton(
                tooltip: 'Descargar archivo',
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.download_rounded),
              ),
          ],
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      const Icon(Icons.description_outlined, size: 40),
                      const SizedBox(height: 16),
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      OutlinedButton(
                          onPressed: _load, child: const Text('Reintentar')),
                    ]),
                  ))
                : _content(_file!),
      );

  Widget _content(SessionFile file) {
    if (file.kind == 'image') {
      return InteractiveViewer(
        minScale: 0.5,
        maxScale: 5,
        child: Center(
            child: _image(
                widget.apiClient
                    .sessionFileUri(
                      widget.sessionId,
                      file.path,
                      content: true,
                    )
                    .toString(),
                file.name)),
      );
    }
    return SingleChildScrollView(
        child: Center(
            child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 900),
      child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (file.truncated)
                const Padding(
                  padding: EdgeInsets.only(bottom: 16),
                  child: Text(
                      'Vista previa parcial. Descargá el archivo para verlo completo.'),
                ),
              if (file.kind == 'directory') ...[
                if (file.entries.isEmpty)
                  const Text('No hay archivos disponibles en esta carpeta.'),
                for (final entry in file.entries)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(entry.isDirectory
                        ? Icons.folder_outlined
                        : Icons.description_outlined),
                    title: Text(entry.name),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _open(entry.path, fromRoot: true),
                  ),
              ] else if (file.kind == 'text') ...[
                if (file.name.toLowerCase().endsWith('.md') ||
                    file.name.toLowerCase().endsWith('.markdown'))
                  MarkdownBody(
                    data: file.text ?? '',
                    selectable: true,
                    onTapLink: (label, href, title) {
                      if (href != null) _open(href);
                    },
                    imageBuilder: (uri, title, alt) {
                      final target = uri.toString();
                      final url = isServerFileLink(target)
                          ? widget.apiClient
                              .sessionFileUri(widget.sessionId, target,
                                  relativeTo: file.path, content: true)
                              .toString()
                          : target;
                      return InkWell(
                          onTap: () => _open(target),
                          child: _image(url, alt ?? 'Captura'));
                    },
                  )
                else
                  SelectableText(file.text ?? '',
                      style: const TextStyle(
                          fontFamily: 'monospace', height: 1.5)),
              ] else ...[
                const Icon(Icons.description_outlined, size: 48),
                const SizedBox(height: 16),
                Text(file.name, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                const Text(
                    'Descargá este archivo para abrirlo con una aplicación del teléfono.'),
                const SizedBox(height: 16),
                FilledButton.icon(
                    onPressed: _saving ? null : _save,
                    icon: const Icon(Icons.download_rounded),
                    label: const Text('Descargar archivo')),
              ],
            ],
          )),
    )));
  }

  Widget _image(String url, String label) => Image.network(
        url,
        semanticLabel: label,
        fit: BoxFit.contain,
        loadingBuilder: (_, child, progress) => progress == null
            ? child
            : const Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator()),
        errorBuilder: (context, error, stack) => Padding(
            padding: const EdgeInsets.all(24),
            child: Text('No se pudo cargar la imagen: $label')),
      );
}
