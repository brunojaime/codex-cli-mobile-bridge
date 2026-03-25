import '../models/agent_configuration.dart';
import '../models/chat_message.dart';

List<ChatMessage> filterVisibleMessages(
  List<ChatMessage> messages, {
  required AgentDisplayMode displayMode,
}) {
  return messages.where((message) {
    if (message.visibility == AgentVisibilityMode.hidden) {
      return false;
    }
    // Preserve direct human prompts even when legacy rows or follow-up state
    // carried a non-human agent id/type onto the user-side message.
    if (message.isUser && message.authorType == ChatMessageAuthorType.human) {
      return true;
    }
    switch (displayMode) {
      case AgentDisplayMode.showAll:
        return true;
      case AgentDisplayMode.collapseSpecialists:
        return message.agentId == AgentId.generator ||
            message.agentId == AgentId.summary ||
            message.agentId == AgentId.supervisor;
      case AgentDisplayMode.summaryOnly:
        return message.agentId == AgentId.summary ||
            message.agentId == AgentId.supervisor;
    }
  }).toList(growable: false);
}
