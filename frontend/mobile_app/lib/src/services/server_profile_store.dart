import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/server_profile.dart';
import '../models/workspace.dart';

class ServerProfileStore {
  static const _profilesKey = 'server_profiles';
  static const _activeProfileIdKey = 'active_server_profile_id';
  static const _sidebarExpandedKey = 'sidebar_expanded';

  Future<List<ServerProfile>> loadProfiles({
    required String defaultBaseUrl,
  }) async {
    final preferences = await SharedPreferences.getInstance();
    final rawProfiles = preferences.getStringList(_profilesKey) ?? <String>[];
    final storedProfiles = rawProfiles
        .map((item) =>
            ServerProfile.fromJson(jsonDecode(item) as Map<String, dynamic>))
        .toList();
    ServerProfile? storedDefaultProfile;
    for (final profile in storedProfiles) {
      if (profile.id == 'default-server') {
        storedDefaultProfile = profile;
        break;
      }
    }
    final defaultProfile = ServerProfile(
      id: 'default-server',
      name: storedDefaultProfile?.name ?? 'Local',
      baseUrl: defaultBaseUrl,
    );

    final profiles = <ServerProfile>[
      defaultProfile,
      ...storedProfiles.where((profile) => profile.id != defaultProfile.id),
    ];

    final shouldPersistProfiles = storedProfiles.length != profiles.length ||
        storedProfiles.isEmpty ||
        storedProfiles.first.id != defaultProfile.id ||
        storedDefaultProfile?.baseUrl != defaultBaseUrl;
    if (shouldPersistProfiles) {
      await saveProfiles(profiles);
    }

    final activeProfileId = preferences.getString(_activeProfileIdKey);
    if (activeProfileId == null || activeProfileId.isEmpty) {
      await saveActiveProfileId(defaultProfile.id);
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

  Future<bool> loadSidebarExpanded() async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getBool(_sidebarExpandedKey) ?? false;
  }

  Future<void> saveSidebarExpanded(bool expanded) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_sidebarExpandedKey, expanded);
  }

  Future<List<Workspace>> loadSidebarWorkspaces(String serverBaseUrl) async {
    final preferences = await SharedPreferences.getInstance();
    final rawWorkspaces =
        preferences.getStringList(_sidebarWorkspacesKey(serverBaseUrl)) ??
            <String>[];
    return rawWorkspaces
        .map((item) =>
            Workspace.fromJson(jsonDecode(item) as Map<String, dynamic>))
        .toList();
  }

  Future<void> saveSidebarWorkspaces(
    String serverBaseUrl,
    List<Workspace> workspaces,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setStringList(
      _sidebarWorkspacesKey(serverBaseUrl),
      workspaces.map((workspace) => jsonEncode(workspace.toJson())).toList(),
    );
  }

  String _sidebarWorkspacesKey(String serverBaseUrl) {
    return 'sidebar_workspaces::$serverBaseUrl';
  }

  Future<Map<String, DateTime>> loadSessionReadMarkers(
    String serverBaseUrl,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    final rawMarkers =
        preferences.getString(_sessionReadMarkersKey(serverBaseUrl));
    if (rawMarkers == null || rawMarkers.isEmpty) {
      return <String, DateTime>{};
    }

    final decoded = jsonDecode(rawMarkers) as Map<String, dynamic>;
    return decoded.map(
      (sessionId, value) => MapEntry(
        sessionId,
        DateTime.parse(value as String),
      ),
    );
  }

  Future<void> saveSessionReadMarkers(
    String serverBaseUrl,
    Map<String, DateTime> markers,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    final serialized = markers.map(
      (sessionId, value) => MapEntry(sessionId, value.toIso8601String()),
    );
    await preferences.setString(
      _sessionReadMarkersKey(serverBaseUrl),
      jsonEncode(serialized),
    );
  }

  String _sessionReadMarkersKey(String serverBaseUrl) {
    return 'session_read_markers::$serverBaseUrl';
  }

  Future<bool> loadAudioRepliesEnabled(String serverBaseUrl) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getBool(_audioRepliesEnabledKey(serverBaseUrl)) ?? false;
  }

  Future<void> saveAudioRepliesEnabled(
    String serverBaseUrl,
    bool enabled,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_audioRepliesEnabledKey(serverBaseUrl), enabled);
  }

  String _audioRepliesEnabledKey(String serverBaseUrl) {
    return 'audio_replies_enabled::$serverBaseUrl';
  }
}
