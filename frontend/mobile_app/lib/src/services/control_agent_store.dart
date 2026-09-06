import 'package:shared_preferences/shared_preferences.dart';

class ControlAgentConfiguration {
  const ControlAgentConfiguration({required this.baseUrl, required this.token});

  final String baseUrl;
  final String token;
}

class ControlAgentStore {
  static const _baseUrlKey = 'control_agent_base_url';
  static const _tokenKey = 'control_agent_token';

  Future<ControlAgentConfiguration?> load() async {
    final preferences = await SharedPreferences.getInstance();
    final baseUrl = preferences.getString(_baseUrlKey)?.trim() ?? '';
    final token = preferences.getString(_tokenKey)?.trim() ?? '';
    if (baseUrl.isEmpty || token.isEmpty) {
      return null;
    }
    return ControlAgentConfiguration(baseUrl: baseUrl, token: token);
  }

  Future<void> save(ControlAgentConfiguration configuration) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_baseUrlKey, configuration.baseUrl);
    await preferences.setString(_tokenKey, configuration.token);
  }
}
