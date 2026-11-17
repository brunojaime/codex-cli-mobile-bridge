import 'package:flutter/foundation.dart';

@immutable
class AgentActivity {
  const AgentActivity({
    required this.id,
    required this.kind,
    required this.title,
    required this.status,
    this.detail = '',
    this.createdAt,
    this.parentId,
  });

  final String id;
  final String kind;
  final String title;
  final String status;
  final String detail;
  final DateTime? createdAt;

  /// Id of the subagent activity that produced this step, if any.
  final String? parentId;

  bool get isSubagent => kind == 'subagent';

  factory AgentActivity.fromJson(Map<String, dynamic> json) => AgentActivity(
        id: json['id'] as String? ?? '',
        kind: json['kind'] as String? ?? 'tool',
        title: json['title'] as String? ?? '',
        status: json['status'] as String? ?? 'unknown',
        detail: json['detail'] as String? ?? '',
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
        parentId: (json['parent_id'] as String?)?.trim().isEmpty ?? true
            ? null
            : (json['parent_id'] as String).trim(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind,
        'title': title,
        'status': status,
        'detail': detail,
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
        if (parentId != null) 'parent_id': parentId,
      };

  @override
  bool operator ==(Object other) =>
      other is AgentActivity &&
      id == other.id &&
      kind == other.kind &&
      title == other.title &&
      status == other.status &&
      detail == other.detail &&
      createdAt == other.createdAt &&
      parentId == other.parentId;

  @override
  int get hashCode =>
      Object.hash(id, kind, title, status, detail, createdAt, parentId);
}

List<AgentActivity> parseAgentActivities(Object? value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => AgentActivity.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .where((item) => item.id.isNotEmpty && item.title.isNotEmpty)
        .toList(growable: false)
    : const [];
