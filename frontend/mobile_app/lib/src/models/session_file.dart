class SessionFile {
  const SessionFile({
    required this.name,
    required this.path,
    required this.kind,
    required this.contentType,
    this.sizeBytes = 0,
    this.text,
    this.truncated = false,
    this.entries = const [],
  });

  final String name;
  final String path;
  final String kind;
  final String contentType;
  final int sizeBytes;
  final String? text;
  final bool truncated;
  final List<SessionFileEntry> entries;

  String get extension =>
      name.contains('.') ? name.split('.').last.toLowerCase() : '';

  String get sizeLabel {
    if (sizeBytes < 1024) return '$sizeBytes B';
    if (sizeBytes < 1024 * 1024) {
      return '${(sizeBytes / 1024).toStringAsFixed(1)} KB';
    }
    return '${(sizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  String get previewKind {
    if (kind == 'directory') return kind;
    // Large files remain downloadable without allocating a full preview in RAM.
    if (sizeBytes > 50 * 1024 * 1024 && kind != 'text') return 'file';
    if (extension == 'pdf') return 'pdf';
    if (extension == 'svg') return 'svg';
    if (const {'mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'opus'}
        .contains(extension)) {
      return 'audio';
    }
    if (const {'mp4', 'webm', 'mov', 'm4v', 'mkv', 'avi', '3gp'}
        .contains(extension)) {
      return 'video';
    }
    return kind;
  }

  factory SessionFile.fromJson(Map<String, dynamic> json) => SessionFile(
        name: json['name'] as String,
        path: json['path'] as String,
        kind: json['kind'] as String,
        contentType: json['content_type'] as String,
        sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
        text: json['text'] as String?,
        truncated: json['truncated'] == true,
        entries: (json['entries'] as List<dynamic>? ?? [])
            .map((entry) =>
                SessionFileEntry.fromJson(entry as Map<String, dynamic>))
            .toList(),
      );
}

class SessionFileEntry {
  const SessionFileEntry(
      {required this.name, required this.path, required this.isDirectory});
  final String name;
  final String path;
  final bool isDirectory;

  factory SessionFileEntry.fromJson(Map<String, dynamic> json) =>
      SessionFileEntry(
        name: json['name'] as String,
        path: json['path'] as String,
        isDirectory: json['is_directory'] == true,
      );
}

bool isServerFileLink(String target) {
  final value = target.trim();
  if (value.startsWith('/') ||
      value.startsWith('./') ||
      value.startsWith('../')) {
    return true;
  }
  final uri = Uri.tryParse(value.replaceFirst(RegExp(r':\d+(?::\d+)?$'), ''));
  return value.isNotEmpty &&
      uri != null &&
      (!uri.hasScheme || uri.scheme == 'file');
}
