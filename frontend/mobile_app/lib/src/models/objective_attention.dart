class ObjectiveAttention {
  const ObjectiveAttention(
      this.title, this.explanation, this.suggestion, this.needsDecision);
  final String title, explanation, suggestion;
  final bool needsDecision;
  factory ObjectiveAttention.fromData(Map<String, dynamic> data) {
    final blocker = data['blocker'] as Map? ?? {};
    final reason = '${blocker['reason'] ?? ''}';
    if (reason.contains('Recovery budget exhausted')) {
      return const ObjectiveAttention(
          'La recuperación necesita un nuevo plan',
          'El equipo llegó al límite de intentos para resolver un problema. No es una autorización externa pendiente.',
          'Pedir al agente que revise lo que falló y proponga una estrategia distinta para continuar.',
          true);
    }
    if (data['status'] == 'budget_exhausted') {
      return const ObjectiveAttention(
          'Se alcanzó el límite de ejecución',
          'El trabajo se conserva, pero no se iniciarán más tareas con el límite actual.',
          'Revisar el avance y el coste antes de decidir si ampliar el límite.',
          true);
    }
    if (reason.isNotEmpty) {
      return ObjectiveAttention(
          'Hay un impedimento registrado',
          reason,
          '${blocker['next_action'] ?? ''}'.isNotEmpty
              ? '${blocker['next_action']}'
              : 'Pedir un diagnóstico antes de decidir cómo continuar.',
          true);
    }
    if (data['status'] == 'needs_attention' || data['status'] == 'blocked') {
      return const ObjectiveAttention(
          'La ejecución necesita revisión',
          'El coordinador no está continuando normalmente. Falta determinar o resolver el motivo.',
          'Pedir al agente que diagnostique el estado y resuelva lo que esté dentro del alcance autorizado.',
          true);
    }
    return const ObjectiveAttention(
        'Correcciones a cargo del equipo',
        'Los hallazgos de revisión no son necesariamente decisiones tuyas.',
        'El equipo debe corregir y volver a verificar. Podés enviar una indicación si necesitás cambiar el rumbo.',
        false);
  }
  static String request(Map<String, dynamic> data, String decision) {
    final blocker = data['blocker'] as Map? ?? {};
    return 'Atender la ejecución por objetivos ${data['id']} del proyecto ${data['project']}. '
        'Mi indicación: $decision\n'
        'Estado observado (revalidar antes de actuar): ${data['status']}. '
        'Motivo: ${blocker['reason'] ?? 'consultar estado y hallazgos actuales'}.\n'
        'Leé la entrada de coordinación Nienfos y el estado canónico de esa ejecución. '
        'No crees otra ejecución ni lances equipos duplicados. Si ya retomó y no hay un impedimento vigente, informá el estado sin reiniciarlo. '
        'Diagnosticá antes de cambiar nada; resolvé los problemas internos reversibles autorizados, preservando trabajo, pruebas y hallazgos. '
        'No reinicies desde cero ni aceptes tareas sin revisión. No aumentes presupuestos ni otorgues permisos externos sin una decisión explícita. '
        'Si requiere una decisión mía, explicá opciones y consecuencias. Informá qué cambió y verificá si hay trabajo activo; no afirmes que retomó sólo por cambiar un estado.';
  }
}
