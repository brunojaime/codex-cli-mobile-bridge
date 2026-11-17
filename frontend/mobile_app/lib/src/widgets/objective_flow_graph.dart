import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/objective_progress.dart';
import '../models/objective_attention.dart';

List<Map<String, dynamic>> _rows(dynamic value) =>
    (value as List? ?? []).whereType<Map<String, dynamic>>().toList();
String _role(dynamic role) =>
    const {
      'ux': 'Diseño',
      'generator': 'Construcción',
      'ux_review': 'Revisión visual',
      'reviewer': 'Funcionamiento',
      'security': 'Seguridad',
      'requirements': 'Planificación',
      'recovery': 'Resolución'
    }[role] ??
    'Equipo';

/// An execution graph: branches show concurrent work, not an invented sequence.
class ObjectiveFlowGraph extends StatelessWidget {
  const ObjectiveFlowGraph(
      {super.key, required this.data, required this.onAttention});
  final Map<String, dynamic> data;
  final VoidCallback onAttention;
  @override
  Widget build(BuildContext context) {
    final active = ObjectiveProgress.agents(data);
    final tasks = _rows((data['presentation'] as Map?)?['tasks']);
    final units = _rows(data['units']);
    final attention = ObjectiveAttention.fromData(data);
    final groups = <String, List<Map<String, dynamic>>>{};
    for (final a in active) {
      groups.putIfAbsent('${a['unit'] ?? a['role']}', () => []).add(a);
    }
    final entries = groups.entries.toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _node(
          context,
          Icons.flag_outlined,
          'Avance del objetivo',
          '${data['accepted_units'] ?? 0} de ${data['total_units'] ?? 0} etapas verificadas · no equivale a publicación',
          const Color(0xFF92A8FF),
          null),
      if (attention.needsDecision) ...[
        const _Connector(),
        _node(
            context,
            Icons.front_hand_outlined,
            attention.title,
            '${active.isEmpty ? 'Sin agentes activos. ' : 'Hay trabajo activo, pero también un impedimento. '}Tocá para ver el motivo y decidir.',
            const Color(0xFFEBC581),
            onAttention),
      ],
      const _Connector(),
      Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(
              active.isEmpty
                  ? 'Ahora · sin actividad registrada'
                  : '${active.length} ${active.length == 1 ? 'agente activo' : 'agentes activos'} · ${entries.length == 1 ? 'una tarea' : '${entries.length} tareas en paralelo'}',
              style: Theme.of(context).textTheme.titleMedium)),
      if (entries.isEmpty)
        _node(
            context,
            Icons.pause_circle_outline,
            data['status'] == 'completed'
                ? 'Trabajo del equipo finalizado'
                : data['status'] == 'paused'
                    ? 'Ejecución en pausa'
                    : 'No hay tareas ejecutándose',
            attention.needsDecision
                ? 'Abrí el impedimento para atenderlo.'
                : 'Se actualiza con la próxima consulta. No significa que la app esté terminada.',
            const Color(0xFFB4B9C6),
            attention.needsDecision ? onAttention : null),
      LayoutBuilder(builder: (context, constraints) {
        final capacity = constraints.maxWidth >= 850
            ? 3
            : constraints.maxWidth >= 560
                ? 2
                : 1;
        final columns = math.min(capacity, math.max(1, entries.length));
        final width = (constraints.maxWidth - 12 * (columns - 1)) / columns;
        if (columns == 1 && entries.length > 1) {
          return Column(children: [
            SizedBox(
                height: 20,
                width: constraints.maxWidth,
                child: CustomPaint(painter: _MobileBranchHeader())),
            for (var index = 0; index < entries.length; index++)
              IntrinsicHeight(
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                    SizedBox(
                        width: 24,
                        child: CustomPaint(
                            painter:
                                _MobileBranch(index == entries.length - 1))),
                    Expanded(
                        child: Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _branch(
                                context, entries[index], tasks, units))),
                  ])),
          ]);
        }
        return Column(children: [
          if (columns > 1)
            SizedBox(
                height: 30,
                width: constraints.maxWidth,
                child: CustomPaint(painter: _Branches(columns))),
          Wrap(spacing: 12, runSpacing: 12, children: [
            for (final entry in entries)
              SizedBox(
                  width: width, child: _branch(context, entry, tasks, units))
          ]),
        ]);
      }),
      if (units.any(
          (u) => u['state'] != 'accepted' && !groups.containsKey(u['id']))) ...[
        const _Connector(),
        _node(
            context,
            Icons.hourglass_bottom,
            'Trabajo pendiente',
            '${units.where((u) => u['state'] != 'accepted' && !groups.containsKey(u['id'])).length} etapas fuera de ejecución. Tocá para ver dependencias; no es un orden confirmado.',
            const Color(0xFFB4B9C6),
            () => _pending(context, tasks, units, groups.keys.toSet())),
      ],
      const SizedBox(height: 12),
      const Text(
          'Las ramas son simultáneas. Tocá una tarea para ver responsables y dependencias.',
          style: TextStyle(color: Color(0xFFB4B9C6), fontSize: 12)),
    ]);
  }

  Widget _branch(
      BuildContext context,
      MapEntry<String, List<Map<String, dynamic>>> entry,
      List<Map<String, dynamic>> tasks,
      List<Map<String, dynamic>> units) {
    final task = tasks.where((t) => t['id'] == entry.key).firstOrNull;
    final title = '${task?['title'] ?? _role(entry.value.first['role'])}';
    final roles = entry.value.map((a) => _role(a['role'])).toSet().join(' · ');
    final activity =
        ObjectiveProgress.activity(data, entry.value.first['unit']);
    return _node(context, Icons.play_circle_outline, title, '$roles\n$activity',
        const Color(0xFF72DAC4), () {
      final unit = units.where((u) => u['id'] == entry.key).firstOrNull;
      final deps = (unit?['depends_on'] as List? ?? []);
      showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          showDragHandle: true,
          builder: (context) => SafeArea(
              child: SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(title,
                            style: Theme.of(context).textTheme.headlineSmall),
                        const SizedBox(height: 8),
                        Text(activity),
                        if (task?['purpose'] != null) ...[
                          const SizedBox(height: 8),
                          Text('${task!['purpose']}')
                        ],
                        const SizedBox(height: 20),
                        const Text('Trabajando ahora',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                        for (final a in entry.value)
                          ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.person_outline),
                              title: Text(_role(a['role'])),
                              subtitle: Text(_since(a['started_at']))),
                        const Text('Depende de',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                        if (deps.isEmpty)
                          const Text(
                              'Sin dependencias registradas para esta tarea.'),
                        for (final id in deps)
                          ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: Icon(units.any((u) =>
                                      u['id'] == id && u['state'] == 'accepted')
                                  ? Icons.check_circle_outline
                                  : Icons.hourglass_empty),
                              title: Text(
                                  '${tasks.where((t) => t['id'] == id).firstOrNull?['title'] ?? 'Otra etapa'}')),
                        const SizedBox(height: 12),
                        FilledButton(
                            onPressed: () => Navigator.pop(context),
                            child: const Text('Entendido')),
                      ]))));
    });
  }

  String _since(dynamic value) {
    final d = DateTime.tryParse('$value');
    if (d == null) return 'En ejecución';
    final minutes = DateTime.now().difference(d).inMinutes;
    return minutes < 1
        ? 'Inició hace menos de un minuto'
        : 'Inició hace $minutes min';
  }

  void _pending(BuildContext context, List<Map<String, dynamic>> tasks,
      List<Map<String, dynamic>> units, Set<String> active) {
    final pending = units
        .where((u) => u['state'] != 'accepted' && !active.contains(u['id']))
        .toList();
    showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (context) => SafeArea(
            child: SizedBox(
                height: MediaQuery.sizeOf(context).height * .7,
                child: ListView(padding: const EdgeInsets.all(20), children: [
                  Text('Pendientes y dependencias',
                      style: Theme.of(context).textTheme.headlineSmall),
                  const Text(
                      'No están ejecutándose. El coordinador determina el próximo trabajo disponible.'),
                  for (final u in pending)
                    ListTile(
                        title: Text(
                            '${tasks.where((t) => t['id'] == u['id']).firstOrNull?['title'] ?? 'Etapa del proyecto'}'),
                        subtitle: Text((u['depends_on'] as List? ?? []).isEmpty
                            ? 'Sin dependencias registradas'
                            : 'Depende de: ${(u['depends_on'] as List).map((id) => tasks.where((t) => t['id'] == id).firstOrNull?['title'] ?? 'Otra etapa').join(' · ')}')),
                ]))));
  }

  Widget _node(BuildContext context, IconData icon, String title,
          String subtitle, Color color, VoidCallback? onTap) =>
      Card(
          margin: EdgeInsets.zero,
          color: const Color(0xFF1E2025),
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(color: color.withValues(alpha: .45))),
          child: InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: onTap,
              child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          Icon(icon, color: color),
                          const SizedBox(width: 10),
                          Expanded(
                              child: Text(title,
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium
                                      ?.copyWith(fontWeight: FontWeight.w700))),
                          if (onTap != null)
                            const Icon(Icons.chevron_right, size: 20)
                        ]),
                        const SizedBox(height: 10),
                        Text(subtitle,
                            style: const TextStyle(color: Color(0xFFD3D6DE))),
                      ]))));
}

