enum ChatMessageStatus { sending, pending, completed, failed }

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.text,
    required this.isUser,
    required this.status,
    this.jobId,
  });

  final String id;
  final String text;
  final bool isUser;
  final ChatMessageStatus status;
  final String? jobId;

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final role = json['role'] as String;
    final status = json['status'] as String? ?? 'completed';
    return ChatMessage(
      id: json['id'] as String,
      text: json['content'] as String? ?? '',
      isUser: role == 'user',
      status: _statusFromJson(status),
      jobId: json['job_id'] as String?,
    );
  }

  ChatMessage copyWith({
    String? text,
    bool? isUser,
    ChatMessageStatus? status,
    String? jobId,
  }) {
    return ChatMessage(
      id: id,
      text: text ?? this.text,
      isUser: isUser ?? this.isUser,
      status: status ?? this.status,
      jobId: jobId ?? this.jobId,
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
