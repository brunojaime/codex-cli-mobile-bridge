class JobStatusResponse {
  const JobStatusResponse({
    required this.jobId,
    required this.sessionId,
    required this.status,
    this.response,
    this.error,
    this.providerSessionId,
  });

  final String jobId;
  final String sessionId;
  final String status;
  final String? response;
  final String? error;
  final String? providerSessionId;

  bool get isTerminal => status == 'completed' || status == 'failed';

  factory JobStatusResponse.fromJson(Map<String, dynamic> json) {
    return JobStatusResponse(
      jobId: (json['job_id'] ?? '') as String,
      sessionId: json['session_id'] as String,
      status: json['status'] as String,
      response: json['response'] as String?,
      error: json['error'] as String?,
      providerSessionId: json['provider_session_id'] as String?,
    );
  }
}
