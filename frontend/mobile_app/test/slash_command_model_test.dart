import 'package:codex_mobile_frontend/src/models/slash_command.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('slash query only matches intentional command token', () {
    expect(
      slashQueryForComposerText('/sta', selectionValid: true),
      'sta',
    );
    expect(
      slashQueryForComposerText('please review /tmp/file',
          selectionValid: true),
      isNull,
    );
    expect(
      slashQueryForComposerText('/review current diff', selectionValid: true),
      isNull,
    );
    expect(
      slashQueryForComposerText('/status', selectionValid: false),
      isNull,
    );
  });

  test('registry filters commands by slash title and description', () {
    final commands = buildSlashCommands(const SlashCommandContext());

    expect(
      filterSlashCommands(commands, 'sta').map((command) => command.id),
      contains('status'),
    );
    expect(
      filterSlashCommands(commands, 'feedback').map((command) => command.id),
      contains('feedback'),
    );
    expect(
      filterSlashCommands(commands, 'not-a-command'),
      isEmpty,
    );
  });

  test('context providers expose project commands only during project intake',
      () {
    final normal = buildSlashCommands(const SlashCommandContext());
    final project = buildSlashCommands(
      const SlashCommandContext(isProjectFactoryIntake: true),
    );

    expect(
        normal.map((command) => command.id), isNot(contains('project-build')));
    expect(project.map((command) => command.id), contains('project-build'));
  });

  test('backend guarded panel commands expose disabled reasons', () {
    final commands = buildSlashCommands(
      const SlashCommandContext(
        hasActiveBackend: false,
        workbenchAvailable: false,
        appsAvailable: false,
      ),
    );
    final apps = commands.singleWhere((command) => command.id == 'apps');
    final workbench =
        commands.singleWhere((command) => command.id == 'workbench');

    expect(apps.isEnabled, isFalse);
    expect(apps.disabledReason, 'No active bridge server.');
    expect(workbench.isEnabled, isFalse);
    expect(workbench.disabledReason, 'No active bridge server.');
  });
}
