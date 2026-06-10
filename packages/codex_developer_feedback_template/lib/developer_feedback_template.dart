import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'developer_feedback_audio_recorder.dart';
import 'developer_feedback_audio_recorder_contract.dart';

typedef DeveloperFeedbackRecorderFactory =
    DeveloperFeedbackAudioRecorder Function();
typedef DeveloperFeedbackCopyText = Future<void> Function(String text);
typedef DeveloperFeedbackBridgeSubmit =
    Future<void> Function(DeveloperFeedbackItem item);

const developerFeedbackTemplateEnabled =
    bool.fromEnvironment('CODEX_FEEDBACK_TEMPLATE_ENABLED') ||
    bool.fromEnvironment('DEVELOPER_FEEDBACK_TEMPLATE_ENABLED') ||
    bool.fromEnvironment('ENABLE_DEVELOPER_FEEDBACK_TEMPLATE');
const developerFeedbackBridgeUrl = String.fromEnvironment(
  'CODEX_FEEDBACK_BRIDGE_URL',
);
const developerFeedbackSourceApp = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_APP',
  defaultValue: 'unknown',
);
const developerFeedbackSourceDisplayName = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_NAME',
);

const developerFeedbackToolbarKey = Key('developer-feedback-toolbar');
const developerFeedbackSwitchKey = Key('developer-feedback-switch');
const developerFeedbackOverlayKey = Key('developer-feedback-overlay');
const developerFeedbackCommentKey = Key('developer-feedback-comment');
const developerFeedbackSaveKey = Key('developer-feedback-save');
const developerFeedbackPendingKey = Key('developer-feedback-pending');
const developerFeedbackCopyKey = Key('developer-feedback-copy');
const developerFeedbackClearKey = Key('developer-feedback-clear');
const developerFeedbackCommentActionKey = Key(
  'developer-feedback-comment-action',
);
const developerFeedbackResetSelectionKey = Key(
  'developer-feedback-reset-selection',
);

const _transparentPngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';

class DeveloperFeedbackTemplate extends StatefulWidget {
  const DeveloperFeedbackTemplate({
    required this.child,
    required this.enabled,
    this.sourceApp = developerFeedbackSourceApp,
    this.sourceDisplayName = developerFeedbackSourceDisplayName,
    this.bridgeUrl = developerFeedbackBridgeUrl,
    this.navigatorKey,
    this.scaffoldMessengerKey,
    this.recorderFactory = createDeveloperFeedbackAudioRecorder,
    this.copyText,
    this.bridgeSubmit,
    this.httpClient,
    super.key,
  });

  final Widget child;
  final bool enabled;
  final String sourceApp;
  final String sourceDisplayName;
  final String bridgeUrl;
  final GlobalKey<NavigatorState>? navigatorKey;
  final GlobalKey<ScaffoldMessengerState>? scaffoldMessengerKey;
  final DeveloperFeedbackRecorderFactory recorderFactory;
  final DeveloperFeedbackCopyText? copyText;
  final DeveloperFeedbackBridgeSubmit? bridgeSubmit;
  final http.Client? httpClient;

  @override
  State<DeveloperFeedbackTemplate> createState() =>
      _DeveloperFeedbackTemplateState();
}

class CodexDeveloperFeedbackTemplate extends DeveloperFeedbackTemplate {
  const CodexDeveloperFeedbackTemplate({
    required super.child,
    required super.enabled,
    required super.sourceApp,
    required super.bridgeUrl,
    super.sourceDisplayName,
    super.navigatorKey,
    super.scaffoldMessengerKey,
    super.recorderFactory,
    super.copyText,
    super.bridgeSubmit,
    super.httpClient,
    super.key,
  });
}

