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
