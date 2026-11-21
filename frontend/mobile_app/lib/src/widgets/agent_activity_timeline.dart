import 'package:flutter/material.dart';

import '../models/agent_activity.dart';
import 'rich_message_content.dart';

/// Public progress and tool lifecycles, scoped to a single assistant response.
class AgentActivityTimeline extends StatefulWidget {
  const AgentActivityTimeline({
    super.key,
    required this.activities,
    required this.isRunning,
    this.responseText = '',
    this.onLinkTap,
  });

  final List<AgentActivity> activities;
  final bool isRunning;
  final String responseText;
  final Future<void> Function(String target)? onLinkTap;

  @override
  State<AgentActivityTimeline> createState() => _AgentActivityTimelineState();
}

class _AgentActivityTimelineState extends State<AgentActivityTimeline> {
  bool? _expanded;
  bool _showEarlier = false;

  @override
  Widget build(BuildContext context) {
    final activities = widget.activities
        .where((item) =>
            item.kind != 'commentary' ||
            item.title.trim() != widget.responseText.trim())
        .toList(growable: false);
    if (activities.isEmpty) return const SizedBox.shrink();
    final expanded = _expanded ?? widget.isRunning;
    final earlierCount = activities.length > 6 ? activities.length - 6 : 0;
    final visible = _showEarlier || earlierCount == 0
        ? activities
        : activities.sublist(earlierCount);
    final failed = activities.where((item) => item.status == 'failed').length;
    final running = activities.where((item) => item.status == 'running').length;
    final subtitle = [
      '${activities.length} ${activities.length == 1 ? 'paso' : 'pasos'}',
      if (widget.isRunning) running > 0 ? '$running en curso' : 'Trabajando',
      if (failed > 0) '$failed con error',
    ].join(' · ');
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF3A4863))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            expanded: expanded,
            child: TextButton(
              style: TextButton.styleFrom(
                foregroundColor: const Color(0xFFD9E4F5),
                alignment: Alignment.centerLeft,
                padding:
                    const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
                minimumSize: const Size(48, 48),
              ),
              onPressed: () => setState(() => _expanded = !expanded),
              child: Row(children: [
                Icon(
                    widget.isRunning
                        ? Icons.bolt_rounded
                        : Icons.history_rounded,
                    size: 18,
                    color: const Color(0xFF55D6BE)),
                const SizedBox(width: 8),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      const Text('Actividad',
                          style: TextStyle(fontWeight: FontWeight.w600)),
                      Text(subtitle,
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xFFB8C8E0))),
                    ])),
                Icon(expanded ? Icons.expand_less : Icons.expand_more,
                    size: 20),
              ]),
            ),
          ),
          AnimatedSize(
            duration: MediaQuery.disableAnimationsOf(context)
                ? Duration.zero
                : const Duration(milliseconds: 180),
            alignment: Alignment.topCenter,
            child: expanded
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                        if (earlierCount > 0 && !_showEarlier)
                          Align(
                              alignment: Alignment.centerLeft,
                              child: TextButton.icon(
                                onPressed: () =>
                                    setState(() => _showEarlier = true),
                                icon: const Icon(Icons.unfold_more_rounded,
                                    size: 16),
                                label:
                                    Text('Ver $earlierCount pasos anteriores'),
                              )),
                        for (final item in visible)
                          _ActivityRow(
                              key: ValueKey(item.id),
                              activity: item,
                              onInspect: () => setState(() {
                                    _expanded = true;
                                  }),
                              onLinkTap: widget.onLinkTap),
                        const SizedBox(height: 10),
                      ])
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}

class _ActivityRow extends StatefulWidget {
  const _ActivityRow(
      {super.key, required this.activity, this.onLinkTap, this.onInspect});
  final AgentActivity activity;
  final Future<void> Function(String target)? onLinkTap;
  final VoidCallback? onInspect;

  @override
  State<_ActivityRow> createState() => _ActivityRowState();
}

