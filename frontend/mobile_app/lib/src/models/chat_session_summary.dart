import 'agent_configuration.dart';
import 'conversation_product.dart';
import 'reviewer_lifecycle_state.dart';

class ChatSessionSummary {
  const ChatSessionSummary({
    required this.id,
    required this.title,
    this.archivedAt,
    required this.workspacePath,
    required this.workspaceName,
    this.agentProfileId = 'default',
    this.agentProfileName = 'Generator',
    this.agentProfileColor = '#55D6BE',
    required this.createdAt,
    required this.updatedAt,
    this.agentConfiguration = kDefaultAgentConfiguration,
    this.providerSessionId,
    this.reviewerProviderSessionId,
    this.activeAgentRunId,
    this.activeAgentTurnIndex = 0,
    this.autoModeEnabled = false,
    this.autoMaxTurns = 0,
    this.autoReviewerPrompt,
    this.autoTurnIndex = 0,
    this.reviewerState = ReviewerLifecycleState.off,
    this.conversationProduct,
    this.lastMessagePreview,
    this.hasPendingMessages = false,
  });

  final String id;
  final String title;
  final DateTime? archivedAt;
  final String workspacePath;
  final String workspaceName;
  final String agentProfileId;
  final String agentProfileName;
  final String agentProfileColor;
  final String? providerSessionId;
  final String? reviewerProviderSessionId;
  final String? activeAgentRunId;
  final int activeAgentTurnIndex;
  final AgentConfiguration agentConfiguration;
  final bool autoModeEnabled;
  final int autoMaxTurns;
  final String? autoReviewerPrompt;
  final int autoTurnIndex;
  final ReviewerLifecycleState reviewerState;
  final ConversationProduct? conversationProduct;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? lastMessagePreview;
  final bool hasPendingMessages;
  bool get isArchived => archivedAt != null;

  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    final rawAgentConfiguration = json['agent_configuration'];
    return ChatSessionSummary(
      id: json['id'] as String,
      title: json['title'] as String,
      archivedAt: json['archived_at'] != null
          ? DateTime.parse(json['archived_at'] as String)
          : null,
      workspacePath: json['workspace_path'] as String,
      workspaceName: json['workspace_name'] as String,
      agentProfileId: json['agent_profile_id'] as String? ?? 'default',
      agentProfileName: json['agent_profile_name'] as String? ?? 'Generator',
      agentProfileColor: json['agent_profile_color'] as String? ?? '#55D6BE',
      providerSessionId: json['provider_session_id'] as String?,
      reviewerProviderSessionId:
          json['reviewer_provider_session_id'] as String?,
      activeAgentRunId: json['active_agent_run_id'] as String?,
      activeAgentTurnIndex: json['active_agent_turn_index'] as int? ?? 0,
      agentConfiguration: rawAgentConfiguration is Map<String, dynamic>
          ? AgentConfiguration.fromJson(rawAgentConfiguration)
          : kDefaultAgentConfiguration,
      autoModeEnabled: json['auto_mode_enabled'] as bool? ?? false,
      autoMaxTurns: json['auto_max_turns'] as int? ?? 0,
      autoReviewerPrompt: json['auto_reviewer_prompt'] as String?,
      autoTurnIndex: json['auto_turn_index'] as int? ?? 0,
      reviewerState: reviewerLifecycleStateFromJson(
        json['reviewer_state'] as String?,
      ),
      conversationProduct: json['conversation_product'] is Map<String, dynamic>
          ? ConversationProduct.fromJson(
              json['conversation_product'] as Map<String, dynamic>,
            )
          : null,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      lastMessagePreview: json['last_message_preview'] as String?,
      hasPendingMessages: json['has_pending_messages'] as bool? ?? false,
    );
  }
}
