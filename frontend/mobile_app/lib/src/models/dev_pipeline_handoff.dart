class DevPipelineHandoffRequest {
  const DevPipelineHandoffRequest({
    required this.title,
    required this.problem,
    required this.context,
    required this.acceptanceCriteria,
    this.selectedContext = const <String, dynamic>{},
    this.evidence = const <Map<String, dynamic>>[],
    this.proposedSpec,
    this.proposedPlan,
    this.proposedTasks = const <String>[],
    this.regressionTests = const <String>[],
    this.risks = const <String>[],
    this.createdFromSessionId,
    this.createdByAction = 'mobile_dev_handoff',
    this.draftToken,
    this.draftId,
    this.draftStatus,
    this.draftError,
    this.draftJobId,
    this.phase,
    this.latestActivity,
  });

  final String title;
  final String problem;
  final String context;
  final String acceptanceCriteria;
  final Map<String, dynamic> selectedContext;
  final List<Map<String, dynamic>> evidence;
  final String? proposedSpec;
  final String? proposedPlan;
  final List<String> proposedTasks;
  final List<String> regressionTests;
  final List<String> risks;
  final String? createdFromSessionId;
  final String createdByAction;
  final String? draftToken;
  final String? draftId;
  final String? draftStatus;
  final String? draftError;
  final String? draftJobId;
  final String? phase;
  final String? latestActivity;

  bool get isDraftReady => draftStatus == null || draftStatus == 'ready';
  bool get isDraftFailed => draftStatus == 'failed';

  factory DevPipelineHandoffRequest.fromJson(Map<String, dynamic> json) {
    return DevPipelineHandoffRequest(
      title: json['title'] as String? ?? '',
      problem: json['problem'] as String? ?? '',
      context: json['context'] as String? ?? '',
      acceptanceCriteria: json['acceptance_criteria'] as String? ?? '',
      selectedContext:
          (json['selected_context'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      evidence: ((json['evidence'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(),
      proposedSpec: json['proposed_spec'] as String?,
      proposedPlan: json['proposed_plan'] as String?,
      proposedTasks: ((json['proposed_tasks'] as List?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(),
      regressionTests:
          ((json['regression_tests'] as List?) ?? const <dynamic>[])
              .map((item) => item.toString())
              .toList(),
      risks: ((json['risks'] as List?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(),
      createdFromSessionId: json['created_from_session_id'] as String?,
      createdByAction:
          json['created_by_action'] as String? ?? 'mobile_dev_handoff',
      draftToken: json['draft_token'] as String?,
      draftId: json['draft_id'] as String?,
      draftStatus: json['draft_status'] as String?,
      draftError: json['draft_error'] as String?,
      draftJobId: json['draft_job_id'] as String?,
      phase: json['phase'] as String?,
      latestActivity: json['latest_activity'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'kind': 'bridge.devHandoff',
      'version': 1,
      'source_environment': 'prod',
      'target_environment': 'dev',
      'operation': 'enqueue_only',
      'title': title,
      'problem': problem,
      'context': context,
      'selected_context': selectedContext,
      'evidence': evidence,
      'proposed_spec': proposedSpec,
      'proposed_plan': proposedPlan,
      'proposed_tasks': proposedTasks,
      'acceptance_criteria': acceptanceCriteria,
      'regression_tests': regressionTests,
      'risks': risks,
      'created_from_session_id': createdFromSessionId,
      'created_by_action': createdByAction,
      'draft_token': draftToken,
    }..removeWhere((_, value) => value == null);
  }
}

class DevPipelineHandoff {
  const DevPipelineHandoff({
    required this.id,
    required this.status,
    required this.title,
    required this.problem,
    required this.idempotencyKey,
  });

  final String id;
  final String status;
  final String title;
  final String problem;
  final String idempotencyKey;

  factory DevPipelineHandoff.fromJson(Map<String, dynamic> json) {
    return DevPipelineHandoff(
      id: json['id'] as String? ?? '',
      status: json['status'] as String? ?? '',
      title: json['title'] as String? ?? '',
      problem: json['problem'] as String? ?? '',
      idempotencyKey: json['idempotency_key'] as String? ?? '',
    );
  }
}
