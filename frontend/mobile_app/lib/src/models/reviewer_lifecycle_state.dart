enum ReviewerLifecycleState {
  off,
  disabled,
  idle,
  waitingOnGenerator,
  queued,
  running,
  completed,
  failed,
  skipped,
}

ReviewerLifecycleState reviewerLifecycleStateFromJson(String? value) {
  switch (value) {
    case 'disabled':
      return ReviewerLifecycleState.disabled;
    case 'idle':
      return ReviewerLifecycleState.idle;
    case 'waiting_on_generator':
      return ReviewerLifecycleState.waitingOnGenerator;
    case 'queued':
      return ReviewerLifecycleState.queued;
    case 'running':
      return ReviewerLifecycleState.running;
    case 'completed':
      return ReviewerLifecycleState.completed;
    case 'failed':
      return ReviewerLifecycleState.failed;
    case 'skipped':
      return ReviewerLifecycleState.skipped;
    default:
      return ReviewerLifecycleState.off;
  }
}