class _DeveloperFeedbackTemplateState extends State<DeveloperFeedbackTemplate> {
  final _captureKey = GlobalKey();
  final _toolbarMeasureKey = GlobalKey();
  final List<DeveloperFeedbackItem> _items = <DeveloperFeedbackItem>[];
  var _editMode = false;
  var _dialogOpen = false;
  var _selectionReady = false;
  var _drawing = <Offset>[];
  Offset? _toolbarOffset;
  Size? _toolbarSize;

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return widget.child;
    final safePadding = MediaQuery.paddingOf(context);

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final toolbarOffset = _effectiveToolbarOffset(viewport, safePadding);
        _scheduleToolbarMeasurement(viewport, safePadding);

        return Stack(
          children: <Widget>[
            RepaintBoundary(key: _captureKey, child: widget.child),
            if (_editMode && !_dialogOpen)
              Positioned.fill(
                child: _DrawingOverlay(
                  key: developerFeedbackOverlayKey,
                  points: _drawing,
                  onStart: _startDrawing,
                  onUpdate: _updateDrawing,
                  onComplete: _completeDrawing,
                ),
              ),
            if (_editMode && !_dialogOpen && _selectionReady)
              Positioned(
                left: 16,
                right: 16,
                bottom: safePadding.bottom + 128,
                child: _SelectionActions(
                  onComment: () => _openFeedbackDialog(List.of(_drawing)),
                  onReset: _resetDrawing,
                ),
              ),
            Positioned(
              left: toolbarOffset.dx,
              top: toolbarOffset.dy,
              child: _DraggableToolbarShell(
                key: _toolbarMeasureKey,
                onDragUpdate: (delta) =>
                    _moveToolbar(delta, viewport, safePadding),
                child: _Toolbar(
                  editMode: _editMode,
                  pendingCount: _items.length,
                  onEditModeChanged: (value) => setState(() {
                    _editMode = value;
                    if (!value) {
                      _drawing = <Offset>[];
                      _selectionReady = false;
                    }
                  }),
                  onOpenPending: _items.isEmpty ? null : _openPendingDialog,
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Offset _effectiveToolbarOffset(Size viewport, EdgeInsets safePadding) {
    final current = _toolbarOffset;
    if (current != null) {
      return _clampToolbarOffset(current, viewport, safePadding);
    }
    final size = _toolbarClampSize;
    return _clampToolbarOffset(
      Offset(viewport.width - size.width - 12, safePadding.top + 12),
      viewport,
      safePadding,
    );
  }

  Offset _clampToolbarOffset(
    Offset offset,
    Size viewport,
    EdgeInsets safePadding,
  ) {
    const margin = 8.0;
    final size = _toolbarClampSize;
    final maxX = math.max(margin, viewport.width - size.width - margin);
    final maxY = math.max(
      safePadding.top + margin,
      viewport.height - size.height - safePadding.bottom - margin,
    );
    return Offset(
      offset.dx.clamp(margin, maxX),
      offset.dy.clamp(safePadding.top + margin, maxY),
    );
  }

  Size get _toolbarClampSize {
    const baseEstimate = Size(176, 48);
    const pendingEstimate = Size(320, 48);
    final measured = _toolbarSize ?? Size.zero;
    final estimate = _items.isEmpty ? baseEstimate : pendingEstimate;
    return Size(
      math.max(measured.width, estimate.width),
      math.max(measured.height, estimate.height),
    );
  }

  void _moveToolbar(Offset delta, Size viewport, EdgeInsets safePadding) {
    setState(() {
      final start = _effectiveToolbarOffset(viewport, safePadding);
      _toolbarOffset = _clampToolbarOffset(
        start + delta,
        viewport,
        safePadding,
      );
    });
  }

  void _scheduleToolbarMeasurement(Size viewport, EdgeInsets safePadding) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final renderObject = _toolbarMeasureKey.currentContext
          ?.findRenderObject();
      if (renderObject is! RenderBox || !renderObject.hasSize) return;
      final measured = renderObject.size;
      if (_toolbarSize == measured) return;
      setState(() {
        _toolbarSize = measured;
        final current = _toolbarOffset;
        if (current != null) {
          _toolbarOffset = _clampToolbarOffset(current, viewport, safePadding);
        }
      });
    });
  }

  void _startDrawing(Offset point) {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[point];
    });
  }

