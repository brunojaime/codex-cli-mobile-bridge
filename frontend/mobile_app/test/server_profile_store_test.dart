import 'dart:convert';

import 'package:codex_mobile_frontend/src/services/server_profile_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('loadProfiles keeps an up-to-date local default profile', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'server_profiles': <String>[
        jsonEncode(<String, dynamic>{
          'id': 'remote-server',
          'name': 'Remote',
          'base_url': 'https://remote.example.com',
        }),
      ],
      'active_server_profile_id': 'remote-server',
    });

    final store = ServerProfileStore();
    final profiles = await store.loadProfiles(
      defaultBaseUrl: 'http://localhost:8000',
    );

    expect(profiles, hasLength(2));
    expect(profiles.first.id, 'default-server');
    expect(profiles.first.name, 'Local');
    expect(profiles.first.baseUrl, 'http://localhost:8000');
    expect(profiles.last.id, 'remote-server');
  });

  test('audio reply playback speed is stored per server and normalized',
      () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});

    final store = ServerProfileStore();

    expect(
      await store.loadAudioReplyPlaybackSpeed('http://localhost:8000'),
      1.0,
    );

    await store.saveAudioReplyPlaybackSpeed('http://localhost:8000', 1.49);
    await store.saveAudioReplyPlaybackSpeed('http://localhost:9000', 1.75);

    expect(
      await store.loadAudioReplyPlaybackSpeed('http://localhost:8000'),
      1.5,
    );
    expect(
      await store.loadAudioReplyPlaybackSpeed('http://localhost:9000'),
      1.75,
    );
  });
}
