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
    expect(
        project.map((command) => command.id), isNot(contains('project-build')));
    expect(project.map((command) => command.id), contains('project-contract'));
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

  test('dev handoff command is exposed only for enabled prod backends', () {
    final prod = buildSlashCommands(
      const SlashCommandContext(
        bridgeEnvironment: 'prod',
        isProdEnvironment: true,
        devHandoffAvailable: true,
      ),
    ).singleWhere((command) => command.id == 'dev-handoff');
    final prodDisabled = buildSlashCommands(
      const SlashCommandContext(
        bridgeEnvironment: 'prod',
        isProdEnvironment: true,
      ),
    ).singleWhere((command) => command.id == 'dev-handoff');
    final dev = buildSlashCommands(
      const SlashCommandContext(
        bridgeEnvironment: 'dev',
        devHandoffAvailable: true,
      ),
    ).singleWhere((command) => command.id == 'dev-handoff');
    final unknown = buildSlashCommands(
      const SlashCommandContext(),
    ).singleWhere((command) => command.id == 'dev-handoff');
    final legacyProdFallback = buildSlashCommands(
      const SlashCommandContext(
        isProdEnvironment: true,
        devHandoffAvailable: true,
      ),
    ).singleWhere((command) => command.id == 'dev-handoff');

    expect(prod.isEnabled, isTrue);
    expect(prod.actionKind, SlashCommandActionKind.callback);
    expect(prodDisabled.isEnabled, isFalse);
    expect(
      prodDisabled.disabledReason,
      'PROD to DEV handoff is disabled by this backend.',
    );
    expect(dev.isEnabled, isFalse);
    expect(dev.disabledReason, 'DEV handoff is only available from PROD.');
    expect(unknown.isEnabled, isFalse);
    expect(
      unknown.disabledReason,
      'Bridge environment identity is unavailable from this backend.',
    );
    expect(legacyProdFallback.isEnabled, isFalse);
    expect(
      legacyProdFallback.disabledReason,
      'Bridge environment identity is unavailable from this backend.',
    );
  });

  test('dev handoff command matches hyphen and underscore aliases', () {
    final commands = buildSlashCommands(
      const SlashCommandContext(
        bridgeEnvironment: 'prod',
        devHandoffAvailable: true,
      ),
    );

    expect(
      filterSlashCommands(commands, 'dev-handoff').map((command) => command.id),
      contains('dev-handoff'),
    );
    expect(
      filterSlashCommands(commands, 'dev_handoff').map((command) => command.id),
      contains('dev-handoff'),
    );
  });

  test('ux commands expose generator-only and full loop callbacks', () {
    final commands = buildSlashCommands(const SlashCommandContext());
    final ux = commands.singleWhere((command) => command.id == 'ux');
    final uxFull = commands.singleWhere((command) => command.id == 'ux-full');

    expect(ux.slash, '/ux');
    expect(ux.actionKind, SlashCommandActionKind.callback);
    expect(ux.payload, 'generator');
    expect(uxFull.slash, '/ux-full');
    expect(uxFull.actionKind, SlashCommandActionKind.callback);
    expect(uxFull.payload, 'full');
    expect(
      filterSlashCommands(commands, 'ux_full').map((command) => command.id),
      contains('ux-full'),
    );
  });

  test('ux full is disabled without a project workspace', () {
    final commands = buildSlashCommands(
      const SlashCommandContext(hasProjectWorkspace: false),
    );
    final uxFull = commands.singleWhere((command) => command.id == 'ux-full');

    expect(uxFull.isEnabled, isFalse);
    expect(
      uxFull.disabledReason,
      'Choose a project chat with a workspace before starting UX Full.',
    );
  });
}
