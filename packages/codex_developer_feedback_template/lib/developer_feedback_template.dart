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
typedef DeveloperFeedbackBridgeSubmitBatch =
    Future<void> Function(DeveloperFeedbackBatch batch);

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
const developerFeedbackPresetDropdownKey = Key(
  'developer-feedback-preset-dropdown',
);
const developerFeedbackReleaseWhenCompleteKey = Key(
  'developer-feedback-release-when-complete',
);
const developerFeedbackSendBatchKey = Key('developer-feedback-send-batch');
const developerFeedbackPreviewItemKey = Key('developer-feedback-preview-item');
const developerFeedbackPreviewThumbnailKey = Key(
  'developer-feedback-preview-thumbnail',
);
const developerFeedbackPreviewBoundsKey = Key(
  'developer-feedback-preview-bounds',
);
const developerFeedbackPreviewAudioKey = Key(
  'developer-feedback-preview-audio',
);
const developerFeedbackRunsKey = Key('developer-feedback-runs');
const developerFeedbackRunStatusKey = Key('developer-feedback-run-status');
const developerFeedbackRefreshRunKey = Key('developer-feedback-refresh-run');
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
    this.bridgeSubmitBatch,
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
  final DeveloperFeedbackBridgeSubmitBatch? bridgeSubmitBatch;
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
    super.bridgeSubmitBatch,
    super.httpClient,
    super.key,
  });
}

class _DeveloperFeedbackTemplateState extends State<DeveloperFeedbackTemplate> {
  final _captureKey = GlobalKey();
  final _toolbarMeasureKey = GlobalKey();
  final List<DeveloperFeedbackItem> _items = <DeveloperFeedbackItem>[];
  final List<_SubmittedFeedbackBatch> _submittedBatches =
      <_SubmittedFeedbackBatch>[];
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
                  submittedCount: _submittedBatches.length,
                  onEditModeChanged: (value) => setState(() {
                    _editMode = value;
                    if (!value) {
                      _drawing = <Offset>[];
                      _selectionReady = false;
                    }
                  }),
                  onOpenPending: _items.isEmpty ? null : _openPendingDialog,
                  onOpenRuns: _submittedBatches.isEmpty
                      ? null
                      : _openRunsDialog,
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
    final estimate = _items.isEmpty && _submittedBatches.isEmpty
        ? baseEstimate
        : pendingEstimate;
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
          _showMessage('Feedback agregado a la cola.');
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

