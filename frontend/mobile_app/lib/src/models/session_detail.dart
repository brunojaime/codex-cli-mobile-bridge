import 'chat_message.dart';

class SessionDetail {
  const SessionDetail({
    required this.id,
    required this.title,
    required this.workspacePath,
    required this.workspaceName,
    required this.createdAt,
    required this.updatedAt,
    required this.messages,
    this.providerSessionId,
    this.reviewerProviderSessionId,
    this.autoModeEnabled = false,
    this.autoMaxTurns = 0,
    this.autoReviewerPrompt,
    this.autoTurnIndex = 0,
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
  final List<ChatMessage> messages;

  SessionDetail copyWith({
    String? title,
    String? workspacePath,
    String? workspaceName,
    String? providerSessionId,
    String? reviewerProviderSessionId,
    bool? autoModeEnabled,
    int? autoMaxTurns,
    String? autoReviewerPrompt,
    int? autoTurnIndex,
    DateTime? createdAt,
    DateTime? updatedAt,
    List<ChatMessage>? messages,
  }) {
    return SessionDetail(
      id: id,
      title: title ?? this.title,
      workspacePath: workspacePath ?? this.workspacePath,
      workspaceName: workspaceName ?? this.workspaceName,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      messages: messages ?? this.messages,
      providerSessionId: providerSessionId ?? this.providerSessionId,
      reviewerProviderSessionId:
          reviewerProviderSessionId ?? this.reviewerProviderSessionId,
      autoModeEnabled: autoModeEnabled ?? this.autoModeEnabled,
      autoMaxTurns: autoMaxTurns ?? this.autoMaxTurns,
      autoReviewerPrompt: autoReviewerPrompt ?? this.autoReviewerPrompt,
      autoTurnIndex: autoTurnIndex ?? this.autoTurnIndex,
    );
  }

  factory SessionDetail.fromJson(Map<String, dynamic> json) {
    final rawMessages = json['messages'] as List<dynamic>? ?? <dynamic>[];
    return SessionDetail(
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
      messages: rawMessages
          .map((item) => ChatMessage.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}
