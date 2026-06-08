import 'dart:convert';
import 'dart:typed_data';

class FeedbackQueueItem {
  const FeedbackQueueItem({
    required this.id,
    required this.sourceApp,
    required this.comment,
    required this.createdAt,
    required this.status,
    required this.hasScreenshot,
    required this.selectionPoints,
    required this.selectionBounds,
    this.screenshotMimeType = 'image/png',
    this.screenshotPngBase64,
    this.audioMimeType,
    this.audioDurationMs,
    this.audioByteLength,
    this.hasAudio = false,
    this.audioBase64,
  });

  final String id;
  final String sourceApp;
  final String comment;
  final DateTime? createdAt;
  final String status;
  final bool hasScreenshot;
  final String screenshotMimeType;
  final String? screenshotPngBase64;
  final List<Map<String, double>> selectionPoints;
  final Map<String, double> selectionBounds;
  final String? audioMimeType;
  final int? audioDurationMs;
  final int? audioByteLength;
  final bool hasAudio;
  final String? audioBase64;

  Uint8List? get screenshotBytes {
    final value = screenshotPngBase64;
    if (value == null || value.isEmpty) return null;
    try {
      return base64Decode(value);
    } catch (_) {
      return null;
    }
  }

  factory FeedbackQueueItem.fromJson(Map<String, dynamic> json) {
    return FeedbackQueueItem(
      id: json['id'] as String? ?? '',
      sourceApp: json['source_app'] as String? ?? 'unknown',
      comment: json['comment'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      status: json['status'] as String? ?? 'pending',
      hasScreenshot: json['has_screenshot'] as bool? ?? false,
      screenshotMimeType:
          json['screenshot_mime_type'] as String? ?? 'image/png',
      screenshotPngBase64: json['screenshot_png_base64'] as String?,
      selectionPoints: _pointsFromJson(json['selection_points']),
      selectionBounds: _doubleMapFromJson(json['selection_bounds']),
      audioMimeType: json['audio_mime_type'] as String?,
      audioDurationMs: json['audio_duration_ms'] as int?,
      audioByteLength: json['audio_byte_length'] as int?,
      hasAudio: json['has_audio'] as bool? ?? false,
      audioBase64: json['audio_base64'] as String?,
    );
  }

  static List<Map<String, double>> _pointsFromJson(Object? value) {
    if (value is! List) return const <Map<String, double>>[];
    return value
        .whereType<Map>()
        .map((point) => _doubleMapFromJson(point))
        .toList(growable: false);
  }

  static Map<String, double> _doubleMapFromJson(Object? value) {
    if (value is! Map) return const <String, double>{};
    return value.map(
      (key, raw) => MapEntry(
        key.toString(),
        raw is num ? raw.toDouble() : double.tryParse('$raw') ?? 0,
      ),
    );
  }
}
