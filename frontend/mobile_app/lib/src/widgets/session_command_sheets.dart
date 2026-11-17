import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_client.dart';

const _muted = Color(0xFF8B97B5);
const _text = Color(0xFFDCE5FF);
const _teal = Color(0xFF55D6BE);

Widget _sheetTitle(BuildContext context, String title, [String? subtitle]) =>
    Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          if (subtitle != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(subtitle, style: const TextStyle(color: _muted)),
            ),
        ],
      ),
    );

Widget _row(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 140,
            child: Text(label, style: const TextStyle(color: _muted)),
          ),
          Expanded(child: SelectableText(value)),
        ],
      ),
    );

/// `/status`: what this chat is, where it runs and what it is doing.
Future<void> showStatusSheet(
  BuildContext context, {
  required List<(String, String)> rows,
  VoidCallback? onUsage,
  VoidCallback? onPermissions,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _sheetTitle(context, 'Estado'),
            for (final row in rows) _row(row.$1, row.$2),
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
              if (onUsage != null)
                OutlinedButton.icon(
                  onPressed: () {
                    Navigator.of(context).pop();
                    onUsage();
                  },
                  icon: const Icon(Icons.data_usage_rounded, size: 18),
                  label: const Text('Uso y límites'),
                ),
              if (onPermissions != null)
                OutlinedButton.icon(
                  onPressed: () {
                    Navigator.of(context).pop();
                    onPermissions();
                  },
                  icon: const Icon(Icons.shield_outlined, size: 18),
                  label: const Text('Permisos'),
                ),
            ]),
          ],
        ),
      ),
    ),
  );
}

/// `/permissions`: agent modes plus Claude's remembered rules (removable).
Future<void> showPermissionsSheet(
  BuildContext context, {
  required ApiClient client,
  required String sessionId,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) =>
        _PermissionsSheet(client: client, sessionId: sessionId),
  );
}

class _PermissionsSheet extends StatefulWidget {
  const _PermissionsSheet({required this.client, required this.sessionId});
  final ApiClient client;
  final String sessionId;

  @override
  State<_PermissionsSheet> createState() => _PermissionsSheetState();
}

class _PermissionsSheetState extends State<_PermissionsSheet> {
  Map<String, dynamic>? _data;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await widget.client.getSessionPermissions(widget.sessionId);
      if (mounted) setState(() => _data = data);
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    }
  }

  Future<void> _remove(String list, String rule) async {
    try {
      await widget.client.removePermissionRule(widget.sessionId, list, rule);
      await _load();
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    }
  }

  List<Widget> _rules(Map<String, dynamic>? scope, {required bool editable}) {
    final rules = (scope?['rules'] as Map?) ?? const {};
    const labels = <String, String>{
      'allow': 'Permitido siempre',
      'ask': 'Preguntar siempre',
      'deny': 'Bloqueado',
    };
    final widgets = <Widget>[];
    for (final entry in labels.entries) {
      final list = (rules[entry.key] as List?)?.cast<Object?>() ?? const [];
      for (final rule in list.whereType<String>()) {
        widgets.add(ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          leading: Icon(
            entry.key == 'deny'
                ? Icons.block_rounded
                : entry.key == 'ask'
                    ? Icons.help_outline_rounded
                    : Icons.check_circle_outline_rounded,
            size: 18,
            color: entry.key == 'allow' ? _teal : _muted,
          ),
          title: Text(rule,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
          subtitle: Text(entry.value),
          trailing: editable
              ? IconButton(
                  tooltip: 'Olvidar esta regla',
                  icon: const Icon(Icons.delete_outline_rounded),
                  onPressed: () => _remove(entry.key, rule),
                )
              : null,
        ));
      }
    }
    return widgets;
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final claude = data?['claude'] as Map?;
    final codex = data?['codex'] as Map?;
    final local = _rules(data?['local'] as Map<String, dynamic>?, editable: true);
    final shared =
        _rules(data?['shared'] as Map<String, dynamic>?, editable: false);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _sheetTitle(context, 'Permisos',
                'Qué puede hacer cada agente en este proyecto.'),
            if (_error != null)
              Text(_error!, style: const TextStyle(color: Color(0xFFFF6B81))),
            if (data == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (data != null) ...<Widget>[
              _row('Claude', '${claude?['description'] ?? ''} (${claude?['mode']})'),
              _row('Codex', '${codex?['description'] ?? ''}'),
              const SizedBox(height: 12),
              const Text('Recordados en este proyecto',
                  style: TextStyle(color: _text, fontWeight: FontWeight.w700)),
              const Text(
                  'Se agregan cuando elegís "Permitir siempre". Borralos para que vuelva a preguntar.',
                  style: TextStyle(color: _muted, fontSize: 12.5)),
              if (local.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 10),
                  child: Text('Todavía no hay reglas recordadas.',
                      style: TextStyle(color: _muted)),
                ),
              ...local,
              if (shared.isNotEmpty) ...<Widget>[
                const SizedBox(height: 12),
                const Text('Del repositorio (.claude/settings.json)',
                    style: TextStyle(color: _text, fontWeight: FontWeight.w700)),
                ...shared,
              ],
            ],
          ],
        ),
      ),
    );
  }
}

