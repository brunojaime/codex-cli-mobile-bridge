import 'dart:async';

import 'package:flutter/material.dart';

import '../models/run_overview.dart';
import '../state/runs_monitor.dart';
import 'interaction_card.dart';

const _surface = Color(0xFF131C33);
const _border = Color(0xFF26324A);
const _text = Color(0xFFDCE5FF);
const _muted = Color(0xFF8B97B5);
const _teal = Color(0xFF55D6BE);
const _amber = Color(0xFFFFC857);
const _red = Color(0xFFFF6B81);

String formatElapsed(Duration value) {
  final hours = value.inHours;
  final minutes = value.inMinutes.remainder(60);
  final seconds = value.inSeconds.remainder(60);
  if (hours > 0) return '${hours}h ${minutes.toString().padLeft(2, '0')}m';
  return '$minutes:${seconds.toString().padLeft(2, '0')}';
}

String timeAgo(DateTime? value, DateTime now) {
  if (value == null) return '';
  final diff = now.difference(value);
  if (diff.inSeconds < 60) return 'recién';
  if (diff.inMinutes < 60) return 'hace ${diff.inMinutes} min';
  if (diff.inHours < 24) return 'hace ${diff.inHours} h';
  return 'hace ${diff.inDays} d';
}

/// Home screen: what every agent is doing and what it needs from the user.
class RunsDashboard extends StatefulWidget {
  const RunsDashboard({
    super.key,
    required this.monitor,
    required this.onOpenRun,
    required this.onStopRun,
    required this.onNewTask,
  });

  final RunsMonitor monitor;
  final void Function(RunCard run) onOpenRun;
  final Future<void> Function(RunCard run) onStopRun;
  final VoidCallback onNewTask;

  @override
  State<RunsDashboard> createState() => _RunsDashboardState();
}

class _RunsDashboardState extends State<RunsDashboard> {
  Timer? _ticker;
  bool _showAllFinished = false;

