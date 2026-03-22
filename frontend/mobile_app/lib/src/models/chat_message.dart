enum ChatMessageStatus { sending, pending, completed, failed }

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.text,
    required this.isUser,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
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
  final ChatMessageStatus status;
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
      status == ChatMessageStatus.pending || status == ChatMessageStatus.sending;

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final role = json['role'] as String;
    final status = json['status'] as String? ?? 'completed';
    return ChatMessage(
      id: json['id'] as String,
      text: json['content'] as String? ?? '',
      isUser: role == 'user',
      status: _statusFromJson(status),
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
    ChatMessageStatus? status,
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
      status: status ?? this.status,
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

ChatMessageStatus _statusFromJson(String status) {
  switch (status) {
    case 'pending':
      return ChatMessageStatus.pending;
    case 'failed':
      return ChatMessageStatus.failed;
    case 'sending':
      return ChatMessageStatus.sending;
    default:
      return ChatMessageStatus.completed;
  }
}