/// `/agents`: pick a subagent and give it a task. Returns the message to send.
Future<String?> showSubagentSheet(
  BuildContext context, {
  required ApiClient client,
  required String sessionId,
  required bool isClaude,
}) {
  return showModalBottomSheet<String>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) => Padding(
      padding:
          EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: _SubagentSheet(
          client: client, sessionId: sessionId, isClaude: isClaude),
    ),
  );
}

class _SubagentSheet extends StatefulWidget {
  const _SubagentSheet({
    required this.client,
    required this.sessionId,
    required this.isClaude,
  });
  final ApiClient client;
  final String sessionId;
  final bool isClaude;

  @override
  State<_SubagentSheet> createState() => _SubagentSheetState();
}

class _SubagentSheetState extends State<_SubagentSheet> {
  List<Map<String, dynamic>>? _agents;
  String? _selected;
  String? _error;
  final TextEditingController _task = TextEditingController();

  @override
  void initState() {
    super.initState();
    _task.addListener(() => setState(() {}));
    if (widget.isClaude) {
      widget.client.getSubagents(widget.sessionId).then((agents) {
        if (mounted) {
          setState(() {
            _agents = agents;
            _selected = agents.isEmpty ? null : 'general-purpose';
          });
        }
      }).catchError((Object error) {
        if (mounted) setState(() => _error = '$error');
      });
    }
  }

  @override
  void dispose() {
    _task.dispose();
    super.dispose();
  }

  String _message() {
    final task = _task.text.trim();
    // The task goes first so lists and the dashboard show what was asked.
    if (!widget.isClaude) {
      return 'Con un subagente: $task\n\n'
          'Lanzá un subagente (spawn_agent) para esa tarea, esperá su resultado y resumímelo.';
    }
    final name = _selected ?? 'general-purpose';
    return 'Con el subagente $name: $task\n\n'
        'Usá el subagente "$name" (herramienta Agent) para esa tarea y resumime lo que encontró.';
  }

  void _launch() {
    if (_task.text.trim().isEmpty) return;
    Navigator.of(context).pop(_message());
  }

  @override
  Widget build(BuildContext context) {
    final agents = _agents ?? const <Map<String, dynamic>>[];
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _sheetTitle(
              context,
              'Lanzar subagente',
              widget.isClaude
                  ? 'Trabaja aparte y te devuelve la conclusión. Lo ves como una rama en los pasos.'
                  : 'Codex abre un agente en paralelo y te trae su resultado.',
            ),
            if (_error != null)
              Text(_error!, style: const TextStyle(color: Color(0xFFFF6B81))),
            if (widget.isClaude && _agents == null && _error == null)
              const LinearProgressIndicator(),
            if (agents.isNotEmpty)
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  for (final agent in agents)
                    Tooltip(
                      message: '${agent['description'] ?? ''}',
                      child: ChoiceChip(
                        label: Text('${agent['name']}'),
                        avatar: agent['source'] == 'builtin'
                            ? null
                            : const Icon(Icons.person_outline, size: 16),
                        selected: _selected == agent['name'],
                        onSelected: (_) =>
                            setState(() => _selected = '${agent['name']}'),
                      ),
                    ),
                ],
              ),
            if (_selected != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  '${agents.firstWhere((a) => a['name'] == _selected, orElse: () => const {})['description'] ?? ''}',
                  style: const TextStyle(color: _muted, fontSize: 13),
                ),
              ),
            const SizedBox(height: 12),
            CallbackShortcuts(
              bindings: <ShortcutActivator, VoidCallback>{
                const SingleActivator(LogicalKeyboardKey.enter, control: true):
                    _launch,
              },
              child: TextField(
                controller: _task,
                autofocus: true,
                minLines: 2,
                maxLines: 6,
                decoration: const InputDecoration(
                  hintText: '¿Qué tiene que hacer? (Ctrl+Enter para lanzar)',
                ),
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                onPressed: _task.text.trim().isEmpty ? null : _launch,
                icon: const Icon(Icons.call_split_rounded, size: 18),
                label: const Text('Lanzar'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