  @override
  void initState() {
    super.initState();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && widget.monitor.overview.runs.any((r) => r.isActive)) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.monitor,
      builder: (context, _) {
        final monitor = widget.monitor;
        final overview = monitor.overview;
        final now = DateTime.now();
        final needsYou = overview.where(RunState.needsYou);
        final working = overview.where(RunState.working);
        final queued = overview.where(RunState.queued);
        final allFinished = overview.runs.where((r) => !r.isActive).toList()
          ..sort((a, b) => (b.completedAt ?? b.updatedAt ?? DateTime(0))
              .compareTo(a.completedAt ?? a.updatedAt ?? DateTime(0)));
        // One row per chat (its latest run): a busy chat must not bury the
        // rest. Chats with something active are already shown above.
        final activeSessions = {
          for (final run in overview.runs)
            if (run.isActive) run.sessionId,
        };
        final runsPerSession = <String, int>{};
        final finished = <RunCard>[];
        for (final run in allFinished) {
          final seen = runsPerSession.containsKey(run.sessionId);
          runsPerSession[run.sessionId] = (runsPerSession[run.sessionId] ?? 0) + 1;
          if (!seen && !activeSessions.contains(run.sessionId)) finished.add(run);
        }
        final width = MediaQuery.sizeOf(context).width;
        final columns = width >= 1280 ? 3 : (width >= 760 ? 2 : 1);
        final visibleFinished =
            _showAllFinished ? finished : finished.take(8).toList();

        return RefreshIndicator(
          onRefresh: monitor.refresh,
          child: ListView(
            key: const ValueKey('runs-dashboard'),
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
            children: <Widget>[
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1240),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _Headline(
                        needsYou: needsYou.length,
                        working: working.length + queued.length,
                        loaded: monitor.loaded,
                        connected: monitor.connected,
                      ),
                      if (monitor.errorText != null)
                        _Notice(
                            text: monitor.errorText!,
                            onClose: monitor.clearError),
                      if (!monitor.loaded)
                        const Padding(
                          padding: EdgeInsets.all(40),
                          child: Center(child: CircularProgressIndicator()),
                        )
                      else if (overview.runs.isEmpty)
                        _EmptyState(onNewTask: widget.onNewTask)
                      else ...<Widget>[
                        if (needsYou.isNotEmpty) ...<Widget>[
                          _SectionTitle(
                              'Te necesita', needsYou.length, _amber),
                          for (final run in needsYou)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: _NeedsYouCard(
                                run: run,
                                now: now,
                                monitor: monitor,
                                onOpen: () => widget.onOpenRun(run),
                              ),
                            ),
                        ],
                        if (working.isNotEmpty || queued.isNotEmpty) ...<Widget>[
                          _SectionTitle('Trabajando ahora',
                              working.length + queued.length, _teal),
                          _Grid(
                            columns: columns,
                            children: <Widget>[
                              for (final run in <RunCard>[...working, ...queued])
                                _WorkingCard(
                                  run: run,
                                  now: now,
                                  onOpen: () => widget.onOpenRun(run),
                                  onStop: () => widget.onStopRun(run),
                                ),
                            ],
                          ),
                        ],
                        if (finished.isNotEmpty) ...<Widget>[
                          _SectionTitle('Terminado', finished.length, _muted),
                          Container(
                            decoration: BoxDecoration(
                              color: _surface,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: _border),
                            ),
                            child: Column(
                              children: <Widget>[
                                for (var i = 0; i < visibleFinished.length; i++)
                                  _FinishedRow(
                                    run: visibleFinished[i],
                                    runCount: runsPerSession[
                                            visibleFinished[i].sessionId] ??
                                        1,
                                    now: now,
                                    showDivider: i > 0,
                                    onOpen: () =>
                                        widget.onOpenRun(visibleFinished[i]),
                                  ),
                              ],
                            ),
                          ),
                          if (finished.length > visibleFinished.length ||
                              _showAllFinished && finished.length > 8)
                            Align(
                              alignment: Alignment.centerLeft,
                              child: TextButton(
                                onPressed: () => setState(
                                    () => _showAllFinished = !_showAllFinished),
                                child: Text(_showAllFinished
                                    ? 'Ver menos'
                                    : 'Ver ${finished.length - visibleFinished.length} más'),
                              ),
                            ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({
    required this.needsYou,
    required this.working,
    required this.loaded,
    required this.connected,
  });

  final int needsYou;
  final int working;
  final bool loaded;
  final bool connected;

  @override
  Widget build(BuildContext context) {
    final String title;
    final Color color;
    if (needsYou > 0) {
      title = needsYou == 1
          ? 'Un agente espera tu respuesta'
          : '$needsYou agentes esperan tu respuesta';
      color = _amber;
    } else if (working > 0) {
      title = working == 1 ? 'Un agente trabajando' : '$working agentes trabajando';
      color = _teal;
    } else {
      title = loaded ? 'Todo tranquilo' : 'Cargando…';
      color = _text;
    }
    final subtitle = needsYou > 0 && working > 0
        ? (working == 1 ? 'y otro sigue trabajando' : 'y $working siguen trabajando')
        : needsYou == 0 && working == 0 && loaded
            ? 'No hay nada corriendo ahora.'
            : null;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16, top: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(title,
                    style: TextStyle(
                        color: color,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        height: 1.2)),
                if (subtitle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(subtitle,
                        style: const TextStyle(color: _muted, fontSize: 14)),
                  ),
              ],
            ),
          ),
          Tooltip(
            message: connected
                ? 'Se actualiza solo, en vivo'
                : 'Reconectando con el servidor',
            child: Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Row(mainAxisSize: MainAxisSize.min, children: <Widget>[
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: connected ? _teal : _muted,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                Text(connected ? 'En vivo' : 'Sin conexión',
                    style: const TextStyle(color: _muted, fontSize: 12)),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.label, this.count, this.color);
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 12, 2, 10),
      child: Semantics(
        header: true,
        child: Row(children: <Widget>[
          Text(label,
              style: TextStyle(
                  color: color, fontWeight: FontWeight.w700, fontSize: 15)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
            decoration: BoxDecoration(
              color: color.withValues(alpha: .15),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text('$count',
                style: TextStyle(
                    color: color, fontSize: 12, fontWeight: FontWeight.w700)),
          ),
        ]),
      ),
    );
  }
}

class _Grid extends StatelessWidget {
  const _Grid({required this.columns, required this.children});
  final int columns;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      const gap = 12.0;
      final width = (constraints.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: <Widget>[
          for (final child in children) SizedBox(width: width, child: child),
        ],
      );
    });
  }
}

