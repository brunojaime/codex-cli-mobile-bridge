import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/server_profile.dart';

class ServerProfileStore {
  static const _profilesKey = 'server_profiles';
  static const _activeProfileIdKey = 'active_server_profile_id';

  Future<List<ServerProfile>> loadProfiles({
    required String defaultBaseUrl,
  }) async {
    final preferences = await SharedPreferences.getInstance();
    final rawProfiles = preferences.getStringList(_profilesKey) ?? <String>[];
    final profiles = rawProfiles
        .map((item) => ServerProfile.fromJson(jsonDecode(item) as Map<String, dynamic>))
        .toList();

    if (profiles.isEmpty) {
      final defaultProfile = ServerProfile(
        id: 'default-server',
        name: 'Local',
        baseUrl: defaultBaseUrl,
      );
      await saveProfiles(<ServerProfile>[defaultProfile]);
      await saveActiveProfileId(defaultProfile.id);
      return <ServerProfile>[defaultProfile];
    }

    return profiles;
  }

  Future<void> saveProfiles(List<ServerProfile> profiles) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setStringList(
      _profilesKey,
      profiles.map((profile) => jsonEncode(profile.toJson())).toList(),
    );
  }

  Future<String?> loadActiveProfileId() async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(_activeProfileIdKey);
  }

  Future<void> saveActiveProfileId(String profileId) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_activeProfileIdKey, profileId);
  }
}
