import 'dart:convert';

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
    final rawActivities = widget.activities
        .where((item) => item.kind != 'usage')
        .where((item) =>
            item.kind != 'commentary' ||
            item.title.trim() != widget.responseText.trim())
        .toList(growable: false);
    final activities = normalizeAgentActivities(rawActivities);
    if (activities.isEmpty) return const SizedBox.shrink();
    final expanded = _expanded ?? widget.isRunning;
    final subagentIds = {
      for (final item in activities)
        if (item.isSubagent) item.id,
    };
    final childrenByParent = <String, List<AgentActivity>>{};
    final roots = <AgentActivity>[];
    for (final item in activities) {
      final parent = item.parentId;
      if (parent != null && subagentIds.contains(parent)) {
        childrenByParent.putIfAbsent(parent, () => <AgentActivity>[]).add(item);
      } else {
        roots.add(item);
      }
    }
    final subagentCount = subagentIds.length;
    final earlierCount = roots.length > 6 ? roots.length - 6 : 0;
    final visible = _showEarlier || earlierCount == 0
        ? roots
        : roots.sublist(earlierCount);
    final failed = activities
        .where((item) => item.status == 'failed' || item.status == 'warning')
        .length;
    final running = activities.where((item) => item.status == 'running').length;
    final subtitle = [
      '${activities.length} ${activities.length == 1 ? 'paso' : 'pasos'}',
      if (subagentCount > 0)
        '$subagentCount ${subagentCount == 1 ? 'subagente' : 'subagentes'}',
      if (widget.isRunning) running > 0 ? '$running en curso' : 'Trabajando',
      if (failed > 0) '$failed con aviso',
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
                          if (item.isSubagent)
                            _SubagentNode(
                              key: ValueKey(item.id),
                              activity: item,
                              children: childrenByParent[item.id] ??
                                  const <AgentActivity>[],
                              onLinkTap: widget.onLinkTap,
                            )
                          else
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
      'warning' => (
          'Aviso',
          Icons.warning_amber_rounded,
          const Color(0xFFFFD08A)
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
                                          maxLines: _expanded ? null : 2,
                                          overflow: _expanded
                                              ? null
                                              : TextOverflow.ellipsis,
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


final RegExp _mcpStartupFailure = RegExp(
  r'''^(?:([\w.-]+) failed to start: )?MCP client for [`'"]?([\w.-]+)[`'"]? failed to start''',
  caseSensitive: false,
);

/// Makes raw provider events readable: groups MCP startup failures into one
/// warning row and moves very long titles into the expandable detail.
List<AgentActivity> normalizeAgentActivities(List<AgentActivity> input) {
  final result = <AgentActivity>[];
  final mcpNames = <String>[];
  final mcpDetails = <String>[];
  int? mcpIndex;
  final readyNames = <String>[];
  int? readyIndex;
  for (final original in input) {
    final item = _withReadableToolInput(_withCommandTitle(original));
    final title = item.title.trim();
    final ready = _mcpReady.firstMatch(title);
    if (ready != null && item.kind != 'commentary') {
      readyNames.add(ready.group(1)!);
      if (readyIndex == null) {
        readyIndex = result.length;
        result.add(AgentActivity(
          id: 'mcp-ready',
          kind: 'status',
          title: 'Herramientas listas',
          status: 'completed',
          createdAt: item.createdAt,
        ));
      }
      continue;
    }
    final match = _mcpStartupFailure.firstMatch(title);
    if (match != null && item.kind != 'commentary') {
      mcpNames.add(match.group(2) ?? match.group(1) ?? 'mcp');
      mcpDetails.add([title, item.detail.trim()].where((e) => e.isNotEmpty).join('\n'));
      mcpIndex ??= result.length;
      result.add(item); // placeholder, replaced below
      continue;
    }
    if (item.kind != 'commentary' && title.length > 160) {
      final cut = title.indexOf(RegExp(r'[:\n]'));
      final short = cut > 20 && cut < 140 ? title.substring(0, cut) : '${title.substring(0, 140)}…';
      result.add(AgentActivity(
        id: item.id,
        kind: item.kind,
        title: short,
        status: item.status,
        detail: [title, item.detail.trim()].where((e) => e.isNotEmpty).join('\n\n'),
        createdAt: item.createdAt,
        parentId: item.parentId,
      ));
      continue;
    }
    result.add(item);
  }
  if (readyIndex != null) {
    final names = readyNames.toSet().toList();
    result[readyIndex] = AgentActivity(
      id: 'mcp-ready',
      kind: 'status',
      title: names.length == 1
          ? 'Herramienta lista: ${names.first}'
          : 'Herramientas listas: ${names.join(', ')}',
      status: 'completed',
      createdAt: result[readyIndex].createdAt,
    );
  }
  if (mcpIndex != null) {
    final names = mcpNames.toSet().toList();
    final grouped = AgentActivity(
      id: 'mcp-startup-failures',
      kind: 'status',
      title: names.length == 1
          ? 'El servidor MCP ${names.first} no inició'
          : '${names.length} servidores MCP no iniciaron: ${names.join(', ')}',
      status: 'warning',
      detail: mcpDetails.join('\n\n'),
    );
    final out = <AgentActivity>[];
    for (var i = 0; i < result.length; i++) {
      final item = result[i];
      if (_mcpStartupFailure.hasMatch(item.title.trim()) && item.kind != 'commentary') {
        if (i == mcpIndex) out.add(grouped);
        continue;
      }
      out.add(item);
    }
    return out;
  }
  return result;
}

final RegExp _mcpReady = RegExp(r'^([\w.-]+) is ready\.?$');
final RegExp _shellWrapper = RegExp(
    r'''^(?:/(?:usr/)?bin/)?(?:ba|z)?sh\s+-l?c\s+(['"]?)(.*)\1$''',
    dotAll: true);

/// Uses the actual command as the row title instead of a generic "Comando".
AgentActivity _withCommandTitle(AgentActivity item) {
  final generic = item.title.trim().toLowerCase();
  if (generic != 'comando' && generic != 'command') return item;
  final firstLine = item.detail.trim().split('\n').first.trim();
  if (firstLine.isEmpty) return item;
  final unwrapped = _shellWrapper.firstMatch(firstLine)?.group(2) ?? firstLine;
  final title =
      unwrapped.length > 120 ? '${unwrapped.substring(0, 120)}…' : unwrapped;
  return AgentActivity(
    id: item.id,
    kind: item.kind,
    title: '\$ $title',
    status: item.status,
    detail: item.detail,
    createdAt: item.createdAt,
    parentId: item.parentId,
  );
}

/// A subagent launched by the main agent, with its own nested steps.
class _SubagentNode extends StatefulWidget {
  const _SubagentNode({
    super.key,
    required this.activity,
    required this.children,
    this.onLinkTap,
  });

  final AgentActivity activity;
  final List<AgentActivity> children;
  final Future<void> Function(String target)? onLinkTap;

  @override
  State<_SubagentNode> createState() => _SubagentNodeState();
}

class _SubagentNodeState extends State<_SubagentNode> {
  bool? _expanded;
  bool _showPrompt = false;

  @override
  Widget build(BuildContext context) {
    final item = widget.activity;
    final running = item.status == 'running' || item.status == 'pending';
    final expanded = _expanded ?? running;
    final failed = item.status == 'failed';
    final accent = failed
        ? const Color(0xFFFFB3B3)
        : running
            ? const Color(0xFF8FEAFF)
            : const Color(0xFFC9B6FF);
    final stepLabel =
        '${widget.children.length} ${widget.children.length == 1 ? 'paso' : 'pasos'}';
    final status = switch (item.status) {
      'running' || 'pending' => 'Trabajando',
      'completed' => 'Terminó',
      'failed' => 'Error',
      'cancelled' => 'Cancelado',
      _ => 'Sin resultado confirmado',
    };
    return Padding(
      padding: const EdgeInsets.only(left: 11, bottom: 8),
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0x14C9B6FF),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: accent.withValues(alpha: 0.35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Semantics(
              expanded: expanded,
              label: 'Subagente ${item.title}',
              child: InkWell(
                borderRadius: BorderRadius.circular(10),
                onTap: () => setState(() => _expanded = !expanded),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(10, 10, 6, 10),
                  child: Row(children: <Widget>[
                    Icon(Icons.account_tree_outlined, size: 18, color: accent),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            item.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 14),
                          ),
                          const SizedBox(height: 2),
                          Text('Subagente · $status · $stepLabel',
                              style: TextStyle(color: accent, fontSize: 12)),
                        ],
                      ),
                    ),
                    if (running)
                      const Padding(
                        padding: EdgeInsets.only(right: 6),
                        child: SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                    Icon(expanded ? Icons.expand_less : Icons.expand_more,
                        size: 20),
                  ]),
                ),
              ),
            ),
            if (expanded) ...<Widget>[
              if (item.detail.trim().isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => setState(() => _showPrompt = !_showPrompt),
                    icon: Icon(
                        _showPrompt
                            ? Icons.visibility_off_outlined
                            : Icons.description_outlined,
                        size: 16),
                    label: Text(_showPrompt ? 'Ocultar encargo' : 'Ver encargo'),
                  ),
                ),
              if (_showPrompt)
                Container(
                  margin: const EdgeInsets.fromLTRB(10, 0, 10, 8),
                  constraints: const BoxConstraints(maxHeight: 240),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF10192B),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SingleChildScrollView(
                    child: SelectableText(item.detail,
                        style: const TextStyle(
                            fontFamily: 'monospace', fontSize: 12.5, height: 1.4)),
                  ),
                ),
              if (widget.children.isEmpty)
                const Padding(
                  padding: EdgeInsets.fromLTRB(14, 0, 14, 10),
                  child: Text('Todavía sin pasos visibles.',
                      style: TextStyle(color: Color(0xFFB8C8E0), fontSize: 12)),
                ),
              for (final child in widget.children)
                _ActivityRow(
                  key: ValueKey('${item.id}/${child.id}'),
                  activity: child,
                  onLinkTap: widget.onLinkTap,
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Turns `{"command": ..., "description": ...}` style tool inputs into a
/// readable title and keeps the raw input (and any output) in the detail.
AgentActivity _withReadableToolInput(AgentActivity item) {
  if (item.kind != 'tool') return item;
  final detail = item.detail.trimLeft();
  if (!detail.startsWith('{')) return item;
  final split = detail.indexOf('\n\n');
  final head = split < 0 ? detail : detail.substring(0, split);
  final rest = split < 0 ? '' : detail.substring(split).trim();
  Map<String, dynamic> input;
  try {
    final decoded = jsonDecode(head);
    if (decoded is! Map<String, dynamic>) return item;
    input = decoded;
  } catch (_) {
    return item;
  }
  String? text(String key) {
    final value = input[key];
    return value is String && value.trim().isNotEmpty ? value.trim() : null;
  }

  String clip(String value, [int max = 110]) =>
      value.length > max ? '${value.substring(0, max)}…' : value;
  final command = text('command');
  final description = text('description');
  final path = text('file_path') ?? text('path') ?? text('notebook_path');
  final pattern = text('pattern') ?? text('query') ?? text('url');
  String? title;
  if (command != null) {
    title = '\$ ${clip(command.split('\n').first)}';
  } else if (path != null) {
    title = '${item.title} · ${clip(path)}';
  } else if (pattern != null) {
    title = '${item.title} · ${clip(pattern)}';
  } else if (description != null) {
    title = '${item.title} · ${clip(description)}';
  }
  if (title == null) return item;
  final readable = <String>[
    if (description != null && command != null) description,
    if (command != null) command,
    if (command == null) const JsonEncoder.withIndent('  ').convert(input),
    if (rest.isNotEmpty) rest,
  ].join('\n\n');
  return AgentActivity(
    id: item.id,
    kind: item.kind,
    title: title,
    status: item.status,
    detail: readable,
    createdAt: item.createdAt,
    parentId: item.parentId,
  );
}
