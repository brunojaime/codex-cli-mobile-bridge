/// Dashboard view of agent runs (`GET /runs/overview`, `WS /ws/runs`).
library;

enum RunState { needsYou, working, queued, failed, done, stopped }

RunState _parseState(Object? value) => switch (value) {
      'needs_you' => RunState.needsYou,
      'working' => RunState.working,
      'queued' => RunState.queued,
      'failed' => RunState.failed,
      'stopped' => RunState.stopped,
      _ => RunState.done,
    };

DateTime? _date(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toLocal() : null;

/// Something the agent is waiting for: a permission, a question or a plan.
class PendingInteraction {
  const PendingInteraction({
    required this.requestId,
    required this.kind,
    required this.title,
    required this.detail,
    this.toolName,
    this.input = const <String, dynamic>{},
    this.suggestions = const <Object?>[],
  });

  factory PendingInteraction.fromJson(Map<String, dynamic> json) =>
      PendingInteraction(
        requestId: (json['request_id'] ?? '').toString(),
        kind: (json['kind'] ?? 'permission').toString(),
        title: (json['title'] ?? '').toString(),
        detail: (json['detail'] ?? '').toString(),
        toolName: json['tool_name'] as String?,
        input: json['input'] is Map
            ? Map<String, dynamic>.from(json['input'] as Map)
            : const <String, dynamic>{},
        suggestions: json['suggestions'] is List
            ? List<Object?>.from(json['suggestions'] as List)
            : const <Object?>[],
      );

  final String requestId;

  /// `permission`, `question` or `plan`.
  final String kind;
  final String title;
  final String detail;
  final String? toolName;
  final Map<String, dynamic> input;
  final List<Object?> suggestions;

  bool get isQuestion => kind == 'question';
  bool get isPlan => kind == 'plan';
  bool get canRemember => suggestions.isNotEmpty;

  List<InteractionQuestion> get questions {
    final raw = input['questions'];
    if (raw is! List) return const <InteractionQuestion>[];
    return raw
        .whereType<Map>()
        .map((item) => InteractionQuestion.fromJson(
            Map<String, dynamic>.from(item)))
        .where((question) => question.question.isNotEmpty)
        .toList();
  }

  String get plan => (input['plan'] ?? detail).toString();
}

class InteractionQuestion {
  const InteractionQuestion({
    required this.question,
    required this.header,
    required this.options,
    required this.multiSelect,
  });

  factory InteractionQuestion.fromJson(Map<String, dynamic> json) =>
      InteractionQuestion(
        question: (json['question'] ?? '').toString(),
        header: (json['header'] ?? '').toString(),
        multiSelect: json['multiSelect'] == true,
        options: (json['options'] is List ? json['options'] as List : const [])
            .whereType<Map>()
            .map((option) => InteractionOption(
                  label: (option['label'] ?? '').toString(),
                  description: (option['description'] ?? '').toString(),
                ))
            .where((option) => option.label.isNotEmpty)
            .toList(),
      );

  final String question;
  final String header;
  final List<InteractionOption> options;
  final bool multiSelect;
}

class InteractionOption {
  const InteractionOption({required this.label, this.description = ''});
  final String label;
  final String description;
}

class RunCard {
  const RunCard({
    required this.jobId,
    required this.sessionId,
    required this.sessionTitle,
    required this.workspaceName,
    required this.engine,
    required this.state,
    required this.request,
    required this.headline,
    required this.output,
    required this.pending,
    required this.steps,
    required this.failedSteps,
    required this.filesChanged,
    required this.elapsedSeconds,
    required this.receivedAt,
    this.error,
    this.createdAt,
    this.updatedAt,
    this.completedAt,
  });

  factory RunCard.fromJson(Map<String, dynamic> json, {DateTime? receivedAt}) =>
      RunCard(
        jobId: (json['job_id'] ?? '').toString(),
        sessionId: (json['session_id'] ?? '').toString(),
        sessionTitle: (json['session_title'] ?? '').toString(),
        workspaceName: (json['workspace_name'] ?? '').toString(),
        engine: (json['engine'] ?? 'agent').toString(),
        state: _parseState(json['state']),
        request: (json['request'] ?? '').toString(),
        headline: (json['headline'] ?? '').toString(),
        output: (json['output'] ?? '').toString(),
        error: json['error'] as String?,
        pending: (json['pending'] is List ? json['pending'] as List : const [])
            .whereType<Map>()
            .map((item) =>
                PendingInteraction.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
        steps: (json['steps'] as num?)?.toInt() ?? 0,
        failedSteps: (json['failed_steps'] as num?)?.toInt() ?? 0,
        filesChanged: (json['files_changed'] as num?)?.toInt() ?? 0,
        elapsedSeconds: (json['elapsed_seconds'] as num?)?.toInt() ?? 0,
        receivedAt: receivedAt ?? DateTime.now(),
        createdAt: _date(json['created_at']),
        updatedAt: _date(json['updated_at']),
        completedAt: _date(json['completed_at']),
      );

  final String jobId;
  final String sessionId;
  final String sessionTitle;
  final String workspaceName;

  /// `claude`, `codex` or `agent` when unknown.
  final String engine;
  final RunState state;

  /// First line of what the user asked.
  final String request;

  /// Plain-language "what is happening": current step, result or error.
  final String headline;

  /// Tail of the live response while the run is active.
  final String output;
  final String? error;
  final List<PendingInteraction> pending;
  final int steps;
  final int failedSteps;
  final int filesChanged;
  final int elapsedSeconds;
  final DateTime receivedAt;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? completedAt;

  bool get isActive =>
      state == RunState.needsYou ||
      state == RunState.working ||
      state == RunState.queued;

  String get engineLabel => switch (engine) {
        'claude' => 'Claude',
        'codex' => 'Codex',
        _ => 'Agente',
      };

  /// Elapsed time that keeps counting between server updates.
  Duration elapsedAt(DateTime now) {
    final base = Duration(seconds: elapsedSeconds);
    if (!isActive) return base;
    final drift = now.difference(receivedAt);
    return drift.isNegative ? base : base + drift;
  }
}

class RunsOverview {
  const RunsOverview({required this.runs});

  factory RunsOverview.fromJson(Map<String, dynamic> json) {
    final now = DateTime.now();
    return RunsOverview(
      runs: (json['runs'] is List ? json['runs'] as List : const [])
          .whereType<Map>()
          .map((item) => RunCard.fromJson(Map<String, dynamic>.from(item),
              receivedAt: now))
          .toList(),
    );
  }

  static const empty = RunsOverview(runs: <RunCard>[]);

  final List<RunCard> runs;

  List<RunCard> where(RunState state) =>
      runs.where((run) => run.state == state).toList();

  int count(RunState state) => runs.where((run) => run.state == state).length;

  int get pendingCount =>
      runs.fold(0, (sum, run) => sum + run.pending.length);
}

/// What the user decided for a [PendingInteraction].
class InteractionDecision {
  const InteractionDecision.allow({this.remember = false})
      : action = remember ? 'allow_always' : 'allow',
        message = null,
        answers = null,
        mode = null;

  const InteractionDecision.deny({this.message})
      : action = 'deny',
        remember = false,
        answers = null,
        mode = null;

  const InteractionDecision.answer(Map<String, String> this.answers)
      : action = 'allow',
        remember = false,
        message = null,
        mode = null;

  const InteractionDecision.approvePlan(String this.mode)
      : action = 'allow',
        remember = false,
        message = null,
        answers = null;

  final String action;
  final bool remember;
  final String? message;
  final Map<String, String>? answers;
  final String? mode;

  Map<String, Object?> toJson() => <String, Object?>{
        'action': action,
        if (message != null && message!.trim().isNotEmpty) 'message': message,
        if (answers != null) 'answers': answers,
        if (mode != null) 'mode': mode,
      };
}