  void _updateDrawing(Offset point) {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[..._drawing, point];
    });
  }

  void _completeDrawing() {
    setState(() {
      _selectionReady = _hasEnoughSelection(_drawing);
      if (!_selectionReady) _drawing = <Offset>[];
    });
  }

  void _resetDrawing() {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[];
    });
  }

  Future<void> _openFeedbackDialog(List<Offset> points) async {
    if (points.isEmpty) return;
    final screenshotPngBase64 = await _captureMarkedScreenshot(points);
    if (!mounted) return;
    setState(() => _dialogOpen = true);
    await showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => _FeedbackDialog(
        recorder: widget.recorderFactory(),
        onSave: (draft) async {
          if (!mounted) return;
          final now = DateTime.now().toUtc();
          final item = DeveloperFeedbackItem(
            id: 'feedback-${now.microsecondsSinceEpoch}',
            createdAt: now,
            sourceApp: widget.sourceApp,
            sourceDisplayName: widget.sourceDisplayName,
            comment: draft.comment,
            screenshotPngBase64: screenshotPngBase64,
            selectionPoints: points,
            audio: draft.audio,
          );
          setState(() {
            _items.add(item);
            _drawing = <Offset>[];
            _selectionReady = false;
          });
          _showMessage('Feedback guardado.');
          unawaited(_submitFeedbackToBridge(item));
        },
      ),
    );
    if (mounted) {
      setState(() {
        _dialogOpen = false;
        _drawing = <Offset>[];
        _selectionReady = false;
      });
    }
  }

  Future<String> _captureMarkedScreenshot(List<Offset> points) async {
    try {
      if (_isWidgetTestBinding()) return _transparentPngBase64;
      final boundary =
          _captureKey.currentContext?.findRenderObject()
              as RenderRepaintBoundary?;
      if (boundary == null) return _transparentPngBase64;
      const pixelRatio = 1.0;
      final baseImage = await boundary
          .toImage(pixelRatio: pixelRatio)
          .timeout(const Duration(seconds: 1));
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(
        recorder,
        Rect.fromLTWH(
          0,
          0,
          baseImage.width.toDouble(),
          baseImage.height.toDouble(),
        ),
      );
      canvas.drawImage(baseImage, Offset.zero, Paint());
      if (points.length > 1) {
        final path = Path()
          ..moveTo(points.first.dx * pixelRatio, points.first.dy * pixelRatio);
        for (final point in points.skip(1)) {
          path.lineTo(point.dx * pixelRatio, point.dy * pixelRatio);
        }
        canvas.drawPath(
          path,
          Paint()
            ..color = Colors.redAccent
            ..style = PaintingStyle.stroke
            ..strokeWidth = 4 * pixelRatio
            ..strokeCap = StrokeCap.round
            ..strokeJoin = StrokeJoin.round,
        );
      }
      final markedImage = await recorder
          .endRecording()
          .toImage(baseImage.width, baseImage.height)
          .timeout(const Duration(seconds: 1));
      final byteData = await markedImage
          .toByteData(format: ui.ImageByteFormat.png)
          .timeout(const Duration(seconds: 1));
      baseImage.dispose();
      markedImage.dispose();
      if (byteData == null) return _transparentPngBase64;
      return base64Encode(
        Uint8List.view(
          byteData.buffer,
          byteData.offsetInBytes,
          byteData.lengthInBytes,
        ),
      );
    } catch (_) {
      return _transparentPngBase64;
    }
  }

  bool _isWidgetTestBinding() {
    var isTestBinding = false;
    assert(() {
      isTestBinding = WidgetsBinding.instance.runtimeType.toString().contains(
        'TestWidgetsFlutterBinding',
      );
      return true;
    }());
    return isTestBinding;
  }

  Future<void> _submitFeedbackToBridge(DeveloperFeedbackItem item) async {
    final customSubmit = widget.bridgeSubmit;
    if (customSubmit != null) {
      await customSubmit(item);
      _showMessage('Feedback enviado a Codex CLI.');
      return;
    }
    if (widget.bridgeUrl.trim().isEmpty) return;
    final baseUrl = widget.bridgeUrl.trim().replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.post(
        Uri.parse('$baseUrl/feedback-queue'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(item.toBridgeJson()),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      _showMessage('Feedback enviado a Codex CLI.');
    } catch (_) {
      _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openPendingDialog() {
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          final dialogWidth = math.min(560.0, availableWidth);
          final compactActions = MediaQuery.sizeOf(context).width < 420;
          return AlertDialog(
            title: const Text('Cola de feedback'),
            content: SizedBox(
              width: dialogWidth,
              child: _items.isEmpty
                  ? const Text('No hay feedback pendiente.')
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: _items.length,
                      separatorBuilder: (_, _) => const Divider(height: 20),
                      itemBuilder: (context, index) {
                        final item = _items[index];
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            item.comment,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            '${item.selectionPoints.length} puntos'
                            '${item.audio == null ? '' : ' · audio ${item.audio!.durationMs} ms · ${item.audio!.bytes.length} bytes'}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: IconButton(
                            tooltip: 'Eliminar',
                            onPressed: () {
                              setState(() => _items.remove(item));
                              setDialogState(() {});
                            },
                            icon: const Icon(Icons.delete_outline),
                          ),
                        );
                      },
                    ),
            ),
            actions: <Widget>[
              TextButton(
                key: developerFeedbackClearKey,
                onPressed: _items.isEmpty
                    ? null
                    : () {
                        setState(_items.clear);
                        setDialogState(() {});
                      },
                child: Text(compactActions ? 'Borrar' : 'Borrar todo'),
              ),
              FilledButton.icon(
                key: developerFeedbackCopyKey,
                onPressed: _items.isEmpty ? null : _copyExport,
                icon: const Icon(Icons.copy),
                label: Text(compactActions ? 'Copiar' : 'Copiar exportación'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _copyExport() async {
    final export = DeveloperFeedbackExport(items: List.of(_items)).toJsonText();
    try {
      final copyText = widget.copyText;
      if (copyText == null) {
        await Clipboard.setData(ClipboardData(text: export));
      } else {
        await copyText(export);
      }
      _showMessage('Cola copiada.');
    } catch (_) {
      _showMessage(
        'Exportación generada; copiala desde la integración disponible.',
      );
    }
  }

  void _showMessage(String message) {
    final messenger =
        widget.scaffoldMessengerKey?.currentState ??
        ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(SnackBar(content: Text(message)));
  }
}

class _SelectionActions extends StatelessWidget {
  const _SelectionActions({required this.onComment, required this.onReset});

  final VoidCallback onComment;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Material(
        color: Theme.of(context).colorScheme.surface,
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 8,
            runSpacing: 4,
            children: <Widget>[
              TextButton.icon(
                key: developerFeedbackResetSelectionKey,
                onPressed: onReset,
                icon: const Icon(Icons.refresh),
                label: const Text('Rehacer'),
              ),
              FilledButton.icon(
                key: developerFeedbackCommentActionKey,
                onPressed: onComment,
                icon: const Icon(Icons.mode_comment_outlined),
                label: const Text('Comentar'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DraggableToolbarShell extends StatelessWidget {
  const _DraggableToolbarShell({
    required this.child,
    required this.onDragUpdate,
    super.key,
  });

  final Widget child;
  final ValueChanged<Offset> onDragUpdate;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onPanUpdate: (details) => onDragUpdate(details.delta),
      child: child,
    );
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({
    required this.editMode,
    required this.pendingCount,
    required this.onEditModeChanged,
    required this.onOpenPending,
  });

  final bool editMode;
  final int pendingCount;
  final ValueChanged<bool> onEditModeChanged;
  final VoidCallback? onOpenPending;

  @override
  Widget build(BuildContext context) {
    return Material(
      key: developerFeedbackToolbarKey,
      color: Theme.of(context).colorScheme.surface,
      elevation: 6,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: () => onEditModeChanged(!editMode),
              child: Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    const Text('Plantilla'),
                    const SizedBox(width: 8),
                    Switch(
                      key: developerFeedbackSwitchKey,
                      value: editMode,
                      onChanged: onEditModeChanged,
                    ),
                  ],
                ),
              ),
            ),
            if (pendingCount > 0) ...<Widget>[
              const SizedBox(width: 6),
              IconButton(
                key: developerFeedbackPendingKey,
                tooltip: 'Pendientes',
                onPressed: onOpenPending,
                icon: Badge.count(
                  count: pendingCount,
                  child: const Icon(Icons.pending_actions),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DrawingOverlay extends StatefulWidget {
  const _DrawingOverlay({
    required this.points,
    required this.onStart,
    required this.onUpdate,
    required this.onComplete,
    super.key,
  });

  final List<Offset> points;
  final ValueChanged<Offset> onStart;
  final ValueChanged<Offset> onUpdate;
  final VoidCallback onComplete;

  @override
  State<_DrawingOverlay> createState() => _DrawingOverlayState();
}

class _DrawingOverlayState extends State<_DrawingOverlay> {
  final List<Offset> _gesturePoints = <Offset>[];

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onPanStart: (details) => _start(details.localPosition),
      onPanUpdate: (details) => _update(details.localPosition),
      onPanEnd: (_) => _complete(),
      child: CustomPaint(
        painter: _SelectionPainter(
          _gesturePoints.isEmpty ? widget.points : _gesturePoints,
        ),
        child: const SizedBox.expand(),
      ),
    );
  }

  void _start(Offset point) {
    setState(() {
      _gesturePoints
        ..clear()
        ..add(point);
    });
    widget.onStart(point);
  }

  void _update(Offset point) {
    setState(() => _gesturePoints.add(point));
    widget.onUpdate(point);
  }

  void _complete() {
    if (_gesturePoints.isEmpty) return;
    widget.onComplete();
    setState(_gesturePoints.clear);
  }
}

bool _hasEnoughSelection(List<Offset> points) {
  const minimumSelectionDistance = 180.0;
  const minimumSelectionPoints = 8;
  const minimumSelectionSpan = 72.0;
  if (points.length < minimumSelectionPoints) return false;
  var left = points.first.dx;
  var right = points.first.dx;
  var top = points.first.dy;
  var bottom = points.first.dy;
  var distance = 0.0;
  for (var i = 1; i < points.length; i += 1) {
    final point = points[i];
    left = math.min(left, point.dx);
    right = math.max(right, point.dx);
    top = math.min(top, point.dy);
    bottom = math.max(bottom, point.dy);
    distance += (points[i] - points[i - 1]).distance;
  }
  return distance >= minimumSelectionDistance &&
      right - left >= minimumSelectionSpan &&
      bottom - top >= minimumSelectionSpan;
}

class _SelectionPainter extends CustomPainter {
  const _SelectionPainter(this.points);

  final List<Offset> points;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
      Offset.zero & size,
      Paint()..color = const Color(0x22000000),
    );
    if (points.length < 2) return;
    final paint = Paint()
      ..color = Colors.redAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_SelectionPainter oldDelegate) =>
      !listEquals(points, oldDelegate.points);
}

class _FeedbackDialog extends StatefulWidget {
  const _FeedbackDialog({required this.recorder, required this.onSave});

  final DeveloperFeedbackAudioRecorder recorder;
  final Future<void> Function(_FeedbackDraft draft) onSave;

  @override
  State<_FeedbackDialog> createState() => _FeedbackDialogState();
}

class _FeedbackDialogState extends State<_FeedbackDialog> {
  static const _maxRecordingDuration = Duration(seconds: 30);

  final _commentController = TextEditingController();
  DeveloperFeedbackAudioClip? _audio;
  var _recording = false;
  var _audioUnsupported = false;
  var _audioBusy = false;
  var _saving = false;
  Timer? _maxRecordingTimer;

  @override
  void initState() {
    super.initState();
    _commentController.addListener(() => setState(() {}));
    widget.recorder.isSupported.then((supported) {
      if (mounted) setState(() => _audioUnsupported = !supported);
    });
  }

  @override
  void dispose() {
    _maxRecordingTimer?.cancel();
    _commentController.dispose();
    unawaited(widget.recorder.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final availableWidth = math.max(0.0, MediaQuery.sizeOf(context).width - 48);
    final dialogWidth = math.min(460.0, availableWidth);
    final compactDialog = MediaQuery.sizeOf(context).width < 420;
    return AlertDialog(
      title: const Text('Enviar feedback'),
      content: SizedBox(
        width: dialogWidth,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              key: developerFeedbackCommentKey,
              controller: _commentController,
              minLines: 3,
              maxLines: 5,
              decoration: const InputDecoration(
                labelText: 'Comentario',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                key: const Key('developer-feedback-audio'),
                onPressed: _audioBusy || _saving
                    ? null
                    : _audioUnsupported
                    ? _showUnsupportedAudio
                    : _toggleAudio,
                icon: Icon(_recording ? Icons.stop : Icons.mic),
                label: Text(
                  _audioBusy
                      ? (compactDialog ? 'Procesando' : 'Procesando audio')
                      : _audio == null
                      ? (_recording
                            ? (compactDialog
                                  ? 'Detener audio'
                                  : 'Detener audio (30 s máx.)')
                            : (compactDialog
                                  ? 'Grabar audio'
                                  : 'Grabar audio (30 s máx.)'))
                      : 'Audio adjunto',
                ),
              ),
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          key: developerFeedbackSaveKey,
          onPressed:
              _commentController.text.trim().isEmpty ||
                  _recording ||
                  _audioBusy ||
                  _saving
              ? null
              : () async {
                  setState(() => _saving = true);
                  await widget.onSave(
                    _FeedbackDraft(
                      comment: _commentController.text.trim(),
                      audio: _audio,
                    ),
                  );
                  if (!context.mounted) return;
                  Navigator.of(context).pop();
                },
          child: Text(_saving ? 'Enviando' : 'Enviar'),
        ),
      ],
    );
  }

  Future<void> _toggleAudio() async {
    if (!mounted) return;
    if (_audioBusy) return;
    if (_recording) {
      await _stopRecording();
      return;
    }

    setState(() {
      _audioBusy = true;
      _audio = null;
    });
    try {
      await widget.recorder.start();
      if (!mounted) return;
      _maxRecordingTimer?.cancel();
      _maxRecordingTimer = Timer(
        _maxRecordingDuration,
        () => unawaited(_stopRecording()),
      );
      setState(() {
        _recording = true;
        _audioBusy = false;
      });
    } catch (error) {
      await widget.recorder.cancel();
      if (!mounted) return;
      setState(() {
        _recording = false;
        _audioBusy = false;
        if (error is UnsupportedError) _audioUnsupported = true;
      });
      if (error is UnsupportedError) {
        _showUnsupportedAudio();
      } else {
        _showAudioError();
      }
    }
  }

  Future<void> _stopRecording() async {
    if (!mounted) return;
    if (_audioBusy) return;
    setState(() => _audioBusy = true);
    _maxRecordingTimer?.cancel();
    _maxRecordingTimer = null;
    try {
      final clip = await widget.recorder.stop();
      if (!mounted) return;
      setState(() {
        _audio = clip;
        _recording = false;
        _audioBusy = false;
      });
    } catch (_) {
      await widget.recorder.cancel();
      if (!mounted) return;
      setState(() {
        _audio = null;
        _recording = false;
        _audioBusy = false;
      });
      _showAudioError();
    }
  }

  void _showUnsupportedAudio() {
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text('Audio no soportado en este entorno.')),
    );
  }

  void _showAudioError() {
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(const SnackBar(content: Text('No se pudo grabar audio.')));
  }
}

class _FeedbackDraft {
  const _FeedbackDraft({required this.comment, required this.audio});

  final String comment;
  final DeveloperFeedbackAudioClip? audio;
}

class DeveloperFeedbackItem {
  const DeveloperFeedbackItem({
    required this.id,
    required this.createdAt,
    this.sourceApp = 'unknown',
    this.sourceDisplayName = '',
    required this.comment,
    required this.screenshotPngBase64,
    required this.selectionPoints,
    required this.audio,
  });

  final String id;
  final DateTime createdAt;
  final String sourceApp;
  final String sourceDisplayName;
  final String comment;
  final String screenshotPngBase64;
  final List<Offset> selectionPoints;
  final DeveloperFeedbackAudioClip? audio;

  Map<String, Object?> toJson() {
    final bounds = _selectionBounds(selectionPoints);
    final hasAudioBytes = audio != null && audio!.bytes.isNotEmpty;
    return <String, Object?>{
      'kind': 'codex.developerFeedback',
      'version': 1,
      'id': id,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'createdAt': createdAt.toIso8601String(),
      'queue': 'codexCli',
      'status': 'pending',
      'comment': comment,
      'screenshotMimeType': 'image/png',
      'screenshotPngBase64': screenshotPngBase64,
      'selectionPoints': selectionPoints
          .map((point) => <String, double>{'x': point.dx, 'y': point.dy})
          .toList(),
      'selectionBounds': bounds,
      'hasAudio': hasAudioBytes,
      if (audio != null) 'audioMimeType': audio!.mimeType,
      if (audio != null) 'audioDurationMs': audio!.durationMs,
      if (audio != null) 'audioByteLength': audio!.bytes.length,
      if (hasAudioBytes) 'audioBase64': base64Encode(audio!.bytes),
    };
  }

  Map<String, Object?> toBridgeJson() {
    final hasAudioBytes = audio != null && audio!.bytes.isNotEmpty;
    return <String, Object?>{
      'kind': 'codex.developerFeedback',
      'version': 1,
      'id': id,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'queue': 'codexCli',
      'status': 'pending',
      'comment': comment,
      'createdAt': createdAt.toIso8601String(),
      'screenshotMimeType': 'image/png',
      'screenshotPngBase64': screenshotPngBase64,
      'selectionPoints': selectionPoints
          .map((point) => <String, double>{'x': point.dx, 'y': point.dy})
          .toList(),
      'selectionBounds': _selectionBounds(selectionPoints),
      'hasAudio': hasAudioBytes,
      if (audio != null) 'audioMimeType': audio!.mimeType,
      if (audio != null) 'audioDurationMs': audio!.durationMs,
      if (audio != null) 'audioByteLength': audio!.bytes.length,
      if (hasAudioBytes) 'audioBase64': base64Encode(audio!.bytes),
    };
  }

  Map<String, double> _selectionBounds(List<Offset> points) {
    var minX = points.first.dx;
    var maxX = points.first.dx;
    var minY = points.first.dy;
    var maxY = points.first.dy;
    for (final point in points.skip(1)) {
      minX = point.dx < minX ? point.dx : minX;
      maxX = point.dx > maxX ? point.dx : maxX;
      minY = point.dy < minY ? point.dy : minY;
      maxY = point.dy > maxY ? point.dy : maxY;
    }
    return <String, double>{
      'left': minX,
      'top': minY,
      'width': maxX - minX,
      'height': maxY - minY,
    };
  }
}

class DeveloperFeedbackExport {
  const DeveloperFeedbackExport({required this.items});

  final List<DeveloperFeedbackItem> items;

  String toJsonText() {
    return const JsonEncoder.withIndent('  ').convert(<String, Object?>{
      'kind': 'codex.developerFeedbackExport',
      'version': 1,
      'generatedAt': DateTime.now().toUtc().toIso8601String(),
      'items': items.map((item) => item.toJson()).toList(),
    });
  }
}
