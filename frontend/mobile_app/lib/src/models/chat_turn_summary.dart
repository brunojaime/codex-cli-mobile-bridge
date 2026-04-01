import 'agent_configuration.dart';
import 'chat_message.dart';

class ChatTurnSummarySourceMessage {
  const ChatTurnSummarySourceMessage({
    required this.messageId,
    required this.isUser,
    required this.authorType,
    required this.agentId,
    required this.agentType,
    this.agentLabel,
    this.content,
    required this.status,
    required this.createdAt,
  });

  final String messageId;
  final bool isUser;
  final ChatMessageAuthorType authorType;
  final AgentId agentId;
  final AgentType agentType;
  final String? agentLabel;
  final String? content;
  final ChatMessageStatus status;
  final DateTime createdAt;

  factory ChatTurnSummarySourceMessage.fromJson(Map<String, dynamic> json) {
    return ChatTurnSummarySourceMessage(
      messageId: json['message_id'] as String,
      isUser: (json['role'] as String?) == 'user',
      authorType: _turnSummaryAuthorTypeFromJson(
        json['author_type'] as String?,
        role: json['role'] as String? ?? 'assistant',
      ),
      agentId: agentIdFromJson(json['agent_id'] as String? ?? 'generator'),
      agentType: agentTypeFromJson(json['agent_type'] as String? ?? 'generator'),
      agentLabel: json['agent_label'] as String?,
      content: json['content'] as String?,
      status:
          _turnSummaryStatusFromJson(json['status'] as String? ?? 'completed'),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class ChatTurnSummary {
  const ChatTurnSummary({
    required this.id,
    required this.content,
    this.sourceMessageIds = const <String>[],
    this.sourceMessages = const <ChatTurnSummarySourceMessage>[],
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String content;
  final List<String> sourceMessageIds;
  final List<ChatTurnSummarySourceMessage> sourceMessages;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory ChatTurnSummary.fromJson(Map<String, dynamic> json) {
    final rawSourceMessageIds =
        json['source_message_ids'] as List<dynamic>? ?? <dynamic>[];
    final rawSourceMessages =
        json['source_messages'] as List<dynamic>? ?? <dynamic>[];
    return ChatTurnSummary(
      id: json['id'] as String,
      content: json['content'] as String,
      sourceMessageIds: rawSourceMessageIds
          .whereType<String>()
          .toList(growable: false),
      sourceMessages: rawSourceMessages
          .whereType<Map<String, dynamic>>()
          .map(ChatTurnSummarySourceMessage.fromJson)
          .toList(growable: false),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

ChatMessageAuthorType _turnSummaryAuthorTypeFromJson(
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

ChatMessageStatus _turnSummaryStatusFromJson(String status) {
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
