class ChatSessionSummary {
  const ChatSessionSummary({
    required this.id,
    required this.title,
    required this.workspacePath,
    required this.workspaceName,
    required this.createdAt,
    required this.updatedAt,
    this.providerSessionId,
    this.lastMessagePreview,
    this.hasPendingMessages = false,
  });

  final String id;
  final String title;
  final String workspacePath;
  final String workspaceName;
  final String? providerSessionId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? lastMessagePreview;
  final bool hasPendingMessages;

  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    return ChatSessionSummary(
      id: json['id'] as String,
      title: json['title'] as String,
      workspacePath: json['workspace_path'] as String,
      workspaceName: json['workspace_name'] as String,
      providerSessionId: json['provider_session_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      lastMessagePreview: json['last_message_preview'] as String?,
      hasPendingMessages: json['has_pending_messages'] as bool? ?? false,
    );
  }
}
