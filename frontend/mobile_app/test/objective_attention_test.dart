import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/models/objective_attention.dart';

void main() {
  test('internal recovery limit is not an external authorization', () {
    final a = ObjectiveAttention.fromData({
      'status': 'needs_attention',
      'blocker': {'reason': 'Recovery budget exhausted'}
    });
    expect(a.needsDecision, true);
    expect(a.explanation, contains('No es una autorización externa'));
  });
  test('ordinary correction does not demand user action', () {
    final a = ObjectiveAttention.fromData({
      'status': 'executing',
      'issues': [
        {'status': 'open'}
      ]
    });
    expect(a.needsDecision, false);
  });
  test('unknown dependency preserves recorded next action', () {
    final a = ObjectiveAttention.fromData({
      'blocker': {
        'reason': 'Authorize provider',
        'next_action': 'Revalidate account'
      }
    });
    expect(a.explanation, 'Authorize provider');
    expect(a.suggestion, 'Revalidate account');
  });
  test('request retains execution and authorization limits', () {
    final m = ObjectiveAttention.request(
        {'id': 'a' * 24, 'project': 'Inventory', 'status': 'blocked'},
        'Explicame opciones');
    expect(m, contains('a' * 24));
    expect(m, contains('Explicame opciones'));
    expect(m, contains('No aumentes presupuestos'));
    expect(m, contains('revalidar antes de actuar'));
  });
}
