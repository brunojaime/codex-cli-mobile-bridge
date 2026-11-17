import 'run_alerts_stub.dart'
    if (dart.library.js_interop) 'run_alerts_web.dart' as impl;

/// Browser-level alerts for runs: system notifications and a count in the
/// tab title. Platforms without support get a silent implementation.
abstract class RunAlerts {
  /// Whether this platform can show system notifications at all.
  bool get supported;

  /// `granted`, `denied` or `default` (not asked yet).
  String get permission;

  /// User preference; alerts are only shown when enabled and granted.
  bool get enabled;
  set enabled(bool value);

  /// True when the user is not looking at the app (hidden tab or unfocused).
  bool get userAway;

  Future<String> requestPermission();

  void notify({
    required String title,
    required String body,
    required String tag,
    void Function()? onClick,
  });

  /// Shows "(n)" in the tab title; 0 clears it.
  void setAttentionCount(int count);
}

RunAlerts createRunAlerts() => impl.createRunAlerts();
