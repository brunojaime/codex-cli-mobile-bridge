import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('New Project intake config keeps reviewer gated during collection', () {
    final config = buildProjectFactoryIntakeConfiguration(
      kDefaultAgentConfiguration,
    );

    expect(isProjectFactoryIntakeConfiguration(config), isTrue);
    expect(config.byId(AgentId.reviewer)?.enabled, isFalse);
  });

  test('build confirmation requires ready marker in transcript', () {
    expect(isProjectFactoryBuildConfirmation('ok, dale para adelante'), isTrue);
    expect(projectFactoryHasBuildReadyMarker(<ChatMessage>[]), isFalse);

    final readyMessage = ChatMessage(
      id: 'assistant-ready',
      text: 'Contract accepted\n$kProjectFactoryReadyForBuildMarker',
      isUser: false,
      authorType: ChatMessageAuthorType.assistant,
      agentId: AgentId.generator,
      status: ChatMessageStatus.completed,
      createdAt: DateTime.utc(2026, 1, 1),
      updatedAt: DateTime.utc(2026, 1, 1),
    );

    expect(
        projectFactoryHasBuildReadyMarker(<ChatMessage>[readyMessage]), isTrue);
  });
}
