import 'agent_configuration.dart';

class AgentProfile {
  const AgentProfile({
    required this.id,
    required this.name,
    required this.description,
    required this.colorHex,
    required this.prompt,
    required this.configuration,
    this.isBuiltin = false,
  });

  final String id;
  final String name;
  final String description;
  final String colorHex;
  final String prompt;
  final AgentConfiguration configuration;
  final bool isBuiltin;

  factory AgentProfile.fromJson(Map<String, dynamic> json) {
    final rawConfiguration = json['configuration'];
    final configuration = rawConfiguration is Map<String, dynamic>
        ? AgentConfiguration.fromJson(rawConfiguration)
        : kDefaultAgentConfiguration.copyWith(
            agents: kDefaultAgentDefinitions.map((agent) {
              if (agent.agentId == AgentId.generator) {
                return agent.copyWith(
                  label: json['name'] as String? ?? agent.label,
                  prompt: json['prompt'] as String? ?? agent.prompt,
                );
              }
              return agent;
            }).toList(),
          );
    return AgentProfile(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      colorHex: json['color_hex'] as String? ?? '#55D6BE',
      prompt: json['prompt'] as String? ?? '',
      configuration: configuration,
      isBuiltin: json['is_builtin'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'id': id,
      'name': name,
      'description': description,
      'color_hex': colorHex,
      'prompt': prompt,
      'configuration': configuration.toJson(),
      'is_builtin': isBuiltin,
    };
  }
}
