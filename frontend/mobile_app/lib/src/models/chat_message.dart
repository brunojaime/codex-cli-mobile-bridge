import 'agent_configuration.dart';

enum ChatMessageStatus {
  sending,
  reserved,
  submissionPending,
  submissionUnknown,
  pending,
  completed,
  failed,
  cancelled
}

enum ChatMessageAuthorType { human, assistant, reviewerCodex }

enum MessageRecoveryAction { retry, cancel }

enum ChatMessageReasonCode {
  supersededByNewerRun,
  orphanedFollowUpCancelled,
  submissionOutcomeUnknown,
  manualRetryRequested,
  manualCancelRequested,
  followUpTerminalCompletedRun
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.text,
    required this.isUser,
    required this.authorType,
    this.agentId = AgentId.generator,
    this.agentType = AgentType.generator,
    this.visibility = AgentVisibilityMode.visible,
    this.triggerSource,
    required this.status,
    this.reasonCode,
    this.recoveryAction,
    this.recoveredFromMessageId,
    this.supersededByMessageId,
    required this.createdAt,
    required this.updatedAt,
    this.agentLabel,
    this.runId,
    this.jobId,
    this.jobStatus,
    this.jobPhase,
    this.jobLatestActivity,
    this.jobElapsedSeconds,
    this.providerSessionId,
    this.completedAt,
  });

  final String id;
  final String text;
  final bool isUser;
  final ChatMessageAuthorType authorType;
  final AgentId agentId;
  final AgentType agentType;
  final String? agentLabel;
  final AgentVisibilityMode visibility;
  final AgentTriggerSource? triggerSource;
  final String? runId;
  final ChatMessageStatus status;
  final ChatMessageReasonCode? reasonCode;
  final MessageRecoveryAction? recoveryAction;
  final String? recoveredFromMessageId;
  final String? supersededByMessageId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? jobId;
  final String? jobStatus;
  final String? jobPhase;
  final String? jobLatestActivity;
  final int? jobElapsedSeconds;
  final String? providerSessionId;
  final DateTime? completedAt;

  bool get isPendingLike =>
      status == ChatMessageStatus.reserved ||
      status == ChatMessageStatus.submissionPending ||
      status == ChatMessageStatus.pending ||
      status == ChatMessageStatus.sending;

  bool get isReviewerCodex => authorType == ChatMessageAuthorType.reviewerCodex;

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final role = json['role'] as String;
    final status = json['status'] as String? ?? 'completed';
    final authorType = _authorTypeFromJson(
      json['author_type'] as String?,
      role: role,
    );
    return ChatMessage(
      id: json['id'] as String,
      text: json['content'] as String? ?? '',
      isUser: role == 'user',
      authorType: authorType,
      agentId: agentIdFromJson(json['agent_id'] as String? ?? 'generator'),
      agentType:
          agentTypeFromJson(json['agent_type'] as String? ?? 'generator'),
      agentLabel: json['agent_label'] as String?,
      visibility:
          agentVisibilityFromJson(json['visibility'] as String? ?? 'visible'),
      triggerSource: json['trigger_source'] != null
          ? agentTriggerSourceFromJson(json['trigger_source'] as String)
          : null,
      runId: json['run_id'] as String?,
      status: _statusFromJson(status),
      reasonCode: json['reason_code'] != null
          ? _reasonCodeFromJson(json['reason_code'] as String)
          : null,
      recoveryAction: json['recovery_action'] != null
          ? _recoveryActionFromJson(json['recovery_action'] as String)
          : null,
      recoveredFromMessageId: json['recovered_from_message_id'] as String?,
      supersededByMessageId: json['superseded_by_message_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      jobId: json['job_id'] as String?,
      jobStatus: json['job_status'] as String?,
      jobPhase: json['job_phase'] as String?,
      jobLatestActivity: json['job_latest_activity'] as String?,
      jobElapsedSeconds: json['job_elapsed_seconds'] as int?,
      providerSessionId: json['provider_session_id'] as String?,
      completedAt: json['completed_at'] != null
          ? DateTime.parse(json['completed_at'] as String)
          : null,
    );
  }

  ChatMessage copyWith({
    String? text,
    bool? isUser,
    ChatMessageAuthorType? authorType,
    AgentId? agentId,
    AgentType? agentType,
    String? agentLabel,
    AgentVisibilityMode? visibility,
    AgentTriggerSource? triggerSource,
    String? runId,
    ChatMessageStatus? status,
    ChatMessageReasonCode? reasonCode,
    MessageRecoveryAction? recoveryAction,
    String? recoveredFromMessageId,
    String? supersededByMessageId,
    String? jobId,
    String? jobStatus,
    String? jobPhase,
    String? jobLatestActivity,
    int? jobElapsedSeconds,
    String? providerSessionId,
    DateTime? createdAt,
    DateTime? updatedAt,
    DateTime? completedAt,
  }) {
    return ChatMessage(
      id: id,
      text: text ?? this.text,
      isUser: isUser ?? this.isUser,
      authorType: authorType ?? this.authorType,
      agentId: agentId ?? this.agentId,
      agentType: agentType ?? this.agentType,
      agentLabel: agentLabel ?? this.agentLabel,
      visibility: visibility ?? this.visibility,
      triggerSource: triggerSource ?? this.triggerSource,
      runId: runId ?? this.runId,
      status: status ?? this.status,
      reasonCode: reasonCode ?? this.reasonCode,
      recoveryAction: recoveryAction ?? this.recoveryAction,
      recoveredFromMessageId: recoveredFromMessageId ?? this.recoveredFromMessageId,
      supersededByMessageId: supersededByMessageId ?? this.supersededByMessageId,
      jobId: jobId ?? this.jobId,
      jobStatus: jobStatus ?? this.jobStatus,
      jobPhase: jobPhase ?? this.jobPhase,
      jobLatestActivity: jobLatestActivity ?? this.jobLatestActivity,
      jobElapsedSeconds: jobElapsedSeconds ?? this.jobElapsedSeconds,
      providerSessionId: providerSessionId ?? this.providerSessionId,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      completedAt: completedAt ?? this.completedAt,
    );
  }
}

