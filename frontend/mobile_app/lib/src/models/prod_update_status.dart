class ProdUpdateStatus {
  const ProdUpdateStatus({
    required this.state,
    this.preparedUpdateId,
    this.updateVersion,
    this.notification = false,
    this.blockers = const <String>[],
    this.nextRequiredAction,
  });

  final String state;
  final String? preparedUpdateId;
  final String? updateVersion;
  final bool notification;
  final List<String> blockers;
  final String? nextRequiredAction;

  bool get isVisible => <String>{
        'waiting_for_idle',
        'auto_update_eligible',
        'updating',
        'updated_pending_ack',
        'failed',
      }.contains(state);

  factory ProdUpdateStatus.fromJson(Map<String, dynamic> json) {
    return ProdUpdateStatus(
      state: json['state'] as String? ?? 'idle',
      preparedUpdateId: json['prepared_update_id'] as String?,
      updateVersion: json['update_version'] as String?,
      notification: json['notification'] as bool? ?? false,
      blockers: _stringList(json['blockers']),
      nextRequiredAction: json['next_required_action'] as String?,
    );
  }

  static List<String> _stringList(Object? value) {
    if (value is! List) return const <String>[];
    return value
        .map((item) => item?.toString() ?? '')
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }
}
