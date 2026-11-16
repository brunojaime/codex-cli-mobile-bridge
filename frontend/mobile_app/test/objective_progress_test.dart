import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/models/objective_progress.dart';

void main() {
  Map<String, dynamic> state() => {
        'status': 'executing',
        'active_agents': [
          {'role': 'generator', 'unit': 'access'}
        ],
        'presentation': {},
        'jobs': [],
        'issues': []
      };
  test('correction is team work, not a user request', () {
    final s = state()
      ..['issues'] = [
        {'unit': 'access', 'status': 'open'}
      ];
    final p = ObjectiveProgress.fromData(s);
    expect(p.title, 'Correcciones en curso');
    expect(p.action, 'Sin acción solicitada a vos');
    expect(
        ObjectiveProgress.activity(s, 'access'), 'Corrigiendo observaciones');
  });
  test(
      'historical acceptance distinguishes adjustment from first implementation',
      () {
    final s = state()
      ..['jobs'] = [
        {
          'unit': 'access',
          'role': 'reviewer',
          'status': 'completed',
          'verdict': 'pass'
        }
      ];
    expect(
        ObjectiveProgress.fromData(s).title, 'Ajustando una entrega revisada');
    expect(ObjectiveProgress.activity(s, 'access'),
        'Ajustando una entrega revisada');
  });
  test('idle executing is not claimed to be progressing', () {
    final s = state()..['active_agents'] = [];
    expect(ObjectiveProgress.fromData(s).title, 'Sin actividad registrada');
    expect(ObjectiveProgress.activity(s, 'access'), 'En espera');
  });
  test('recovery, paused and external dependency take precedence', () {
    final s = state()
      ..['active_agents'] = [
        {'role': 'recovery'}
      ];
    expect(ObjectiveProgress.fromData(s).title, 'Resolviendo un impedimento');
    s['status'] = 'paused';
    expect(ObjectiveProgress.fromData(s).title, 'Ejecución en pausa');
    s['blocker'] = {'reason': 'Provider authorization required'};
    expect(ObjectiveProgress.fromData(s).action, 'Revisá Atención');
  });
  test('completed code never promises deployed app', () {
    final s = state()..['status'] = 'completed';
    expect(ObjectiveProgress.fromData(s).summary, contains('no acredita'));
  });
  test('active review is distinct from corrective implementation', () {
    final s = state()
      ..['active_agents'] = [
        {'role': 'reviewer', 'unit': 'access'}
      ];
    expect(ObjectiveProgress.fromData(s).title, 'Verificando las entregas');
    expect(ObjectiveProgress.activity(s, 'access'), 'Verificando la entrega');
  });
}