ChatMessageReasonCode? _reasonCodeFromJson(String value) {
  switch (value) {
    case 'superseded_by_newer_run':
      return ChatMessageReasonCode.supersededByNewerRun;
    case 'orphaned_follow_up_cancelled':
      return ChatMessageReasonCode.orphanedFollowUpCancelled;
    case 'submission_outcome_unknown':
      return ChatMessageReasonCode.submissionOutcomeUnknown;
    case 'manual_retry_requested':
      return ChatMessageReasonCode.manualRetryRequested;
    case 'manual_cancel_requested':
      return ChatMessageReasonCode.manualCancelRequested;
    case 'follow_up_terminal_completed_run':
      return ChatMessageReasonCode.followUpTerminalCompletedRun;
    default:
      return null;
  }
}

MessageRecoveryAction _recoveryActionFromJson(String value) {
  switch (value) {
    case 'cancel':
      return MessageRecoveryAction.cancel;
    default:
      return MessageRecoveryAction.retry;
  }
}

ChatMessageAuthorType _authorTypeFromJson(
  String? authorType, {
  required String role,
}) {
  switch (authorType) {
    case 'assistant':
      return ChatMessageAuthorType.assistant;
    case 'reviewer_codex':
      return ChatMessageAuthorType.reviewerCodex;
    case 'human':
      return ChatMessageAuthorType.human;
    default:
      return role == 'assistant'
          ? ChatMessageAuthorType.assistant
          : ChatMessageAuthorType.human;
  }
}

ChatMessageStatus _statusFromJson(String status) {
  switch (status) {
    case 'reserved':
      return ChatMessageStatus.reserved;
    case 'submission_pending':
      return ChatMessageStatus.submissionPending;
    case 'submission_unknown':
      return ChatMessageStatus.submissionUnknown;
    case 'pending':
      return ChatMessageStatus.pending;
    case 'failed':
      return ChatMessageStatus.failed;
    case 'cancelled':
      return ChatMessageStatus.cancelled;
    case 'sending':
      return ChatMessageStatus.sending;
    default:
      return ChatMessageStatus.completed;
  }
}
