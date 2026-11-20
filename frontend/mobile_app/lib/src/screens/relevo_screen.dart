import 'dart:async';

import 'package:flutter/material.dart';

import '../models/relevo.dart';
import '../services/api_client.dart';

/// «Pasar a Batata»: traslada TODO el trabajo en curso del sistema a otro equipo.
///
/// El Bridge ejecuta el relevo desacoplado: cierra ordenadamente todos los chats activos
/// (también este), sube el trabajo y abre los chats de continuación en el destino.
class RelevoScreen extends StatefulWidget {
  const RelevoScreen({super.key, required this.client, this.pollInterval = const Duration(seconds: 3)});

  final ApiClient client;
  final Duration pollInterval;

  @override
  State<RelevoScreen> createState() => _RelevoScreenState();
}

class _RelevoScreenState extends State<RelevoScreen> {
  List<RelevoDestination> _destinations = const <RelevoDestination>[];
  String? _selected;
  RelevoRun? _run;
  String? _error;
  bool _loading = true;
  bool _starting = false;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final destinations = await widget.client.getRelevoDestinations();
      final run = await widget.client.getLatestRelevo();
      if (!mounted) return;
      setState(() {
        _destinations = destinations;
        _selected = destinations.where((d) => d.enabled).map((d) => d.name).firstOrNull;
        _run = run.isNone ? null : run;
        _loading = false;
        _error = null;
      });
      _schedulePoll();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '$error';
      });
    }
  }

  void _schedulePoll() {
    _poll?.cancel();
    if (_run?.isRunning ?? false) {
      _poll = Timer.periodic(widget.pollInterval, (_) => unawaited(_refresh()));
    }
  }

  Future<void> _refresh() async {
    try {
      final run = await widget.client.getLatestRelevo();
      if (!mounted) return;
      setState(() => _run = run.isNone ? null : run);
      if (!run.isRunning) _poll?.cancel();
    } catch (_) {
      // El Bridge puede no responder unos segundos mientras cierra chats: se reintenta.
    }
  }

  Future<void> _start() async {
    final destination = _selected;
    if (destination == null) return;
    final label = _destinations.firstWhere((d) => d.name == destination).label;
    final confirmed = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            icon: const Icon(Icons.swap_horiz_rounded),
            title: Text('¿Pasar todo a $label?'),
            content: Text(
              'Todos los chats que están trabajando ahora (en DEV y PROD, incluido este) '
              'van a recibir el aviso de cierre, terminar su paso y dejar un resumen. '
              'Después se sube el trabajo y se abren los chats de continuación en $label.',
            ),
            actions: <Widget>[
              TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancelar')),
              FilledButton(
                key: const Key('relevo-confirm'),
                onPressed: () => Navigator.of(context).pop(true),
                child: Text('Pasar a $label'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    setState(() {
      _starting = true;
      _error = null;
    });
    try {
      final run = await widget.client.startRelevo(destination);
      if (!mounted) return;
      setState(() => _run = run);
      if (run.alreadyRunning) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Ya había un relevo en curso: te muestro ese.')),
        );
      }
      _schedulePoll();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final running = _run?.isRunning ?? false;
    final selected = _destinations.where((d) => d.name == _selected).firstOrNull;
    return Scaffold(
      appBar: AppBar(title: const Text('Pasar de equipo')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
              children: <Widget>[
                Text(
                  'Mueve todo lo que está corriendo en este equipo a otro: cierra los chats activos '
                  'con un resumen, sube el trabajo y abre la continuación allá.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                for (final d in _destinations)
                  ListTile(
                    enabled: d.enabled && !running,
                    leading: Icon(d.name == _selected
                        ? Icons.radio_button_checked_rounded
                        : Icons.radio_button_unchecked_rounded),
                    onTap: () => setState(() => _selected = d.name),
                    title: Text(d.label),
                    subtitle: d.enabled ? null : Text(d.note ?? 'Todavía no configurado'),
                  ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  key: const Key('relevo-start'),
                  onPressed: selected == null || running || _starting ? null : _start,
                  icon: _starting
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.swap_horiz_rounded),
                  label: Text(running ? 'Relevo en curso…' : 'Pasar a ${selected?.label ?? '…'}'),
                ),
                if (_error != null) ...<Widget>[
                  const SizedBox(height: 12),
                  Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
                if (_run != null) ...<Widget>[
                  const SizedBox(height: 20),
                  _RunCard(run: _run!),
                ],
              ],
            ),
    );
  }
}

class _RunCard extends StatelessWidget {
  const _RunCard({required this.run});

  final RelevoRun run;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = switch (run.status) {
      'running' => 'Relevo en curso',
      'finished' => 'Relevo terminado',
      _ => 'El relevo falló',
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(children: <Widget>[
              if (run.isRunning)
                const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              else
                Icon(run.status == 'finished' ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                    color: run.status == 'finished' ? const Color(0xFF55D6BE) : theme.colorScheme.error),
              const SizedBox(width: 10),
              Expanded(child: Text(title, key: const Key('relevo-status'), style: theme.textTheme.titleMedium)),
            ]),
            if (run.isRunning || run.status == 'failed')
              for (final line in run.progress.reversed.take(4).toList().reversed)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(line, style: theme.textTheme.bodySmall),
                ),
            if (run.error != null && run.status == 'failed')
              Padding(padding: const EdgeInsets.only(top: 6), child: Text(run.error!)),
            for (final p in run.projects)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(p.name, style: theme.textTheme.titleSmall),
                    Text(p.state,
                        style: theme.textTheme.bodySmall?.copyWith(color: p.isError ? theme.colorScheme.error : null)),
                    for (final chat in p.chats) Text('· $chat', style: theme.textTheme.bodySmall),
                    if (p.destinationChatId != null)
                      Text('Chat en ${run.destination ?? 'destino'}: ${p.destinationChatId!.substring(0, 8)}',
                          style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