class _EngineBadge extends StatelessWidget {
  const _EngineBadge(this.run);
  final RunCard run;

  @override
  Widget build(BuildContext context) {
    final color = switch (run.engine) {
      'claude' => const Color(0xFFE8A27C),
      'codex' => const Color(0xFF8CA8FF),
      _ => _muted,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .14),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(run.engineLabel,
          style: TextStyle(
              color: color, fontSize: 11.5, fontWeight: FontWeight.w700)),
    );
  }
}

class _CardShell extends StatelessWidget {
  const _CardShell({
    required this.child,
    required this.onTap,
    this.accent = _border,
    this.label,
  });
  final Widget child;
  final VoidCallback onTap;
  final Color accent;
  final String? label;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: _surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: accent),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(onTap: onTap, child: child),
      ),
    );
  }
}

class _RunHeader extends StatelessWidget {
  const _RunHeader({required this.run, required this.trailing});
  final RunCard run;
  final String trailing;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(children: <Widget>[
          _EngineBadge(run),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              run.sessionTitle.isEmpty ? 'Sin título' : run.sessionTitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: _text, fontWeight: FontWeight.w700, fontSize: 15),
            ),
          ),
          const SizedBox(width: 8),
          Text(trailing,
              style: const TextStyle(
                  color: _muted,
                  fontSize: 12.5,
                  fontFeatures: <FontFeature>[FontFeature.tabularFigures()])),
        ]),
        if (run.workspaceName.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Text(run.workspaceName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: _muted, fontSize: 12)),
          ),
      ],
    );
  }
}

class _Asked extends StatelessWidget {
  const _Asked(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    if (text.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text.rich(
        TextSpan(children: <InlineSpan>[
          const TextSpan(
              text: 'Pediste: ', style: TextStyle(fontWeight: FontWeight.w600)),
          TextSpan(text: text),
        ]),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(color: _muted, fontSize: 13),
      ),
    );
  }
}

class _NeedsYouCard extends StatelessWidget {
  const _NeedsYouCard({
    required this.run,
    required this.now,
    required this.monitor,
    required this.onOpen,
  });
  final RunCard run;
  final DateTime now;
  final RunsMonitor monitor;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return _CardShell(
      onTap: onOpen,
      accent: _amber.withValues(alpha: .55),
      label: '${run.sessionTitle}, espera tu respuesta',
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _RunHeader(run: run, trailing: formatElapsed(run.elapsedAt(now))),
            _Asked(run.request),
            const SizedBox(height: 12),
            for (final pending in run.pending)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: InteractionCard(
                  key: ValueKey('interaction-${pending.requestId}'),
                  interaction: pending,
                  dense: true,
                  busy: monitor.isAnswering(pending.requestId),
                  onDecide: (decision) =>
                      monitor.respond(run, pending, decision),
                ),
              ),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: onOpen,
                icon: const Icon(Icons.open_in_new_rounded, size: 16),
                label: const Text('Ver todo lo que hizo'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PulseDot extends StatefulWidget {
  const _PulseDot();
  @override
  State<_PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<_PulseDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1100))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: .35, end: 1).animate(_controller),
      child: Container(
        width: 9,
        height: 9,
        decoration: const BoxDecoration(color: _teal, shape: BoxShape.circle),
      ),
    );
  }
}

