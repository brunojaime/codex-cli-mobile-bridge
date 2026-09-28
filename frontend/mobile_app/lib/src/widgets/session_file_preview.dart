import 'package:flutter/material.dart';
import 'package:pdfx/pdfx.dart';
import 'package:video_player/video_player.dart';

import '../models/session_file.dart';
import '../services/api_client.dart';

/// Native renderers only; document scripts and HTML are never executed.
class SessionFilePreview extends StatefulWidget {
  const SessionFilePreview(
      {super.key,
      required this.file,
      required this.apiClient,
      required this.sessionId});
  final SessionFile file;
  final ApiClient apiClient;
  final String sessionId;
  @override
  State<SessionFilePreview> createState() => _SessionFilePreviewState();
}

class _SessionFilePreviewState extends State<SessionFilePreview> {
  PdfControllerPinch? _pdf;
  VideoPlayerController? _media;
  bool _failed = false;
  bool _ready = false;
  int _page = 1;
  int _pages = 0;

  @override
  void initState() {
    super.initState();
    if (widget.file.previewKind == 'pdf') {
      _pdf = PdfControllerPinch(
          document: PdfDocument.openData(
        widget.apiClient
            .downloadSessionFile(widget.sessionId, widget.file.path),
      ));
    } else {
      _initMedia();
    }
  }

  Future<void> _initMedia() async {
    final controller = VideoPlayerController.networkUrl(widget.apiClient
        .sessionFileUri(widget.sessionId, widget.file.path, content: true));
    _media = controller;
    controller.addListener(_mediaChanged);
    try {
      await controller.initialize().timeout(const Duration(seconds: 30));
      if (mounted) setState(() => _ready = true);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  void _mediaChanged() {
    if (mounted && _media!.value.hasError) setState(() => _failed = true);
  }

  @override
  void dispose() {
    _pdf?.dispose();
    _media?.removeListener(_mediaChanged);
    _media?.dispose();
    super.dispose();
  }

  String _time(Duration value) =>
      '${value.inMinutes}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    if (_failed) {
      return const Center(
          child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No se pudo mostrar la vista previa. Podés descargar el archivo desde el botón superior.',
                textAlign: TextAlign.center,
              )));
    }
    if (_pdf != null) {
      return Column(children: [
        Expanded(
            child: PdfViewPinch(
          controller: _pdf!,
          onDocumentLoaded: (document) =>
              setState(() => _pages = document.pagesCount),
          onPageChanged: (page) => setState(() => _page = page),
          onDocumentError: (_) {
            if (mounted) setState(() => _failed = true);
          },
        )),
        if (_pages > 0)
          Padding(
              padding: const EdgeInsets.all(12),
              child: Text('Página $_page de $_pages')),
      ]);
    }
    if (!_ready) return const Center(child: CircularProgressIndicator());
    final controller = _media!;
    final value = controller.value;
    return Center(
        child: SingleChildScrollView(
            child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (widget.file.previewKind == 'video')
          AspectRatio(
              aspectRatio: value.aspectRatio > 0 ? value.aspectRatio : 16 / 9,
              child: VideoPlayer(controller))
        else
          const Icon(Icons.audio_file_outlined, size: 72),
        const SizedBox(height: 20),
        Text(widget.file.name, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        VideoProgressIndicator(controller,
            allowScrubbing: true,
            padding: const EdgeInsets.symmetric(vertical: 16)),
        Text('${_time(value.position)} / ${_time(value.duration)}'),
        IconButton.filled(
          tooltip: value.isPlaying ? 'Pausar' : 'Reproducir',
          icon: Icon(value.isPlaying ? Icons.pause : Icons.play_arrow),
          onPressed: () async {
            try {
              if (value.isPlaying) {
                await controller.pause();
              } else {
                if (value.position >= value.duration) {
                  await controller.seekTo(Duration.zero);
                }
                await controller.play();
              }
            } catch (_) {
              if (mounted) setState(() => _failed = true);
            }
          },
        ),
      ]),
    )));
  }
}
