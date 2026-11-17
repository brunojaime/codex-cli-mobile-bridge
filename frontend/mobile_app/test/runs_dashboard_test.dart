import 'package:codex_mobile_frontend/src/models/run_overview.dart';
import 'package:codex_mobile_frontend/src/models/slash_command.dart';
import 'package:codex_mobile_frontend/src/services/run_alerts.dart';
import 'package:codex_mobile_frontend/src/state/runs_monitor.dart';
import 'package:codex_mobile_frontend/src/widgets/interaction_card.dart';
import 'package:codex_mobile_frontend/src/widgets/runs_dashboard.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeAlerts implements RunAlerts {
  final notified = <String>[];
  int attention = 0;
  @override
  bool get supported => true;
  @override
  String get permission => 'granted';
  @override
  bool enabled = true;
  @override
  bool userAway = true;
  @override
  Future<String> requestPermission() async => 'granted';
  @override
  void notify({required String title, required String body, required String tag, void Function()? onClick}) =>
      notified.add(title);
  @override
  void setAttentionCount(int count) => attention = count;
}

Map<String, dynamic> _run(String id, String state, {List<Map<String, dynamic>> pending = const []}) => {
      'job_id': id,
      'session_id': 's-$id',
      'session_title': 'Chat $id',
      'workspace_name': 'app',
      'engine': 'claude',
      'state': state,
      'request': 'Arreglá el login',
      'headline': state == 'done' ? 'Listo, quedó andando' : 'Ejecutando npm test',
      'output': '',
      'pending': pending,
      'steps': 3,
      'failed_steps': 0,
      'files_changed': 1,
      'elapsed_seconds': 65,
      'updated_at': DateTime.now().toIso8601String(),
    };

final _permission = <String, dynamic>{
  'request_id': 'r1',
  'kind': 'permission',
  'title': 'Claude pide permiso para usar Bash',
  'detail': r'$ rm -rf build',
  'tool_name': 'Bash',
  'input': {'command': 'rm -rf build'},
  'suggestions': [{'type': 'addRules'}],
};

void main() {
  testWidgets('dashboard groups runs into needs-you, working and finished', (tester) async {
    final monitor = RunsMonitor(alerts: _FakeAlerts());
    monitor.debugApply(RunsOverview.fromJson({
      'runs': [
        _run('a', 'needs_you', pending: [_permission]),
        _run('b', 'working'),
        _run('c', 'done'),
      ],
    }));
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    RunCard? opened;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: RunsDashboard(
          monitor: monitor,
          onOpenRun: (run) => opened = run,
          onStopRun: (_) async {},
          onNewTask: () {},
        ),
      ),
    ));
    expect(find.text('Un agente espera tu respuesta'), findsOneWidget);
    expect(find.text('Te necesita'), findsOneWidget);
    expect(find.text('Trabajando ahora'), findsOneWidget);
    expect(find.text('Terminado'), findsOneWidget);
    expect(find.text('Quiere ejecutar este comando'), findsOneWidget);
    expect(find.text('Permitir siempre'), findsOneWidget);
    expect(find.text('Ejecutando npm test'), findsWidgets);
    expect(find.text('1:05'), findsWidgets);
    await tester.tap(find.text('Listo, quedó andando'));
    expect(opened?.jobId, 'c');
    monitor.dispose();
  });

  test('alerts fire once for new requests and for finished runs, not on first load', () {
    final alerts = _FakeAlerts();
    final monitor = RunsMonitor(alerts: alerts);
    monitor.debugApply(RunsOverview.fromJson({'runs': [_run('a', 'working')]}));
    expect(alerts.notified, isEmpty);
    monitor.debugApply(RunsOverview.fromJson({'runs': [_run('a', 'needs_you', pending: [_permission])]}));
    monitor.debugApply(RunsOverview.fromJson({'runs': [_run('a', 'needs_you', pending: [_permission])]}));
    expect(alerts.notified, ['Claude necesita permiso']);
    expect(alerts.attention, 1);
    monitor.debugApply(RunsOverview.fromJson({'runs': [_run('a', 'done')]}));
    expect(alerts.notified.last, 'Terminó: Chat a');
    expect(alerts.attention, 0);
    monitor.dispose();
  });

  testWidgets('interaction card maps CLI choices to decisions', (tester) async {
    final decisions = <Map<String, Object?>>[];
    Future<bool> decide(InteractionDecision d) async {
      decisions.add(d.toJson());
      return true;
    }

    Future<void> pump(Map<String, dynamic> json) => tester.pumpWidget(MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: InteractionCard(
                key: UniqueKey(),
                interaction: PendingInteraction.fromJson(json),
                onDecide: decide,
              ),
            ),
          ),
        ));

    await pump(_permission);
    await tester.tap(find.text('Permitir siempre'));
    await tester.pump();
    expect(decisions.last, {'action': 'allow_always'});
    await tester.tap(find.text('Rechazar…'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'usá git clean');
    await tester.tap(find.text('Rechazar'));
    await tester.pump();
    expect(decisions.last, {'action': 'deny', 'message': 'usá git clean'});

    await pump({
      'request_id': 'q',
      'kind': 'question',
      'title': 'Color?',
      'detail': '',
      'input': {
        'questions': [
          {'question': 'Color?', 'header': 'Color', 'multiSelect': false, 'options': [{'label': 'Rojo'}, {'label': 'Azul'}]},
        ],
      },
    });
    await tester.tap(find.text('Azul'));
    await tester.pump();
    await tester.tap(find.text('Responder'));
    await tester.pump();
    expect(decisions.last, {'action': 'allow', 'answers': {'Color?': 'Azul'}});

    await pump({'request_id': 'p', 'kind': 'plan', 'title': 'Plan', 'detail': '', 'input': {'plan': '1. Hacer x'}});
    await tester.tap(find.text('Aprobar'));
    await tester.pump();
    expect(decisions.last, {'action': 'allow', 'mode': 'acceptEdits'});
  });

  test('new CLI-parity commands are callbacks', () {
    final commands = buildSlashCommands(const SlashCommandContext());
    for (final id in ['status', 'permissions', 'agents', 'compact']) {
      final command = commands.firstWhere((c) => c.id == id);
      expect(command.actionKind, SlashCommandActionKind.callback, reason: id);
    }
    expect(filterSlashCommands(commands, 'subagent').first.id, 'agents');
  });
}
