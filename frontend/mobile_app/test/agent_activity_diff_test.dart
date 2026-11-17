import 'package:codex_mobile_frontend/src/models/agent_activity.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_activity_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('detects diffs and counts changed lines', () {
    const diff = '--- /repo/a.py (update)\n@@ -1 +1 @@\n-old\n+new\n+more';
    expect(looksLikeDiff(diff), isTrue);
    expect(diffStats(diff), (2, 1));
    expect(looksLikeDiff('ls -la\nfile-a\nfile-b'), isFalse);
  });

  test('Claude Edit input becomes a diff with a readable title', () {
    final out = normalizeAgentActivities(const [
      AgentActivity(
        id: 'e1',
        kind: 'tool',
        title: 'Edit',
        status: 'completed',
        detail: '{"file_path": "/repo/a.py", "old_string": "x = 1", "new_string": "x = 2"}',
      ),
    ]);
    expect(out.single.title, 'Edit · /repo/a.py');
    expect(out.single.detail, startsWith('--- /repo/a.py (update)\n@@\n-x = 1\n+x = 2'));
  });

  testWidgets('file change rows show +/- stats and a colored diff', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: AgentActivityTimeline(
            isRunning: true,
            activities: <AgentActivity>[
              AgentActivity(
                id: 'f1',
                kind: 'tool',
                title: 'Cambios en 1 archivo: a.py',
                status: 'completed',
                detail: '--- /repo/a.py (update)\n@@ -1 +1 @@\n-old\n+new',
              ),
            ],
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(find.text('+1'), findsOneWidget);
    expect(find.text('−1'), findsOneWidget);
    await tester.tap(find.text('Cambios en 1 archivo: a.py'));
    await tester.pump();
    expect(find.text('+new'), findsOneWidget);
    expect(find.text('-old'), findsOneWidget);
  });
}