class _Connector extends StatelessWidget {
  const _Connector();
  @override
  Widget build(BuildContext context) => const ExcludeSemantics(
      child: SizedBox(
          height: 30,
          child: Center(
              child: Icon(Icons.south, size: 24, color: Color(0xFF60799D)))));
}

class _Branches extends CustomPainter {
  const _Branches(this.columns);
  final int columns;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF60799D)
      ..strokeWidth = 2;
    final width = (size.width - 12 * (columns - 1)) / columns;
    final first = width / 2, last = (columns - 1) * (width + 12) + width / 2;
    canvas.drawLine(
        Offset(size.width / 2, 0), Offset(size.width / 2, 12), paint);
    canvas.drawLine(Offset(first, 12), Offset(last, 12), paint);
    for (var i = 0; i < columns; i++) {
      final x = i * (width + 12) + width / 2;
      canvas.drawLine(Offset(x, 12), Offset(x, size.height), paint);
      canvas.drawCircle(Offset(x, size.height - 3), 3, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _Branches oldDelegate) =>
      columns != oldDelegate.columns;
}

class _MobileBranchHeader extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF60799D)
      ..strokeWidth = 2;
    canvas.drawLine(
        Offset(size.width / 2, 0), Offset(size.width / 2, 8), paint);
    canvas.drawLine(Offset(size.width / 2, 8), const Offset(6, 8), paint);
    canvas.drawLine(const Offset(6, 8), Offset(6, size.height), paint);
  }

  @override
  bool shouldRepaint(covariant _MobileBranchHeader oldDelegate) => false;
}

class _MobileBranch extends CustomPainter {
  const _MobileBranch(this.last);
  final bool last;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF60799D)
      ..strokeWidth = 2;
    final y = (size.height - 12) / 2;
    canvas.drawLine(
        const Offset(6, 0), Offset(6, last ? y : size.height), paint);
    canvas.drawLine(Offset(6, y), Offset(size.width, y), paint);
    canvas.drawCircle(Offset(size.width - 3, y), 3, paint);
  }

  @override
  bool shouldRepaint(covariant _MobileBranch oldDelegate) =>
      last != oldDelegate.last;
}
