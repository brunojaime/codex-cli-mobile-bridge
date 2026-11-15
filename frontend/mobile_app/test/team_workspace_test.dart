import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
void main() {
 test('only coordinator workspaces are hidden; ordinary projects survive', () {
  expect(isTeamWorkspace('/Projects/nienfos-team-a7589470910bac071e0b2414-3-generator'), isTrue);
  expect(isTeamWorkspace('/Projects/nienfos-team-a7589470910bac071e0b2414-4-ux_review-scratch'), isTrue);
  expect(isTeamWorkspace('/Projects/nienfos-team-product'), isFalse);
  expect(isTeamWorkspace('/Projects/gim_app_20261115'), isFalse);
  expect(isTeamWorkspace(''), isFalse);
 });
}
