class SessionFile {
  const SessionFile({
    required this.name,
    required this.path,
    required this.kind,
    required this.contentType,
    this.text,
    this.truncated = false,
    this.entries = const [],
  });

  final String name;
  final String path;
  final String kind;
  final String contentType;
  final String? text;
  final bool truncated;
  final List<SessionFileEntry> entries;

  factory SessionFile.fromJson(Map<String, dynamic> json) => SessionFile(
        name: json['name'] as String,
        path: json['path'] as String,
        kind: json['kind'] as String,
        contentType: json['content_type'] as String,
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
