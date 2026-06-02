import 'agent_configuration.dart';
import 'chat_message.dart';
import 'chat_turn_summary.dart';
import 'conversation_product.dart';
import 'current_run_execution.dart';
import 'reviewer_lifecycle_state.dart';

class SessionDetail {
  const SessionDetail({
    required this.id,
    required this.title,
    this.archivedAt,
    required this.workspacePath,
    required this.workspaceName,
    this.turnSummariesEnabled = false,
    this.agentProfileId = 'default',
    this.agentProfileName = 'Generator',
    this.agentProfileColor = '#55D6BE',
    required this.createdAt,
    required this.updatedAt,
    required this.messages,
    this.turnSummaries = const <ChatTurnSummary>[],
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
    this.currentRun,
    this.recentRuns = const <CurrentRunExecution>[],
  });

  final String id;
  final String title;
  final DateTime? archivedAt;
  final String workspacePath;
  final String workspaceName;
  final bool turnSummariesEnabled;
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
  final CurrentRunExecution? currentRun;
  final List<CurrentRunExecution> recentRuns;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<ChatMessage> messages;
  final List<ChatTurnSummary> turnSummaries;
  bool get isArchived => archivedAt != null;

  SessionDetail copyWith({
    String? title,
    DateTime? archivedAt,
    String? workspacePath,
    String? workspaceName,
    bool? turnSummariesEnabled,
    String? agentProfileId,
    String? agentProfileName,
    String? agentProfileColor,
    String? providerSessionId,
    String? reviewerProviderSessionId,
    String? activeAgentRunId,
    int? activeAgentTurnIndex,
    AgentConfiguration? agentConfiguration,
    bool? autoModeEnabled,
    int? autoMaxTurns,
    String? autoReviewerPrompt,
    int? autoTurnIndex,
    ReviewerLifecycleState? reviewerState,
    ConversationProduct? conversationProduct,
    CurrentRunExecution? currentRun,
    List<CurrentRunExecution>? recentRuns,
    DateTime? createdAt,
    DateTime? updatedAt,
    List<ChatMessage>? messages,
    List<ChatTurnSummary>? turnSummaries,
  }) {
    return SessionDetail(
      id: id,
      title: title ?? this.title,
      archivedAt: archivedAt ?? this.archivedAt,
      workspacePath: workspacePath ?? this.workspacePath,
      workspaceName: workspaceName ?? this.workspaceName,
      turnSummariesEnabled: turnSummariesEnabled ?? this.turnSummariesEnabled,
      agentProfileId: agentProfileId ?? this.agentProfileId,
      agentProfileName: agentProfileName ?? this.agentProfileName,
      agentProfileColor: agentProfileColor ?? this.agentProfileColor,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      messages: messages ?? this.messages,
      turnSummaries: turnSummaries ?? this.turnSummaries,
      providerSessionId: providerSessionId ?? this.providerSessionId,
      reviewerProviderSessionId:
          reviewerProviderSessionId ?? this.reviewerProviderSessionId,
      activeAgentRunId: activeAgentRunId ?? this.activeAgentRunId,
      activeAgentTurnIndex: activeAgentTurnIndex ?? this.activeAgentTurnIndex,
      agentConfiguration: agentConfiguration ?? this.agentConfiguration,
      autoModeEnabled: autoModeEnabled ?? this.autoModeEnabled,
      autoMaxTurns: autoMaxTurns ?? this.autoMaxTurns,
      autoReviewerPrompt: autoReviewerPrompt ?? this.autoReviewerPrompt,
      autoTurnIndex: autoTurnIndex ?? this.autoTurnIndex,
      reviewerState: reviewerState ?? this.reviewerState,
      conversationProduct: conversationProduct ?? this.conversationProduct,
      currentRun: currentRun ?? this.currentRun,
      recentRuns: recentRuns ?? this.recentRuns,
    );
  }

  factory SessionDetail.fromJson(Map<String, dynamic> json) {
    final rawMessages = json['messages'] as List<dynamic>? ?? <dynamic>[];
    final rawTurnSummaries =
        json['turn_summaries'] as List<dynamic>? ?? <dynamic>[];
    final rawRecentRuns = json['recent_runs'] as List<dynamic>? ?? <dynamic>[];
    final rawAgentConfiguration = json['agent_configuration'];
    return SessionDetail(
      id: json['id'] as String,
      title: json['title'] as String,
      archivedAt: json['archived_at'] != null
          ? DateTime.parse(json['archived_at'] as String)
          : null,
      workspacePath: json['workspace_path'] as String,
      workspaceName: json['workspace_name'] as String,
      turnSummariesEnabled: json['turn_summaries_enabled'] as bool? ?? false,
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
      currentRun: json['current_run'] is Map<String, dynamic>
          ? CurrentRunExecution.fromJson(
              json['current_run'] as Map<String, dynamic>,
            )
          : null,
      recentRuns: rawRecentRuns
          .whereType<Map<dynamic, dynamic>>()
          .map((item) => CurrentRunExecution.fromJson(
                <String, dynamic>{
                  for (final entry in item.entries)
                    if (entry.key is String) entry.key as String: entry.value,
                },
              ))
          .toList(growable: false),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      messages: rawMessages
          .map((item) => ChatMessage.fromJson(item as Map<String, dynamic>))
          .toList(),
      turnSummaries: rawTurnSummaries
          .whereType<Map<String, dynamic>>()
          .map(ChatTurnSummary.fromJson)
          .toList(growable: false),
    );
  }
}
