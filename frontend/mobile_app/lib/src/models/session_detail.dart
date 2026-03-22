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
  });

  final String id;
  final String title;
  final String workspacePath;
  final String workspaceName;
  final String? providerSessionId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<ChatMessage> messages;

  factory SessionDetail.fromJson(Map<String, dynamic> json) {
    final rawMessages = json['messages'] as List<dynamic>? ?? <dynamic>[];
    return SessionDetail(
      id: json['id'] as String,
      title: json['title'] as String,
      workspacePath: json['workspace_path'] as String,
      workspaceName: json['workspace_name'] as String,
      providerSessionId: json['provider_session_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      messages: rawMessages
          .map((item) => ChatMessage.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}
