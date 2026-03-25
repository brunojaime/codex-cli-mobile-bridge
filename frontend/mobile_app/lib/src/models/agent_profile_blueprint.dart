import 'dart:convert';

import 'agent_configuration.dart';
import 'agent_profile.dart';

final RegExp _agentProfileBlockPattern = RegExp(
  r'```(?:agent-profile|agent_profile)\s*([\s\S]*?)```',
  caseSensitive: false,
);

List<AgentProfile> extractAgentProfilesFromMessage(String text) {
  final profiles = <AgentProfile>[];
  final seenIds = <String>{};

  for (final match in _agentProfileBlockPattern.allMatches(text)) {
    final block = match.group(1);
    if (block == null || block.trim().isEmpty) {
      continue;
    }
    final payload = _decodeJsonObject(block);
    if (payload == null) {
      continue;
    }
    final normalizedPayload = _normalizeProfilePayload(payload);
    if (normalizedPayload == null) {
      continue;
    }
    final profile = AgentProfile.fromJson(normalizedPayload);
    if (!seenIds.add(profile.id)) {
      continue;
    }
    profiles.add(profile);
  }

  return profiles;
}

Map<String, dynamic>? _decodeJsonObject(String rawJson) {
  try {
    final decoded = jsonDecode(rawJson);
    if (decoded is! Map) {
      return null;
    }
    return <String, dynamic>{
      for (final entry in decoded.entries)
        if (entry.key is String) entry.key as String: entry.value,
    };
  } catch (_) {
    return null;
  }
}

Map<String, dynamic>? _normalizeProfilePayload(Map<String, dynamic> payload) {
  final name = _readText(payload['name']);
  if (name == null) {
    return null;
  }

  AgentConfiguration? configuration;
  final rawConfiguration = payload['configuration'];
  if (rawConfiguration is Map) {
    final normalizedConfiguration = <String, dynamic>{
      for (final entry in rawConfiguration.entries)
        if (entry.key is String) entry.key as String: entry.value,
    };
    try {
      configuration = AgentConfiguration.fromJson(normalizedConfiguration);
    } catch (_) {
      configuration = null;
    }
  }

  final prompt = _readText(payload['prompt']) ??
      _primaryPromptFromConfiguration(configuration);
  if (prompt == null) {
    return null;
  }

  return <String, dynamic>{
    'id': _readText(payload['id']) ?? _slugify(name),
    'name': name,
    'description': _readText(payload['description']) ?? '',
    'color_hex': _normalizeColorHex(payload['color_hex']) ?? '#55D6BE',
    'prompt': prompt,
    if (configuration != null) 'configuration': configuration.toJson(),
    'is_builtin': false,
  };
}

String? _readText(Object? value) {
  if (value is! String) {
    return null;
  }
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

String? _normalizeColorHex(Object? value) {
  final raw = _readText(value);
  if (raw == null) {
    return null;
  }
  final normalized = raw.toUpperCase();
  final colorPattern = RegExp(r'^#[0-9A-F]{6}$');
  return colorPattern.hasMatch(normalized) ? normalized : null;
}

String _slugify(String value) {
  final normalized = value
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
  return normalized.isEmpty ? 'generated_agent' : normalized;
}

String? _primaryPromptFromConfiguration(AgentConfiguration? configuration) {
  if (configuration == null) {
    return null;
  }
  final primaryAgentId = configuration.preset == AgentPreset.supervisor
      ? AgentId.supervisor
      : AgentId.generator;
  return configuration.byId(primaryAgentId)?.prompt;
}
