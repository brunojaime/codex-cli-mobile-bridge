class JobStatusResponse {
  const JobStatusResponse({
    required this.jobId,
    required this.sessionId,
    required this.status,
    required this.elapsedSeconds,
    this.response,
    this.error,
    this.providerSessionId,
    this.phase,
    this.latestActivity,
    this.updatedAt,
    this.completedAt,
  });

  final String jobId;
  final String sessionId;
  final String status;
  final int elapsedSeconds;
  final String? response;
  final String? error;
  final String? providerSessionId;
  final String? phase;
  final String? latestActivity;
  final DateTime? updatedAt;
  final DateTime? completedAt;

  bool get isTerminal => status == 'completed' || status == 'failed';

  factory JobStatusResponse.fromJson(Map<String, dynamic> json) {
    return JobStatusResponse(
      jobId: (json['job_id'] ?? '') as String,
      sessionId: json['session_id'] as String,
      status: json['status'] as String,
      elapsedSeconds: json['elapsed_seconds'] as int? ?? 0,
      response: json['response'] as String?,
      error: json['error'] as String?,
      providerSessionId: json['provider_session_id'] as String?,
      phase: json['phase'] as String?,
      latestActivity: json['latest_activity'] as String?,
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : null,
      completedAt: json['completed_at'] != null
          ? DateTime.parse(json['completed_at'] as String)
          : null,
    );
  }
}
