class ChatSessionSummary {
  const ChatSessionSummary({
    required this.id,
    required this.title,
    required this.workspacePath,
    required this.workspaceName,
    required this.createdAt,
    required this.updatedAt,
    this.providerSessionId,
    this.reviewerProviderSessionId,
    this.autoModeEnabled = false,
    this.autoMaxTurns = 0,
    this.autoReviewerPrompt,
    this.autoTurnIndex = 0,
    this.lastMessagePreview,
    this.hasPendingMessages = false,
  });

  final String id;
  final String title;
  final String workspacePath;
  final String workspaceName;
  final String? providerSessionId;
  final String? reviewerProviderSessionId;
  final bool autoModeEnabled;
  final int autoMaxTurns;
  final String? autoReviewerPrompt;
  final int autoTurnIndex;
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
      reviewerProviderSessionId:
          json['reviewer_provider_session_id'] as String?,
      autoModeEnabled: json['auto_mode_enabled'] as bool? ?? false,
      autoMaxTurns: json['auto_max_turns'] as int? ?? 0,
      autoReviewerPrompt: json['auto_reviewer_prompt'] as String?,
      autoTurnIndex: json['auto_turn_index'] as int? ?? 0,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      lastMessagePreview: json['last_message_preview'] as String?,
      hasPendingMessages: json['has_pending_messages'] as bool? ?? false,
    );
  }
}
