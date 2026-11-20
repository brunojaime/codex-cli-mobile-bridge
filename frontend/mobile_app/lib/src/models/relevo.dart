/// Relevo entre equipos (`/relevo/*`): pasar todo el trabajo en curso a otro equipo.
class RelevoDestination {
  const RelevoDestination({required this.name, required this.enabled, this.note});

  factory RelevoDestination.fromJson(Map<String, dynamic> json) => RelevoDestination(
        name: json['name'] as String,
        enabled: json['enabled'] as bool? ?? false,
        note: json['note'] as String?,
      );

  final String name;
  final bool enabled;
  final String? note;

  String get label => name.isEmpty ? name : name[0].toUpperCase() + name.substring(1);
}

class RelevoProjectResult {
  const RelevoProjectResult({required this.project, required this.state, this.destinationChatId, this.chats = const <String>[]});

  factory RelevoProjectResult.fromJson(Map<String, dynamic> json) => RelevoProjectResult(
        project: json['proyecto'] as String? ?? '',
        state: json['estado'] as String? ?? '',
        destinationChatId: json['chat_destino'] as String?,
        chats: (json['chats'] as List<dynamic>? ?? const <dynamic>[]).map((e) => '$e').toList(),
      );

  final String project;
  final String state;
  final String? destinationChatId;
  final List<String> chats;

  String get name => project.split('/').where((p) => p.isNotEmpty).lastOrNull ?? project;
  bool get isError => state.startsWith('ERROR');
}

class RelevoRun {
  const RelevoRun({
    required this.id,
    required this.status,
    this.destination,
    this.progress = const <String>[],
    this.projects = const <RelevoProjectResult>[],
    this.error,
    this.alreadyRunning = false,
  });

  factory RelevoRun.fromJson(Map<String, dynamic> json) => RelevoRun(
        id: json['id'] as String? ?? '',
        status: json['status'] as String? ?? 'none',
        destination: json['destination'] as String?,
        progress: (json['progress'] as List<dynamic>? ?? const <dynamic>[]).map((e) => '$e').toList(),
        projects: (json['projects'] as List<dynamic>? ?? const <dynamic>[])
            .map((e) => RelevoProjectResult.fromJson(e as Map<String, dynamic>))
            .toList(),
        error: json['error'] as String?,
        alreadyRunning: json['already_running'] as bool? ?? false,
      );

  final String id;
  final String status;
  final String? destination;
  final List<String> progress;
  final List<RelevoProjectResult> projects;
  final String? error;
  final bool alreadyRunning;

  bool get isRunning => status == 'running';
  bool get isNone => status == 'none';
}
