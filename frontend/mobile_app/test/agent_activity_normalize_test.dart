import 'package:codex_mobile_frontend/src/models/agent_activity.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_activity_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

AgentActivity _a(String id, String title,
        {String status = 'observed', String detail = '', String kind = 'status'}) =>
    AgentActivity(id: id, kind: kind, title: title, status: status, detail: detail);

void main() {
  test('groups MCP startup failures into one warning row', () {
    final out = normalizeAgentActivities([
      _a('1', 'Launching the local Codex subprocess.'),
      _a('2', 'memory failed to start: MCP client for `memory` failed to start: handshaking failed ...'),
      _a('3', 'tasks failed to start: MCP client for `tasks` failed to start: HTTP 404'),
    ]);
    expect(out.map((e) => e.title), [
      'Launching the local Codex subprocess.',
      '2 servidores MCP no iniciaron: memory, tasks',
    ]);
    expect(out.last.status, 'warning');
    expect(out.last.detail, contains('HTTP 404'));
  });

  test('groups MCP ready events and titles commands by their command line', () {
    final out = normalizeAgentActivities([
      _a('1', 'github is ready.'),
      _a('2', 'playwright is ready.'),
      _a('3', 'Comando', kind: 'tool', status: 'completed', detail: "/bin/bash -lc 'ls -la'"),
    ]);
    expect(out.map((e) => e.title), [
      'Herramientas listas: github, playwright',
      r'$ ls -la',
    ]);
  });

  test('moves very long titles into the detail', () {
    final long = 'Error: ${'x' * 300}';
    final out = normalizeAgentActivities([_a('1', long)]);
    expect(out.single.title.length, lessThan(160));
    expect(out.single.detail, contains(long));
  });

  test('tool JSON input becomes a readable title', () {
    final out = normalizeAgentActivities([
      _a('1', 'Bash',
          kind: 'tool',
          status: 'completed',
          detail: '{"command": "ls -la /tmp", "description": "List files"}\n\nfile-a\nfile-b'),
      _a('2', 'Read', kind: 'tool', detail: '{"file_path": "/repo/README.md"}'),
    ]);
    expect(out[0].title, r'$ ls -la /tmp');
    expect(out[0].detail, contains('List files'));
    expect(out[0].detail, contains('file-a'));
    expect(out[1].title, 'Read · /repo/README.md');
  });
}
