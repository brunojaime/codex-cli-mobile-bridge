enum SlashCommandActionKind {
  insertText,
  sendMessage,
  openPanel,
  route,
  backend,
  callback,
  disabled,
}

class SlashCommand {
  const SlashCommand({
    required this.id,
    required this.slash,
    required this.title,
    required this.description,
    required this.scope,
    required this.actionKind,
    this.payload = '',
    this.disabledReason,
  });

  final String id;
  final String slash;
  final String title;
  final String description;
  final String scope;
  final SlashCommandActionKind actionKind;
  final String payload;
  final String? disabledReason;

  bool get isEnabled =>
      disabledReason == null && actionKind != SlashCommandActionKind.disabled;

  bool matches(String query) {
    final normalized = query.toLowerCase();
    return slash.toLowerCase().contains(normalized) ||
        title.toLowerCase().contains(normalized) ||
        description.toLowerCase().contains(normalized);
  }
}

class SlashCommandContext {
  const SlashCommandContext({
    this.isProjectFactoryIntake = false,
    this.hasActiveBackend = true,
    this.workbenchAvailable = true,
    this.appsAvailable = true,
  });

  final bool isProjectFactoryIntake;
  final bool hasActiveBackend;
  final bool workbenchAvailable;
  final bool appsAvailable;
}

abstract class SlashCommandProvider {
  const SlashCommandProvider();

  Iterable<SlashCommand> commands(SlashCommandContext context);
}

class GlobalSlashCommandProvider extends SlashCommandProvider {
  const GlobalSlashCommandProvider();

  @override
  Iterable<SlashCommand> commands(SlashCommandContext context) {
    final backendDisabledReason =
        context.hasActiveBackend ? null : 'No active bridge server.';
    return <SlashCommand>[
      const SlashCommand(
        id: 'new-project',
        slash: '/new-project',
        title: 'New Project',
        description: 'Open or resume guided New Project intake.',
        scope: 'global',
        actionKind: SlashCommandActionKind.callback,
      ),
      const SlashCommand(
        id: 'status',
        slash: '/status',
        title: 'Status',
        description: 'Ask for session, backend, workspace, and run status.',
        scope: 'global',
        actionKind: SlashCommandActionKind.sendMessage,
        payload: 'Show current session, backend, workspace, and run status.',
      ),
      const SlashCommand(
        id: 'review',
        slash: '/review',
        title: 'Review',
        description: 'Request a focused review of the current workspace.',
        scope: 'workspace',
        actionKind: SlashCommandActionKind.sendMessage,
        payload:
            'Review the current workspace changes and call out bugs, risks, and missing tests.',
      ),
      const SlashCommand(
        id: 'feedback',
        slash: '/feedback',
        title: 'Feedback',
        description: 'Stage a feedback note in the composer.',
        scope: 'global',
        actionKind: SlashCommandActionKind.insertText,
        payload: 'Feedback: ',
      ),
      const SlashCommand(
        id: 'compact',
        slash: '/compact',
        title: 'Compact',
        description: 'Ask for a compact conversation summary.',
        scope: 'session',
        actionKind: SlashCommandActionKind.sendMessage,
        payload:
            'Compact this conversation into a concise summary with current decisions and next steps.',
      ),
      const SlashCommand(
        id: 'diff',
        slash: '/diff',
        title: 'Diff',
        description: 'Ask for current workspace changes.',
        scope: 'workspace',
        actionKind: SlashCommandActionKind.sendMessage,
        payload:
            'Show the current workspace diff and summarize the changed files.',
      ),
      SlashCommand(
        id: 'workbench',
        slash: '/workbench',
        title: 'Workbench',
        description: 'Open SDD Workbench tools when supported by the backend.',
        scope: 'workbench',
        actionKind: context.workbenchAvailable
            ? SlashCommandActionKind.openPanel
            : SlashCommandActionKind.disabled,
        payload: 'workbench',
        disabledReason:
            context.workbenchAvailable ? null : backendDisabledReason,
      ),
      SlashCommand(
        id: 'apps',
        slash: '/apps',
        title: 'Apps',
        description: 'Open installable apps when available.',
        scope: 'global',
        actionKind: context.appsAvailable
            ? SlashCommandActionKind.openPanel
            : SlashCommandActionKind.disabled,
        payload: 'apps',
        disabledReason: context.appsAvailable ? null : backendDisabledReason,
      ),
      const SlashCommand(
        id: 'plan',
        slash: '/plan',
        title: 'Plan',
        description: 'Planning mode is not exposed in this mobile build.',
        scope: 'global',
        actionKind: SlashCommandActionKind.disabled,
        disabledReason: 'Planning mode is unavailable in this build.',
      ),
      const SlashCommand(
        id: 'goal',
        slash: '/goal',
        title: 'Goal',
        description: 'Persistent goals are not exposed in this mobile build.',
        scope: 'global',
        actionKind: SlashCommandActionKind.disabled,
        disabledReason: 'Goal management is unavailable in this build.',
      ),
      const SlashCommand(
        id: 'model',
        slash: '/model',
        title: 'Model',
        description: 'Model selection is not exposed in this composer.',
        scope: 'global',
        actionKind: SlashCommandActionKind.disabled,
        disabledReason: 'Model selection is unavailable in this composer.',
      ),
      const SlashCommand(
        id: 'permissions',
        slash: '/permissions',
        title: 'Permissions',
        description: 'Permission state is not exposed by this backend.',
        scope: 'global',
        actionKind: SlashCommandActionKind.disabled,
        disabledReason: 'Permission metadata is unavailable from this backend.',
      ),
    ];
  }
}

class NewProjectSlashCommandProvider extends SlashCommandProvider {
  const NewProjectSlashCommandProvider();

  @override
  Iterable<SlashCommand> commands(SlashCommandContext context) {
    if (!context.isProjectFactoryIntake) {
      return const <SlashCommand>[];
    }
    return const <SlashCommand>[
      SlashCommand(
        id: 'project-contract',
        slash: '/project-contract',
        title: 'Project Contract',
        description: 'Ask for the current New Project contract preview.',
        scope: 'new_project',
        actionKind: SlashCommandActionKind.sendMessage,
        payload:
            'Show the current New Project contract preview with assumptions, blockers, assets, release plan, Workbench/SDD, web preview, and Android plan.',
      ),
      SlashCommand(
        id: 'project-build',
        slash: '/project-build',
        title: 'Project Build',
        description: 'Confirm build only after the contract is ready.',
        scope: 'new_project',
        actionKind: SlashCommandActionKind.insertText,
        payload: 'Confirm the project contract and start the build.',
      ),
    ];
  }
}

const List<SlashCommandProvider> defaultSlashCommandProviders =
    <SlashCommandProvider>[
  GlobalSlashCommandProvider(),
  NewProjectSlashCommandProvider(),
];

List<SlashCommand> buildSlashCommands(
  SlashCommandContext context, {
  List<SlashCommandProvider> providers = defaultSlashCommandProviders,
}) {
  return providers
      .expand((provider) => provider.commands(context))
      .toList(growable: false);
}

List<SlashCommand> filterSlashCommands(
  Iterable<SlashCommand> commands,
  String query,
) {
  final normalized = query.trim();
  return commands
      .where((command) => normalized.isEmpty || command.matches(normalized))
      .toList(growable: false);
}

String? slashQueryForComposerText(String text, {required bool selectionValid}) {
  if (!selectionValid ||
      !text.startsWith('/') ||
      text.contains(RegExp(r'\s'))) {
    return null;
  }
  return text.substring(1).trim();
}