class _WorkingCard extends StatelessWidget {
  const _WorkingCard({
    required this.run,
    required this.now,
    required this.onOpen,
    required this.onStop,
  });
  final RunCard run;
  final DateTime now;
  final VoidCallback onOpen;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final queued = run.state == RunState.queued;
    final facts = <String>[
      if (run.steps > 0) '${run.steps} paso${run.steps == 1 ? '' : 's'}',
      if (run.filesChanged > 0)
        '${run.filesChanged} archivo${run.filesChanged == 1 ? '' : 's'} editado${run.filesChanged == 1 ? '' : 's'}',
      if (run.failedSteps > 0)
        '${run.failedSteps} con error',
    ];
    return _CardShell(
      onTap: onOpen,
      label: '${run.sessionTitle}, ${run.headline}',
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 6, 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _RunHeader(
                  run: run, trailing: formatElapsed(run.elapsedAt(now))),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _Asked(run.request),
            ),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Padding(
                    padding: const EdgeInsets.only(top: 5),
                    child: queued
                        ? const Icon(Icons.schedule_rounded,
                            size: 12, color: _muted)
                        : const _PulseDot(),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      run.headline,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: _text, fontSize: 14.5, height: 1.35),
                    ),
                  ),
                ],
              ),
            ),
            if (run.output.trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(19, 8, 8, 0),
                child: Text(
                  run.output.trim(),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: _muted, fontSize: 13, height: 1.35),
                ),
              ),
            const SizedBox(height: 4),
            Row(
              children: <Widget>[
                const SizedBox(width: 19),
                Expanded(
                  child: Text(facts.join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: _muted, fontSize: 12)),
                ),
                IconButton(
                  tooltip: 'Detener',
                  onPressed: onStop,
                  icon: const Icon(Icons.stop_circle_outlined,
                      color: _muted, size: 22),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _FinishedRow extends StatelessWidget {
  const _FinishedRow({
    required this.run,
    this.runCount = 1,
    required this.now,
    required this.showDivider,
    required this.onOpen,
  });
  final RunCard run;
  final int runCount;
  final DateTime now;
  final bool showDivider;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final (icon, color, status) = switch (run.state) {
      RunState.failed => (Icons.error_outline_rounded, _red, 'Falló'),
      RunState.stopped => (Icons.stop_circle_outlined, _muted, 'Detenido'),
      _ => (Icons.check_circle_outline_rounded, _teal, 'Terminó'),
    };
    final when = timeAgo(run.completedAt ?? run.updatedAt, now);
    return Semantics(
      button: true,
      label: '$status: ${run.sessionTitle}. ${run.headline}',
      child: InkWell(
        onTap: onOpen,
        child: Container(
          decoration: BoxDecoration(
            border: showDivider
                ? const Border(top: BorderSide(color: _border))
                : null,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Icon(icon, color: color, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(children: <Widget>[
                      Expanded(
                        child: Text(
                          run.sessionTitle.isEmpty ? 'Sin título' : run.sessionTitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: _text,
                              fontWeight: FontWeight.w600,
                              fontSize: 14),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                          runCount > 1
                              ? '$when · $runCount corridas'
                              : when,
                          style: const TextStyle(color: _muted, fontSize: 12)),
                    ]),
                    const SizedBox(height: 2),
                    Text(
                      run.headline,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: run.state == RunState.failed ? _red : _muted,
                          fontSize: 13,
                          height: 1.3),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onNewTask});
  final VoidCallback onNewTask;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(children: <Widget>[
        const Icon(Icons.nights_stay_outlined, size: 44, color: _muted),
        const SizedBox(height: 12),
        const Text('Nada corriendo en las últimas 48 horas',
            textAlign: TextAlign.center,
            style: TextStyle(color: _muted, fontSize: 15)),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: onNewTask,
          icon: const Icon(Icons.add),
          label: const Text('Nueva tarea'),
        ),
      ]),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.text, required this.onClose});
  final String text;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
      decoration: BoxDecoration(
        color: const Color(0xFF362411),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(children: <Widget>[
        Expanded(child: Text(text, style: const TextStyle(color: _text))),
        IconButton(
          tooltip: 'Cerrar',
          onPressed: onClose,
          icon: const Icon(Icons.close, size: 18),
        ),
      ]),
    );
  }
}