class _ActivityRowState extends State<_ActivityRow> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final item = widget.activity;
    final commentary = item.kind == 'commentary';
    final (label, icon, color) = switch (item.status) {
      'observed' => (
          'Registrado',
          Icons.notes_rounded,
          const Color(0xFFB8C8E0)
        ),
      'pending' => (
          'Pendiente',
          Icons.schedule_outlined,
          const Color(0xFFB8C8E0)
        ),
      'running' => (
          'En curso',
          Icons.pending_outlined,
          const Color(0xFF8FEAFF)
        ),
      'completed' => (
          'Completado',
          Icons.check_circle_outline_rounded,
          const Color(0xFF55D6BE)
        ),
      'failed' => (
          'Error',
          Icons.error_outline_rounded,
          const Color(0xFFFFB3B3)
        ),
      'cancelled' => (
          'Cancelado',
          Icons.cancel_outlined,
          const Color(0xFFFFD08A)
        ),
      _ => (
          'Sin resultado confirmado',
          Icons.help_outline_rounded,
          const Color(0xFFFFD08A)
        ),
    };
    return Padding(
      padding: const EdgeInsets.only(left: 11),
      child: DecoratedBox(
        decoration: const BoxDecoration(
            border: Border(left: BorderSide(color: Color(0xFF43516A)))),
        child: Padding(
          padding: const EdgeInsets.only(left: 14, bottom: 10, top: 2),
          child: commentary
              ? Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: RichMessageContent(
                    text: item.title,
                    textColor: const Color(0xFFD9E4F5),
                    onLinkTap: widget.onLinkTap,
                  ))
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                      Semantics(
                        expanded: item.detail.isNotEmpty ? _expanded : null,
                        child: TextButton(
                          onPressed: item.detail.isNotEmpty
                              ? () {
                                  if (!_expanded) widget.onInspect?.call();
                                  setState(() => _expanded = !_expanded);
                                }
                              : null,
                          style: TextButton.styleFrom(
                            alignment: Alignment.centerLeft,
                            foregroundColor: const Color(0xFFD9E4F5),
                            disabledForegroundColor: const Color(0xFFD9E4F5),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 4, vertical: 8),
                            minimumSize: const Size(48, 48),
                          ),
                          child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Padding(
                                    padding: const EdgeInsets.only(top: 2),
                                    child: Icon(icon, size: 17, color: color)),
                                const SizedBox(width: 9),
                                Expanded(
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                      Text(item.title,
                                          style: const TextStyle(
                                              fontSize: 14,
                                              fontWeight: FontWeight.w600)),
                                      const SizedBox(height: 3),
                                      Text(label,
                                          style: TextStyle(
                                              color: color, fontSize: 12)),
                                      if (!_expanded &&
                                          item.detail.trim().isNotEmpty) ...[
                                        const SizedBox(height: 4),
                                        Text(
                                            item.detail
                                                .trim()
                                                .split('\n')
                                                .first,
                                            maxLines: 2,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(
                                                color: Color(0xFFB8C8E0),
                                                fontFamily: 'monospace',
                                                fontSize: 12)),
                                      ],
                                    ])),
                                if (item.detail.isNotEmpty) ...[
                                  const SizedBox(width: 4),
                                  Icon(
                                      _expanded
                                          ? Icons.expand_less
                                          : Icons.expand_more,
                                      size: 18),
                                ],
                              ]),
                        ),
                      ),
                      if (_expanded && item.detail.isNotEmpty)
                        Container(
                          constraints: const BoxConstraints(maxHeight: 280),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                              color: const Color(0xFF10192B),
                              borderRadius: BorderRadius.circular(8)),
                          child: SingleChildScrollView(
                              child: SelectableText(item.detail,
                                  style: const TextStyle(
                                      color: Color(0xFFD9E4F5),
                                      fontFamily: 'monospace',
                                      fontSize: 13,
                                      height: 1.45))),
                        ),
                    ]),
        ),
      ),
    );
  }
}
