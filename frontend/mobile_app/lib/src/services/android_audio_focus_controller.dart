import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class AndroidAudioFocusController {
  static const MethodChannel _channel =
      MethodChannel('codex_mobile_frontend/audio_focus');

  static bool get _isAndroidMobile =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  static Future<void> requestTransientRecordingFocus() async {
    if (!_isAndroidMobile) {
      return;
    }
    await _channel.invokeMethod<void>('requestTransientRecordingFocus');
  }

  static Future<void> releaseRecordingFocus() async {
    if (!_isAndroidMobile) {
      return;
    }
    await _channel.invokeMethod<void>('releaseRecordingFocus');
  }
}
