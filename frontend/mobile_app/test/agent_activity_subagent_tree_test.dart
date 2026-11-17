import 'package:codex_mobile_frontend/src/models/agent_activity.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_activity_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('subagent steps are nested under their subagent node', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: AgentActivityTimeline(
            isRunning: true,
            activities: <AgentActivity>[
              AgentActivity(id: 'c1', kind: 'commentary', title: 'Voy a delegar', status: 'completed'),
              AgentActivity(
                id: 'toolu_1',
                kind: 'subagent',
                title: 'Revisar tests',
                status: 'running',
                detail: 'Corré los tests y resumí fallas',
              ),
              AgentActivity(
                id: 'toolu_2',
                kind: 'tool',
                title: 'Bash',
                status: 'completed',
                detail: 'pytest -q',
                parentId: 'toolu_1',
              ),
              AgentActivity(id: 'toolu_3', kind: 'tool', title: 'Read', status: 'completed'),
            ],
          ),
        ),
      ),
    ));
    await tester.pump();

    expect(find.textContaining('1 subagente'), findsOneWidget);
    expect(find.text('Revisar tests'), findsOneWidget);
    expect(find.textContaining('Subagente · Trabajando · 1 paso'), findsOneWidget);
    // Child step is visible inside the running subagent node.
    expect(find.text('Bash'), findsOneWidget);
    expect(find.text('Read'), findsOneWidget);

    await tester.tap(find.text('Ver encargo'));
    await tester.pump();
    expect(find.text('Corré los tests y resumí fallas'), findsOneWidget);

    // Collapsing the subagent hides its nested steps but keeps root steps.
    await tester.tap(find.text('Revisar tests'));
    await tester.pump();
    expect(find.text('Bash'), findsNothing);
    expect(find.text('Read'), findsOneWidget);
  });

  test('parent_id round-trips through json', () {
    final item = AgentActivity.fromJson(const <String, dynamic>{
      'id': 'a',
      'kind': 'tool',
      'title': 'Bash',
      'status': 'running',
      'parent_id': 'toolu_1',
    });
    expect(item.parentId, 'toolu_1');
    expect(item.toJson()['parent_id'], 'toolu_1');
  });
}
