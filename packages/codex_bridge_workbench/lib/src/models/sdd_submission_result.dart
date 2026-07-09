class SddFeedbackSubmissionResult {
  const SddFeedbackSubmissionResult({required this.id, this.status = 'queued'});

  final String id;
  final String status;
}

class SddCodexActionSubmissionResult {
  const SddCodexActionSubmissionResult({
    required this.jobId,
    required this.sessionId,
    this.status = 'submitted',
  });

  final String jobId;
  final String sessionId;
  final String status;
}
