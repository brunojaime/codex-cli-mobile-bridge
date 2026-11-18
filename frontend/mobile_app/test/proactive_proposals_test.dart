import 'package:codex_mobile_frontend/src/state/proactive_mock_controller.dart';
import 'package:codex_mobile_frontend/src/widgets/proactive_proposals.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('starts silent and persists observations, read state and decision',
      () async {
    final controller = ProactiveMockController();
    await controller.load();
    expect(controller.hasProposal, isFalse);
    expect(controller.unread, isFalse);
    await controller.simulateArrival();
    expect(controller.unread, isTrue);
    expect(await controller.saveObservations('  '), isFalse);
    await controller.saveObservations(' Primero acotar el alcance. ');
    expect(controller.unread, isFalse);
    expect(controller.status, 'Con observaciones');
    await controller.respond(MockProposalDecision.execute);
    expect(await controller.respond(MockProposalDecision.reject), isFalse);
    controller.dispose();

    final restored = ProactiveMockController();
    await restored.load();
    expect(restored.decision, MockProposalDecision.execute);
    expect(restored.observations, 'Primero acotar el alcance.');
    expect(restored.unread, isFalse);
    await restored.simulateArrival();
    expect(restored.observations, isEmpty);
    await restored.respond(MockProposalDecision.reject);
    expect(restored.status, 'Rechazada');
    restored.dispose();
  });

  test('invalid saved data reports an error and can be replaced explicitly',
      () async {
    SharedPreferences.setMockInitialValues({
      ProactiveMockController.storageKey: '{invalid',
    });
    final controller = ProactiveMockController();
    await controller.load();
    expect(controller.error, isNotNull);
    await controller.simulateArrival();
    expect(controller.error, isNull);
    expect(controller.hasProposal, isTrue);
    controller.dispose();
  });

  testWidgets(
      'notification opens proposal, observations validate and execute is simulated',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = ProactiveMockController();
    await controller.load();
    await tester.pumpWidget(MaterialApp(
      home: ProactiveProposalsScreen(controller: controller),
    ));
    expect(find.text('No hay propuestas nuevas'), findsOneWidget);
    expect(find.textContaining('Nueva propuesta ·'), findsNothing);
    await tester
        .tap(find.byKey(const ValueKey('simulate-proactive-notification')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Nueva propuesta ·'), findsOneWidget);
    expect(controller.unread, isTrue);
    await tester.tap(find.text('Abrir'));
    await tester.pumpAndSettle();
    expect(controller.unread, isFalse);
    expect(find.text('Ejecutar'), findsOneWidget);
    expect(find.text('Rechazar'), findsOneWidget);
    await tester.tap(find.text('Observaciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Guardar observaciones'));
    await tester.pumpAndSettle();
    expect(
        find.text('Escribí una observación antes de guardar.'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Primero una sola tanda.');
    await tester.tap(find.text('Guardar observaciones'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(controller.observations, 'Primero una sola tanda.');
    await tester.tap(find.text('Ejecutar'));
    await tester.pumpAndSettle();
    expect(controller.decision, MockProposalDecision.execute);
    expect(find.text('Ejecutar'), findsNothing);
    expect(find.text('Ejecución simulada'), findsWidgets);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets('bell shows unread badge and rejection survives reopening',
      (tester) async {
    final seed = ProactiveMockController();
    await seed.load();
    await seed.simulateArrival();
    seed.dispose();
    await tester.pumpWidget(MaterialApp(
      home:
          Scaffold(appBar: AppBar(actions: const [ProactiveProposalsButton()])),
    ));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Propuestas del agente: 1 nueva'), findsOneWidget);
    await tester.tap(find.byTooltip('Propuestas del agente: 1 nueva'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('proactive-proposal-card')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rechazar'));
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Rechazada'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byTooltip('Propuestas del agente'), findsOneWidget);
  });

  for (final size in [
    const Size(360, 800),
    const Size(430, 932),
    const Size(768, 1024),
    const Size(1440, 900),
    const Size(640, 360),
  ]) {
    testWidgets('proposal and observations fit $size with larger text',
        (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final controller = ProactiveMockController();
      await controller.load();
      await controller.simulateArrival();
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: const TextScaler.linear(1.3)),
          child: child!,
        ),
        home: ProactiveProposalDetail(controller: controller),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Observaciones'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.enterText(
          find.byType(TextField), 'Observación larga. ' * 50);
      await tester.tap(find.text('Guardar observaciones'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    });
  }
}
