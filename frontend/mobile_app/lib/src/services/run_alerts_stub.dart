import 'run_alerts.dart';

class _SilentRunAlerts implements RunAlerts {
  @override
  bool get supported => false;
  @override
  String get permission => 'denied';
  @override
  bool enabled = false;
  @override
  bool get userAway => false;
  @override
  Future<String> requestPermission() async => 'denied';
  @override
  void notify({
    required String title,
    required String body,
    required String tag,
    void Function()? onClick,
  }) {}
  @override
  void setAttentionCount(int count) {}
}

RunAlerts createRunAlerts() => _SilentRunAlerts();
