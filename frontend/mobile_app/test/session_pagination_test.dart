import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';

Map<String, dynamic> card(String id, {String revision = 'v1', bool archived = false}) => {
  'id': id, 'title': 'Chat $id', 'workspace_path': '/work', 'workspace_name': 'Work',
  'created_at': '2026-10-18T00:00:00Z', 'updated_at': '2026-10-18T00:00:00Z',
  'archived_at': archived ? '2026-10-18T00:00:00Z' : null,
  'revision': revision, 'has_full_agent_configuration': false,
};
http.Response response(Object value) => http.Response(jsonEncode(value), 200,
  headers: {'content-type': 'application/json; charset=utf-8'});

void main() {
  test('running chat stays observable while browsing archived history', () async {
    var closed = false;
    final api = ApiClient(baseUrl:'http://bridge',client:MockClient((request) async {
      if (request.url.path == '/sessions/cards') {
        expect(jsonDecode(request.body)['ids'], ['running']);
        return response({'items': [card('running')..['active_agent_run_id'] = closed ? null : 'run-1']});
      }
      if (request.url.path == '/sessions/changes') return response({'items': [], 'removed_ids': []});
      return response({'items': [card('archived', archived:true)], 'next_cursor': null});
    }));
    api.trackSessionCards({'running'});
    api.setSessionFilter(archived:true);
    expect((await api.listSessions()).map((c)=>c.id), ['archived']);
    expect(api.activityCard('running')?.activeAgentRunId, 'run-1');
    closed = true;
    await api.listSessions();
    expect(api.activityCard('running')?.activeAgentRunId, isNull);
  });

  test('first page, load more, conditional refresh and archived removal', () async {
    var step = 0;
    final api = ApiClient(baseUrl: 'http://bridge', client: MockClient((r) async {
      switch (++step) {
        case 1:
          expect(r.url.path, '/sessions/page'); expect(r.url.queryParameters['limit'], '40');
          expect(r.url.queryParameters['archived'], 'false');
          return response({'items': [card('a')], 'next_cursor': 'cursor-a'});
        case 2:
          expect(r.url.queryParameters['before'], 'cursor-a');
          return response({'items': [card('b')], 'next_cursor': null});
        case 3:
          expect(r.method, 'POST'); expect(r.url.path, '/sessions/changes');
          expect(jsonDecode(r.body)['known'], {'a':'v1','b':'v1'});
          return response({'items': [card('a',revision:'v2')], 'removed_ids':['b']});
        default:
          expect(r.url.path, '/sessions/page'); expect(r.url.queryParameters['archived'], 'true');
          expect(r.url.queryParameters['search'], 'older');
          return response({'items': [card('c',archived:true)], 'next_cursor': null});
      }
    }));
    expect((await api.listSessions()).map((c)=>c.id), ['a']); expect(api.hasMoreSessions,isTrue);
    expect((await api.loadMoreSessions()).map((c)=>c.id), ['a','b']); expect(api.hasMoreSessions,isFalse);
    expect((await api.listSessions()).map((c)=>c.id), ['a']);
    api.setSessionFilter(archived:true,search:'older');
    expect((await api.listSessions()).map((c)=>c.id), ['c']);
  });
  test('out of order filter response cannot replace current history', () async {
    final old = Completer<http.Response>(); var calls = 0;
    final api = ApiClient(baseUrl:'http://bridge',client:MockClient((r) async {
      if (++calls == 1) return old.future;
      return response({'items':[card('archive',archived:true)],'next_cursor':null});
    }));
    final controller=ChatController(apiClient:api); addTearDown(controller.dispose);
    final first=controller.refreshSessions(); await Future<void>.delayed(Duration.zero);
    final filtered=controller.filterSessions(archived:true);
    old.complete(response({'items':[card('stale')],'next_cursor':'stale-cursor'}));
    await first; await filtered;
    expect(controller.sessions.map((c)=>c.id),['archive']);
    expect(controller.hasMoreSessions,isFalse);
  });
  test('failed page retains cursor and loaded history for retry', () async {
    var calls=0;
    final api=ApiClient(baseUrl:'http://bridge',client:MockClient((r) async {
      if (++calls==1) return response({'items':[card('a')],'next_cursor':'next'});
      if (calls==2) return http.Response('Unavailable',503);
      expect(r.url.queryParameters['before'],'next');
      return response({'items':[card('b')],'next_cursor':null});
    }));
    await api.listSessions();
    await expectLater(api.loadMoreSessions(),throwsException);
    expect(api.hasMoreSessions,isTrue);
    expect((await api.loadMoreSessions()).map((c)=>c.id),['a','b']);
  });
  test('fallback supports a backend not yet activated', () async {
    final api=ApiClient(baseUrl:'http://bridge',client:MockClient((r) async {
      if(r.url.path=='/sessions/page') return http.Response('Not found',404);
      expect(r.url.path,'/sessions');
      return response([card('active'),card('archive',archived:true)]);
    }));
    expect((await api.listSessions()).map((c)=>c.id),['active']);
    api.setSessionFilter(archived:true);
    expect((await api.listSessions()).map((c)=>c.id),['archive']);
  });
}