  Future<_DeveloperFeedbackWorkflowPresets> _loadWorkflowPresets() async {
    if (widget.bridgeUrl.trim().isEmpty) {
      return _DeveloperFeedbackWorkflowPresets.fallback();
    }
    final baseUrl = widget.bridgeUrl.trim().replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.get(
        Uri.parse('$baseUrl/feedback-workflow-presets'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      return _DeveloperFeedbackWorkflowPresets.fromJson(
        jsonDecode(response.body) as Map<String, Object?>,
      );
    } catch (_) {
      return _DeveloperFeedbackWorkflowPresets.fallback();
    } finally {
      if (ownsClient) client.close();
    }
  }

  Future<bool> _submitFeedbackBatchToBridge({
    required String workflowPresetId,
    required bool releaseWhenComplete,
  }) async {
    if (_items.isEmpty) return false;
    final batch = DeveloperFeedbackBatch(
      sourceApp: widget.sourceApp,
      sourceDisplayName: widget.sourceDisplayName,
      workflowPresetId: workflowPresetId,
      releaseWhenComplete: releaseWhenComplete,
      items: List.of(_items),
    );
    final customBatchSubmit = widget.bridgeSubmitBatch;
    if (customBatchSubmit != null) {
      try {
        await customBatchSubmit(batch);
        setState(() {
          _items.clear();
          _submittedBatches.insert(0, _SubmittedFeedbackBatch.local());
        });
        _showMessage('Feedback enviado a Codex CLI.');
        return true;
      } catch (_) {
        _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
        return false;
      }
    }
    final customSubmit = widget.bridgeSubmit;
    if (customSubmit != null) {
      try {
        for (final item in List<DeveloperFeedbackItem>.of(_items)) {
          await customSubmit(item);
        }
        setState(() {
          _items.clear();
          _submittedBatches.insert(0, _SubmittedFeedbackBatch.local());
        });
        _showMessage('Feedback enviado a Codex CLI.');
        return true;
      } catch (_) {
        _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
        return false;
      }
    }
    if (widget.bridgeUrl.trim().isEmpty) return false;
    final baseUrl = widget.bridgeUrl.trim().replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.post(
        Uri.parse('$baseUrl/feedback-batches/start-session'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(batch.toBridgeJson()),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final submittedBatch = _SubmittedFeedbackBatch.fromStartResponse(
        jsonDecode(response.body) as Map<String, Object?>,
      );
      setState(() {
        _items.clear();
        if (submittedBatch != null) _submittedBatches.insert(0, submittedBatch);
      });
      _showMessage('Feedback enviado a Codex CLI.');
      return true;
    } catch (_) {
      _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
      return false;
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openPendingDialog() {
    final presetsFuture = _loadWorkflowPresets();
    var selectedPresetId = '';
    var releaseWhenComplete = false;
    var sending = false;
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
            actionsOverflowDirection: VerticalDirection.down,
            actionsOverflowAlignment: OverflowBarAlignment.end,
            content: SizedBox(
              width: dialogWidth,
              child: _items.isEmpty
                  ? const Text('No hay feedback pendiente.')
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        ConstrainedBox(
                          constraints: BoxConstraints(
                            maxHeight: math.min(
                              320.0,
                              MediaQuery.sizeOf(context).height * 0.45,
                            ),
                          ),
                          child: ListView.separated(
                            shrinkWrap: true,
                            itemCount: _items.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 20),
                            itemBuilder: (context, index) {
                              final item = _items[index];
                              return Row(
                                key: developerFeedbackPreviewItemKey,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  _FeedbackPreviewThumbnail(item: item),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: <Widget>[
                                        Text(
                                          item.comment,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          _formatSelectionBounds(
                                            item.selectionBounds,
                                          ),
                                          key:
                                              developerFeedbackPreviewBoundsKey,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(
                                            context,
                                          ).textTheme.bodySmall,
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          _formatAudioSummary(item.audio),
                                          key: developerFeedbackPreviewAudioKey,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(
                                            context,
                                          ).textTheme.bodySmall,
                                        ),
                                      ],
                                    ),
                                  ),
                                  IconButton(
                                    tooltip: 'Eliminar',
                                    onPressed: sending
                                        ? null
                                        : () {
                                            setState(() => _items.remove(item));
                                            setDialogState(() {});
                                          },
                                    icon: const Icon(Icons.delete_outline),
                                  ),
                                ],
                              );
                            },
                          ),
                        ),
                        const SizedBox(height: 16),
                        FutureBuilder<_DeveloperFeedbackWorkflowPresets>(
                          future: presetsFuture,
                          builder: (context, snapshot) {
                            final presets =
                                snapshot.data ??
                                _DeveloperFeedbackWorkflowPresets.fallback();
                            final presetIds = presets.presets
                                .map((preset) => preset.id)
                                .toSet();
                            final value =
                                selectedPresetId.isNotEmpty &&
                                    presetIds.contains(selectedPresetId)
                                ? selectedPresetId
                                : presets.defaultPresetId;
                            return DropdownButtonFormField<String>(
                              key: developerFeedbackPresetDropdownKey,
                              initialValue: value,
                              decoration: const InputDecoration(
                                labelText: 'Preset',
                                border: OutlineInputBorder(),
                              ),
                              isExpanded: true,
                              items: presets.presets
                                  .map(
                                    (preset) => DropdownMenuItem<String>(
                                      value: preset.id,
                                      child: Text(
                                        preset.name,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  )
                                  .toList(),
                              onChanged: sending
                                  ? null
                                  : (value) {
                                      if (value == null) return;
                                      setDialogState(() {
                                        selectedPresetId = value;
                                      });
                                    },
                            );
                          },
                        ),
                        Row(
                          children: <Widget>[
                            Checkbox(
                              key: developerFeedbackReleaseWhenCompleteKey,
                              value: releaseWhenComplete,
                              onChanged: sending
                                  ? null
                                  : (value) {
                                      setDialogState(() {
                                        releaseWhenComplete = value ?? false;
                                      });
                                    },
                            ),
                            Expanded(
                              child: Text(
                                compactActions
                                    ? 'Release al finalizar'
                                    : 'Generar release al finalizar',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
            ),
            actions: <Widget>[
              if (compactActions) ...<Widget>[
                IconButton(
                  key: developerFeedbackClearKey,
                  tooltip: 'Borrar todo',
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () {
                          setState(_items.clear);
                          setDialogState(() {});
                        },
                  icon: const Icon(Icons.delete_sweep_outlined),
                ),
                IconButton.filled(
                  key: developerFeedbackCopyKey,
                  tooltip: 'Copiar exportación',
                  onPressed: _items.isEmpty || sending ? null : _copyExport,
                  icon: const Icon(Icons.copy),
                ),
                IconButton.filled(
                  key: developerFeedbackSendBatchKey,
                  tooltip: sending ? 'Enviando' : 'Enviar',
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () async {
                          setDialogState(() => sending = true);
                          final presets = await presetsFuture;
                          final sent = await _submitFeedbackBatchToBridge(
                            workflowPresetId: selectedPresetId.isEmpty
                                ? presets.defaultPresetId
                                : selectedPresetId,
                            releaseWhenComplete: releaseWhenComplete,
                          );
                          if (!context.mounted) return;
                          if (sent) {
                            Navigator.of(context).pop();
                            return;
                          }
                          setDialogState(() => sending = false);
                        },
                  icon: const Icon(Icons.send),
                ),
              ] else ...<Widget>[
                TextButton(
                  key: developerFeedbackClearKey,
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () {
                          setState(_items.clear);
                          setDialogState(() {});
                        },
                  child: const Text('Borrar todo'),
                ),
                FilledButton.icon(
                  key: developerFeedbackCopyKey,
                  onPressed: _items.isEmpty || sending ? null : _copyExport,
                  icon: const Icon(Icons.copy),
                  label: const Text('Copiar exportación'),
                ),
                FilledButton.icon(
                  key: developerFeedbackSendBatchKey,
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () async {
                          setDialogState(() => sending = true);
                          final presets = await presetsFuture;
                          final sent = await _submitFeedbackBatchToBridge(
                            workflowPresetId: selectedPresetId.isEmpty
                                ? presets.defaultPresetId
                                : selectedPresetId,
                            releaseWhenComplete: releaseWhenComplete,
                          );
                          if (!context.mounted) return;
                          if (sent) {
                            Navigator.of(context).pop();
                            return;
                          }
                          setDialogState(() => sending = false);
                        },
                  icon: const Icon(Icons.send),
                  label: Text(sending ? 'Enviando' : 'Enviar'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  void _openRunsDialog() {
    var refreshing = <String>{};
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          return AlertDialog(
            title: const Text('Runs de feedback'),
            content: SizedBox(
              width: math.min(560.0, availableWidth),
              child: _submittedBatches.isEmpty
                  ? const Text('No hay runs enviados.')
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: _submittedBatches.length,
                      separatorBuilder: (_, _) => const Divider(height: 20),
                      itemBuilder: (context, index) {
                        final batch = _submittedBatches[index];
                        final batchId = batch.batchId;
                        final canRefresh =
                            batchId != null &&
                            widget.bridgeUrl.trim().isNotEmpty &&
                            !refreshing.contains(batchId);
                        return Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: <Widget>[
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    batch.title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    batch.statusLabel,
                                    key: developerFeedbackRunStatusKey,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              key: developerFeedbackRefreshRunKey,
                              tooltip: 'Actualizar',
                              onPressed: canRefresh
                                  ? () async {
                                      setDialogState(() {
                                        refreshing = {...refreshing, batchId};
                                      });
                                      await _refreshSubmittedBatch(batchId);
                                      if (!context.mounted) return;
                                      setDialogState(() {
                                        refreshing = {...refreshing}
                                          ..remove(batchId);
                                      });
                                    }
                                  : null,
                              icon: refreshing.contains(batchId)
                                  ? const SizedBox.square(
                                      dimension: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.refresh),
                            ),
                          ],
                        );
                      },
                    ),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _refreshSubmittedBatch(String batchId) async {
    final baseUrl = widget.bridgeUrl.trim().replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.get(
        Uri.parse('$baseUrl/feedback-batches/$batchId'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final updated = _SubmittedFeedbackBatch.fromStatusResponse(
        jsonDecode(response.body) as Map<String, Object?>,
      );
      setState(() {
        final index = _submittedBatches.indexWhere(
          (batch) => batch.batchId == batchId,
        );
        if (index >= 0) _submittedBatches[index] = updated;
      });
    } catch (_) {
      _showMessage('No se pudo actualizar el run.');
    } finally {
      if (ownsClient) client.close();
    }
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
    required this.submittedCount,
    required this.onEditModeChanged,
    required this.onOpenPending,
    required this.onOpenRuns,
  });

  final bool editMode;
  final int pendingCount;
  final int submittedCount;
  final ValueChanged<bool> onEditModeChanged;
  final VoidCallback? onOpenPending;
  final VoidCallback? onOpenRuns;

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
            if (submittedCount > 0) ...<Widget>[
              const SizedBox(width: 6),
              IconButton(
                key: developerFeedbackRunsKey,
                tooltip: 'Runs',
                onPressed: onOpenRuns,
                icon: Badge.count(
                  count: submittedCount,
                  child: const Icon(Icons.track_changes),
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
      title: const Text('Guardar feedback'),
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
          child: Text(_saving ? 'Guardando' : 'Guardar'),
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

class _FeedbackPreviewThumbnail extends StatelessWidget {
  const _FeedbackPreviewThumbnail({required this.item});

  final DeveloperFeedbackItem item;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.memory(
        _decodePreviewImage(item.screenshotPngBase64),
        key: developerFeedbackPreviewThumbnailKey,
        width: 72,
        height: 72,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => Container(
          width: 72,
          height: 72,
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          alignment: Alignment.center,
          child: const Icon(Icons.broken_image_outlined),
        ),
      ),
    );
  }
}

Uint8List _decodePreviewImage(String screenshotPngBase64) {
  try {
    return base64Decode(screenshotPngBase64);
  } catch (_) {
    return base64Decode(_transparentPngBase64);
  }
}

class _SubmittedFeedbackBatch {
  const _SubmittedFeedbackBatch({
    required this.status,
    this.batchId,
    this.jobId,
    this.sessionId,
    this.statusDetail,
  });

  final String? batchId;
  final String? jobId;
  final String? sessionId;
  final String status;
  final String? statusDetail;

  factory _SubmittedFeedbackBatch.local() {
    return const _SubmittedFeedbackBatch(status: 'running');
  }

  static _SubmittedFeedbackBatch? fromStartResponse(Map<String, Object?> json) {
    final batchId = json['feedback_batch_id'] as String?;
    final jobId = json['job_id'] as String?;
    final sessionId = json['session_id'] as String?;
    if ((batchId ?? '').trim().isEmpty && (jobId ?? '').trim().isEmpty) {
      return null;
    }
    return _SubmittedFeedbackBatch(
      batchId: batchId,
      jobId: jobId,
      sessionId: sessionId,
      status: (json['status'] as String?) ?? 'running',
    );
  }

  factory _SubmittedFeedbackBatch.fromStatusResponse(
    Map<String, Object?> json,
  ) {
    return _SubmittedFeedbackBatch(
      batchId: json['batch_id'] as String?,
      jobId: json['job_id'] as String?,
      sessionId: json['session_id'] as String?,
      status: (json['status'] as String?) ?? 'pending',
      statusDetail: json['status_detail'] as String?,
    );
  }

  String get title {
    if ((batchId ?? '').isNotEmpty) return 'Batch $batchId';
    if ((jobId ?? '').isNotEmpty) return 'Job $jobId';
    return 'Run local';
  }

  String get statusLabel {
    final detail = (statusDetail ?? '').trim();
    final base = 'Estado: $status';
    return detail.isEmpty ? base : '$base · $detail';
  }
}

class _FeedbackDraft {
  const _FeedbackDraft({required this.comment, required this.audio});

  final String comment;
  final DeveloperFeedbackAudioClip? audio;
}

class DeveloperFeedbackBatch {
  const DeveloperFeedbackBatch({
    required this.sourceApp,
    required this.sourceDisplayName,
    required this.workflowPresetId,
    required this.releaseWhenComplete,
    required this.items,
  });

  final String sourceApp;
  final String sourceDisplayName;
  final String workflowPresetId;
  final bool releaseWhenComplete;
  final List<DeveloperFeedbackItem> items;

  Map<String, Object?> toBridgeJson() {
    return <String, Object?>{
      'kind': 'codex.developerFeedbackBatch',
      'version': 1,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'workflowPresetId': workflowPresetId,
      'releaseWhenComplete': releaseWhenComplete,
      'items': items.map((item) => item.toBridgeJson()).toList(),
    };
  }
}

class _DeveloperFeedbackWorkflowPreset {
  const _DeveloperFeedbackWorkflowPreset({
    required this.id,
    required this.name,
  });

  final String id;
  final String name;

  factory _DeveloperFeedbackWorkflowPreset.fromJson(Map<String, Object?> json) {
    return _DeveloperFeedbackWorkflowPreset(
      id: (json['id'] as String?) ?? 'generator_only',
      name: (json['name'] as String?) ?? 'Generator only',
    );
  }
}

class _DeveloperFeedbackWorkflowPresets {
  const _DeveloperFeedbackWorkflowPresets({
    required this.defaultPresetId,
    required this.presets,
  });

  final String defaultPresetId;
  final List<_DeveloperFeedbackWorkflowPreset> presets;

  factory _DeveloperFeedbackWorkflowPresets.fromJson(
    Map<String, Object?> json,
  ) {
    final rawPresets = json['presets'];
    final presets = rawPresets is List
        ? rawPresets
              .whereType<Map>()
              .map(
                (raw) => _DeveloperFeedbackWorkflowPreset.fromJson(
                  raw.cast<String, Object?>(),
                ),
              )
              .toList()
        : <_DeveloperFeedbackWorkflowPreset>[];
    if (presets.isEmpty) return _DeveloperFeedbackWorkflowPresets.fallback();
    final defaultPresetId =
        (json['default_preset_id'] as String?) ??
        (json['defaultPresetId'] as String?) ??
        presets.first.id;
    return _DeveloperFeedbackWorkflowPresets(
      defaultPresetId: defaultPresetId,
      presets: presets,
    );
  }

  factory _DeveloperFeedbackWorkflowPresets.fallback() {
    return const _DeveloperFeedbackWorkflowPresets(
      defaultPresetId: 'generator_only',
      presets: <_DeveloperFeedbackWorkflowPreset>[
        _DeveloperFeedbackWorkflowPreset(
          id: 'generator_only',
          name: 'Generator only',
        ),
        _DeveloperFeedbackWorkflowPreset(
          id: 'generator_reviewer',
          name: 'Generator + Reviewer',
        ),
      ],
    );
  }
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

  Map<String, double> get selectionBounds => _selectionBounds(selectionPoints);

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
      'selectionBounds': selectionBounds,
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

String _formatSelectionBounds(Map<String, double> bounds) {
  return 'Bounds: x ${bounds['left']!.round()}, y ${bounds['top']!.round()}, '
      '${bounds['width']!.round()} x ${bounds['height']!.round()}';
}

String _formatAudioSummary(DeveloperFeedbackAudioClip? audio) {
  if (audio == null) return 'Audio: sin adjunto';
  return 'Audio: ${audio.durationMs} ms, ${audio.bytes.length} bytes, '
      '${audio.mimeType}';
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
