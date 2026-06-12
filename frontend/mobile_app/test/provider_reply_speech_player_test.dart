import 'package:codex_mobile_frontend/src/services/provider_reply_speech_player.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('maps provider response formats to cache file extensions', () {
    expect(replyAudioFileExtensionForResponseFormat('ogg'), 'ogg');
    expect(replyAudioFileExtensionForResponseFormat('wav'), 'wav');
    expect(replyAudioFileExtensionForResponseFormat('unknown'), 'mp3');
  });
}
