import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/models/objective_brief.dart';
import 'package:codex_mobile_frontend/src/models/objective_progress.dart';

void main() {
  Map<String, dynamic> state() => {
        'status': 'executing',
        'jobs': [
          {'role': 'ux_review', 'unit': 'account', 'status': 'running'},
          {
            'role': 'security',
            'unit': 'account',
            'status': 'completed',
            'verdict': 'pass'
          }
        ],
        'issues': [
          {'unit': 'polish', 'status': 'open'}
        ],
        'units': [
          {
            'id': 'polish',
            'state': 'ready',
            'depends_on': ['account']
          }
        ],
        'presentation': {
          'tasks': [
            {'id': 'account', 'title': 'Inicio y cuenta'},
            {'id': 'polish', 'title': 'Mejorar la composición visual'}
          ]
        }
      };
  test('current review, queued correction, no claim of current approvals', () {
    final s = state();
    final b = ObjectiveBrief.fromData(s);
    expect(b.now, 'Estamos revisando: Inicio y cuenta.');
    expect(b.remaining, contains('diseño'));
    expect(b.remaining, isNot(contains('seguridad')));
    expect(b.next, contains('Mejorar la composición visual'));
    expect(b.next, contains('orden aún no está confirmado'));
    expect(ObjectiveProgress.fromData(s).title, 'Verificando las entregas');
  });
  test('parallel work is named without inventing a next step', () {
    final s = state();
    (s['jobs'] as List)
        .add({'role': 'generator', 'unit': 'billing', 'status': 'running'});
    (s['presentation']['tasks'] as List)
        .add({'id': 'billing', 'title': 'Cobros'});
    final b = ObjectiveBrief.fromData(s);
    expect(b.now, contains('Inicio y cuenta y Cobros'));
    expect(b.remaining, contains('revisión independiente'));
  });
  test('idle and blocked are not narrated as active work', () {
    final s = state()..['jobs'] = [];
    expect(ObjectiveBrief.fromData(s).now, contains('no muestra agentes'));
    s['blocker'] = {'reason': 'Authorization'};
    expect(ObjectiveBrief.fromData(s).action, contains('Revisá Atención'));
  });
}
