import 'objective_progress.dart';

List<Map<String, dynamic>> _rows(dynamic value) =>
    (value as List? ?? []).whereType<Map<String, dynamic>>().toList();

/// A plain-language reading of observed state, never a promised schedule.
class ObjectiveBrief {
  const ObjectiveBrief(this.now, this.remaining, this.next, this.action);
  final String now, remaining, next, action;

  factory ObjectiveBrief.fromData(Map<String, dynamic> data) {
    final progress = ObjectiveProgress.fromData(data);
    final active = ObjectiveProgress.agents(data);
    final tasks = _rows((data['presentation'] as Map?)?['tasks']);
    final units = _rows(data['units']);
    final activeIds = active.map((a) => a['unit']).whereType<String>().toSet();
    final titles = tasks
        .where((t) => activeIds.contains(t['id']))
        .map((t) => '${t['title']}')
        .where((t) => t.isNotEmpty)
        .toSet();
    final terminal = ['paused', 'cancelled', 'budget_exhausted', 'completed']
        .contains(data['status']);
    final blocked = '${(data['blocker'] as Map?)?['reason'] ?? ''}'.isNotEmpty;
    if (terminal ||
        blocked ||
        active.isEmpty ||
        data['status'] == 'planning' ||
        active.any((a) => a['role'] == 'recovery')) {
      return ObjectiveBrief(
          progress.summary,
          data['status'] == 'completed'
              ? 'Confirmar qué versión está publicada.'
              : progress.next,
          terminal
              ? 'No hay una siguiente tarea en ejecución.'
              : 'El orden siguiente todavía no está confirmado.',
          blocked
              ? 'Revisá Atención: hay una dependencia que necesita resolución.'
              : data['status'] == 'budget_exhausted'
                  ? 'Revisar el límite antes de continuar.'
                  : 'No hay una acción solicitada a vos.');
    }
    const reviews = {
      'reviewer': 'funcionamiento',
      'ux_review': 'diseño',
      'security': 'seguridad'
    };
    final onlyReviews = active.every((a) => reviews.containsKey(a['role']));
    final correcting = _rows(data['issues'])
        .any((i) => i['status'] == 'open' && activeIds.contains(i['unit']));
    final subject = titles.isEmpty
        ? 'las entregas del proyecto'
        : titles.take(2).join(' y ');
    final now =
        '${onlyReviews ? 'Estamos revisando' : correcting ? 'Estamos corrigiendo' : 'Estamos trabajando en'}: $subject${titles.length > 2 ? ' y otras tareas' : ''}.';
    final remaining = onlyReviews
        ? 'Terminar la revisión de ${active.map((a) => reviews[a['role']]).toSet().join(', ')}. Puede aprobar o pedir ajustes.'
        : 'Completar este trabajo y pasar la revisión independiente.';
    final pending = units
        .where((u) =>
            !['accepted', 'implementing', 'reviewing'].contains(u['state']) &&
            _rows(data['jobs']).every((j) =>
                j['unit'] != u['id'] ||
                !['running', 'starting', 'launching', 'pending']
                    .contains(j['status'])) &&
            (u['depends_on'] as List? ?? []).any(activeIds.contains))
        .map((u) => u['id'])
        .toSet();
    final nextTitles = tasks
        .where((t) => pending.contains(t['id']))
        .map((t) => '${t['title']}')
        .take(2)
        .toList();
    return ObjectiveBrief(
        now,
        remaining,
        nextTitles.isEmpty
            ? 'El coordinador todavía no confirmó la siguiente tarea.'
            : 'Después de aprobar esta etapa podrá avanzar: ${nextTitles.join(' · ')}. El orden aún no está confirmado.',
        'No hay una acción solicitada a vos.');
  }
}
