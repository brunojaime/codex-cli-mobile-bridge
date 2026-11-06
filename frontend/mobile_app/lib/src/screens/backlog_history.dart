import 'package:flutter/material.dart';
import '../services/work_client.dart';

/// A read-only archive with keyset pagination, independent of queue controls.
class BacklogHistory extends StatefulWidget {
  const BacklogHistory(
      {super.key,
      required this.client,
      this.workspacePath,
      required this.taskBuilder});
  final WorkClient client;
  final String? workspacePath;
  final Widget Function(Map<String, dynamic>) taskBuilder;
  @override
  State<BacklogHistory> createState() => _BacklogHistoryState();
}

class _BacklogHistoryState extends State<BacklogHistory> {
  final List<Map<String, dynamic>> _tasks = [];
  String? _cursor, _error;
  bool _loading = false;
  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.client.history(
          workspacePath: widget.workspacePath, cursor: reset ? null : _cursor);
      if (!mounted) return;
      setState(() {
        if (reset) _tasks.clear();
        for (final task
            in (data['tasks'] as List).cast<Map<String, dynamic>>()) {
          if (!_tasks.any((t) => t['id'] == task['id'])) {
            _tasks.add(task);
          }
        }
        _cursor = data['next_cursor'] as String?;
      });
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'No se pudo cargar el historial. Reintentá.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () => _load(reset: true),
        child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 104),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              Text('Historial del backlog',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 6),
              const Text(
                  'Terminados y retirados. Los pedidos pendientes siguen en Backlog.'),
              const SizedBox(height: 16),
              if (_loading) const LinearProgressIndicator(),
              if (_error != null) ...[
                Text(_error!),
                TextButton(
                    onPressed: () => _load(reset: _tasks.isEmpty),
                    child: const Text('Reintentar historial')),
              ],
              if (!_loading && _error == null && _tasks.isEmpty)
                const Padding(
                    padding: EdgeInsets.symmetric(vertical: 48),
                    child: Column(children: [
                      Icon(Icons.history_rounded, size: 40),
                      SizedBox(height: 12),
                      Text('Todavía no hay pedidos terminados ni retirados.')
                    ])),
              for (final task in _tasks) ...[
                if (widget.workspacePath == null)
                  Padding(
                      padding: const EdgeInsets.only(top: 16, bottom: 4),
                      child: Text(task['project_name'] as String? ?? '',
                          style: Theme.of(context).textTheme.labelLarge)),
                widget.taskBuilder(task),
              ],
              if (_cursor != null && !_loading)
                TextButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.expand_more),
                    label: const Text('Ver más historial')),
            ]),
      );
}
