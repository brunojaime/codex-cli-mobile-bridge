import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'run_alerts.dart';

const _enabledKey = 'codex-bridge.run-alerts.enabled';

class _WebRunAlerts implements RunAlerts {
  String? _baseTitle;

  @override
  bool get supported {
    try {
      return web.window.has('Notification');
    } catch (_) {
      return false;
    }
  }

  @override
  String get permission => supported ? web.Notification.permission : 'denied';

  @override
  bool get enabled {
    try {
      return web.window.localStorage.getItem(_enabledKey) != 'false';
    } catch (_) {
      return true;
    }
  }

  @override
  set enabled(bool value) {
    try {
      web.window.localStorage.setItem(_enabledKey, value ? 'true' : 'false');
    } catch (_) {}
  }

  @override
  bool get userAway {
    try {
      return web.document.hidden || !web.document.hasFocus();
    } catch (_) {
      return false;
    }
  }

  @override
  Future<String> requestPermission() async {
    if (!supported) return 'denied';
    try {
      final result = await web.Notification.requestPermission().toDart;
      return result.toDart;
    } catch (_) {
      return permission;
    }
  }

  @override
  void notify({
    required String title,
    required String body,
    required String tag,
    void Function()? onClick,
  }) {
    if (!supported || !enabled || permission != 'granted') return;
    try {
      final notification = web.Notification(
        title,
        web.NotificationOptions(body: body, tag: tag),
      );
      notification.onclick = ((web.Event _) {
        web.window.focus();
        notification.close();
        onClick?.call();
      }).toJS;
    } catch (_) {}
  }

  @override
  void setAttentionCount(int count) {
    try {
      final current = web.document.title;
      final base = _baseTitle ??
          current.replaceFirst(RegExp(r'^\(\d+\) '), '');
      _baseTitle = base;
      final next = count > 0 ? '($count) $base' : base;
      if (current != next) web.document.title = next;
    } catch (_) {}
  }
}

RunAlerts createRunAlerts() => _WebRunAlerts();
