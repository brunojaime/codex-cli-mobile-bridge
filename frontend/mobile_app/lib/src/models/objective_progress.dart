List<Map<String, dynamic>> _rows(dynamic value) =>
    (value as List? ?? []).whereType<Map<String, dynamic>>().toList();

class ObjectiveProgress {
  const ObjectiveProgress(this.title, this.summary, this.next, this.action);
  final String title;
  final String summary;
  final String next;
  final String action;

  static List<Map<String, dynamic>> agents(Map<String, dynamic> data) {
    final jobs = _rows(data['jobs'])
        .where((j) => ['running', 'starting', 'launching', 'pending']
            .contains(j['status']))
        .toList();
    return jobs.isNotEmpty ? jobs : _rows(data['active_agents']);
  }

  static String activity(Map<String, dynamic> data, dynamic unit) {
    final assigned = agents(data).where((a) => a['unit'] == unit).toList();
    if (assigned.isEmpty) return 'En espera';
    if (assigned.any(
        (a) => ['reviewer', 'ux_review', 'security'].contains(a['role']))) {
      return 'Verificando la entrega';
    }
    if (_rows(data['issues'])
        .any((i) => i['unit'] == unit && i['status'] == 'open')) {
      return 'Corrigiendo observaciones';
    }
    final reviewed = _rows(data['jobs']).any((j) =>
        j['unit'] == unit &&
        j['status'] == 'completed' &&
        j['verdict'] == 'pass');
    return reviewed
        ? 'Ajustando una entrega revisada'
        : 'Construyendo esta etapa';
  }

  factory ObjectiveProgress.fromData(Map<String, dynamic> data) {
    final active = agents(data);
    final status = data['status'];
    final blocker = data['blocker'] as Map? ?? {};
    final product = data['presentation'] as Map? ?? {};
    const none = 'Sin acción solicitada a vos';
    if ('${blocker['reason'] ?? ''}'.trim().isNotEmpty) {
      return const ObjectiveProgress(
          'Hay un impedimento registrado',
          'El equipo necesita resolver una dependencia para continuar.',
          'Consultar el motivo y el paso solicitado en Atención.',
          'Revisá Atención');
    }
    if (status == 'paused' ||
        status == 'cancelled' ||
        status == 'budget_exhausted') {
      return ObjectiveProgress(
          status == 'paused'
              ? 'Ejecución en pausa'
              : status == 'cancelled'
                  ? 'Ejecución cancelada'
                  : 'Límite de ejecución alcanzado',
          'El trabajo realizado se conserva.',
          'Revisar el estado antes de continuar.',
          none);
    }
    if (status == 'completed') {
      return const ObjectiveProgress(
          'Trabajo del equipo finalizado',
          'La aceptación del código no acredita por sí sola la publicación de la app.',
          'Consultar los resultados y la verificación del despliegue.',
          none);
    }
    if (active.any((a) => a['role'] == 'recovery')) {
      return const ObjectiveProgress(
          'Resolviendo un impedimento',
          'El equipo está preparando una corrección para poder continuar.',
          'Aplicar la corrección y comprobar que el trabajo retome.',
          none);
    }
    if (status == 'planning') {
      return ObjectiveProgress(
          active.isEmpty
              ? 'Esperando actividad de planificación'
              : 'Preparando el plan',
          'Se están organizando las historias y el orden del trabajo.',
          'Validar el plan antes de comenzar la implementación.',
          none);
    }
    if (active.isEmpty) {
      return const ObjectiveProgress(
          'Sin actividad registrada',
          'La última consulta no muestra agentes trabajando. No podemos confirmar que esté avanzando.',
          'Esperar la próxima actualización o revisar Atención.',
          none);
    }
    final correcting =
        _rows(data['issues']).any((i) => i['status'] == 'open') ||
            (product['issues'] as num? ?? 0) > 0;
    if (correcting) {
      return const ObjectiveProgress(
          'Correcciones en curso',
          'El equipo está ajustando entregas observadas en la revisión.',
          'Volver a verificar los cambios antes de aprobar estas etapas.',
          none);
    }
    if (active.any(
        (a) => activity(data, a['unit']) == 'Ajustando una entrega revisada')) {
      return const ObjectiveProgress(
          'Ajustando una entrega revisada',
          'Se está trabajando sobre una etapa que ya tuvo una revisión aprobada.',
          'Comprobar los nuevos cambios antes de continuar.',
          none);
    }
    if (status == 'final_review' ||
        active.every(
            (a) => ['reviewer', 'ux_review', 'security'].contains(a['role']))) {
      return const ObjectiveProgress(
          'Verificando las entregas',
          'El equipo está comprobando el funcionamiento y los controles aplicables.',
          'Aprobar lo comprobado o devolver observaciones para corregir.',
          none);
    }
    return const ObjectiveProgress(
        'Construyendo nuevas etapas',
        'El equipo está implementando las partes previstas en el plan.',
        'Revisar cada entrega antes de considerarla aprobada.',
        none);
  }
}
