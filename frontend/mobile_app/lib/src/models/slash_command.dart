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
    this.aliases = const <String>[],
    this.payload = '',
    this.disabledReason,
  });

  final String id;
  final String slash;
  final String title;
  final String description;
  final String scope;
  final SlashCommandActionKind actionKind;
  final List<String> aliases;
  final String payload;
  final String? disabledReason;

  bool get isEnabled =>
      disabledReason == null && actionKind != SlashCommandActionKind.disabled;

  bool matches(String query) {
    final normalized = query.toLowerCase();
    return slash.toLowerCase().contains(normalized) ||
        aliases.any((alias) => alias.toLowerCase().contains(normalized)) ||
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
    this.hasProjectWorkspace = true,
    this.isProdEnvironment = false,
    this.bridgeEnvironment,
    this.devHandoffAvailable = false,
    this.skills = const <SlashSkill>[],
  });

  final bool isProjectFactoryIntake;
  final bool hasActiveBackend;
  final bool workbenchAvailable;
  final bool appsAvailable;
  final bool hasProjectWorkspace;
  final bool isProdEnvironment;
  final String? bridgeEnvironment;
  final bool devHandoffAvailable;
  final List<SlashSkill> skills;

  String? get normalizedBridgeEnvironment {
    final normalized = bridgeEnvironment?.trim().toLowerCase();
    return normalized == null || normalized.isEmpty ? null : normalized;
  }

  bool get hasKnownBridgeEnvironment => normalizedBridgeEnvironment != null;

  bool get isExplicitProdBridgeEnvironment =>
      normalizedBridgeEnvironment == 'prod';
}

class SlashSkill {
  const SlashSkill({
    required this.id,
    required this.name,
    this.description = '',
    this.selected = false,
  });

  final String id;
  final String name;
  final String description;
  final bool selected;
}

class SkillSlashCommandProvider extends SlashCommandProvider {
  const SkillSlashCommandProvider();

  @override
  Iterable<SlashCommand> commands(SlashCommandContext context) {
    return context.skills.where((skill) => skill.name.trim().isNotEmpty).map(
          (skill) => SlashCommand(
            id: 'skill:${skill.id}',
            slash: '/${skill.name.trim().replaceAll(RegExp(r'\s+'), '-')}',
            title: skill.selected ? 'Skill · activa' : 'Skill',
            description: skill.description.isEmpty
                ? 'Usar esta skill en el próximo mensaje.'
                : skill.description,
            scope: 'skill',
            actionKind: SlashCommandActionKind.callback,
          ),
        );
  }
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
    final handoffDisabledReason = !context.hasActiveBackend
        ? 'No active bridge server.'
        : !context.hasKnownBridgeEnvironment
            ? 'Bridge environment identity is unavailable from this backend.'
            : !context.isExplicitProdBridgeEnvironment
                ? 'DEV handoff is only available from PROD.'
                : 'PROD to DEV handoff is disabled by this backend.';
    final handoffEnabled =
        context.isExplicitProdBridgeEnvironment && context.devHandoffAvailable;
    final uxDisabledReason = !context.hasActiveBackend
        ? 'No active bridge server.'
        : !context.hasProjectWorkspace
            ? 'Choose a project chat with a workspace before starting UX.'
            : null;
    final uxFullDisabledReason = !context.hasActiveBackend
        ? 'No active bridge server.'
        : !context.hasProjectWorkspace
            ? 'Choose a project chat with a workspace before starting UX Full.'
            : null;
    return <SlashCommand>[
      SlashCommand(
          id: 'backlog',
          slash: '/backlog',
          title: 'Añadir al backlog',
          description:
              'Guardar un encargo para ejecutar al terminar el anterior.',
          scope: 'workspace',
          actionKind: SlashCommandActionKind.insertText,
          disabledReason: uxDisabledReason,
          payload: '/backlog '),
      SlashCommand(
        id: 'ejecutar',
        slash: '/ejecutar',
        title: 'Generator + Reviewer',
        description:
            'Preparar un pedido editable para otro chat. 25 turnos por agente por defecto.',
        scope: 'workspace',
        actionKind: SlashCommandActionKind.insertText,
        disabledReason: uxDisabledReason,
        payload:
            'Usá la skill generator-reviewer para arrancar esta tarea en un chat nuevo del mismo proyecto, '
            'con prompts adaptados y 25 turnos máximos para cada agente salvo que indique otros límites. '
            'Dejá un enlace para abrirlo cuando yo quiera. Tarea: ',
      ),
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
      SlashCommand(
        id: 'ux',
        slash: '/ux',
        aliases: const <String>['/ux-generator'],
        title: 'UX',
        description: 'Run a Senior UX generator pass on the current project.',
        scope: 'workspace',
        actionKind: uxDisabledReason == null
            ? SlashCommandActionKind.callback
            : SlashCommandActionKind.disabled,
        payload: 'generator',
        disabledReason: uxDisabledReason,
      ),
      SlashCommand(
        id: 'ux-full',
        slash: '/ux-full',
        aliases: const <String>['/ux-generator-reviewer', '/ux_full'],
        title: 'UX Full',
        description:
            'Run the Senior UX generator/reviewer loop with reviewer stop.',
        scope: 'workspace',
        actionKind: uxFullDisabledReason == null
            ? SlashCommandActionKind.callback
            : SlashCommandActionKind.disabled,
        payload: 'full',
        disabledReason: uxFullDisabledReason,
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
      SlashCommand(
        id: 'dev-handoff',
        slash: '/dev-handoff',
        aliases: const <String>['/dev_handoff'],
        title: 'DEV Handoff',
        description: 'Queue an explicit PROD to DEV handoff.',
        scope: 'global',
        actionKind: handoffEnabled
            ? SlashCommandActionKind.callback
            : SlashCommandActionKind.disabled,
        disabledReason: handoffEnabled ? null : handoffDisabledReason,
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
      SlashCommand(
        id: 'model',
        slash: '/model',
        title: 'Modelo',
        description: 'Ver y cambiar el modelo y el agente de este chat.',
        scope: 'global',
        actionKind: SlashCommandActionKind.callback,
        disabledReason: backendDisabledReason,
      ),
      SlashCommand(
        id: 'usage',
        slash: '/usage',
        title: 'Uso',
        description: 'Uso del plan, límites y cuándo se renuevan.',
        scope: 'global',
        aliases: const <String>['/cost', '/limits'],
        actionKind: SlashCommandActionKind.callback,
        disabledReason: backendDisabledReason,
      ),
      SlashCommand(
        id: 'new',
        slash: '/new',
        title: 'Nuevo chat',
        description: 'Empezar un chat nuevo eligiendo el proyecto.',
        scope: 'global',
        aliases: const <String>['/clear'],
        actionKind: SlashCommandActionKind.callback,
        disabledReason: backendDisabledReason,
      ),
      const SlashCommand(
        id: 'help',
        slash: '/help',
        title: 'Ayuda',
        description: 'Ver todos los comandos y atajos de teclado.',
        scope: 'global',
        actionKind: SlashCommandActionKind.callback,
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
    ];
  }
}

const List<SlashCommandProvider> defaultSlashCommandProviders =
    <SlashCommandProvider>[
  GlobalSlashCommandProvider(),
  NewProjectSlashCommandProvider(),
  SkillSlashCommandProvider(),
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
  final normalized = query.trim().toLowerCase().replaceFirst(RegExp(r'^/'), '');
  int score(SlashCommand command) {
    if (normalized.isEmpty) return 0;
    final slash = command.slash.toLowerCase().replaceFirst(RegExp(r'^/'), '');
    final aliases = command.aliases
        .map((alias) => alias.toLowerCase().replaceFirst(RegExp(r'^/'), ''));
    if (slash == normalized) return 0;
    if (slash.startsWith(normalized)) return 1;
    if (aliases.any((alias) => alias.startsWith(normalized))) return 2;
    if (slash.contains(normalized)) return 3;
    if (command.title.toLowerCase().startsWith(normalized)) return 4;
    if (command.matches(normalized)) return 5;
    return -1;
  }

  final ranked = <(int, int, SlashCommand)>[];
  var order = 0;
  for (final command in commands) {
    final value = score(command);
    if (value < 0) continue;
    // Enabled commands first inside each relevance bucket.
    ranked.add((value * 2 + (command.isEnabled ? 0 : 1), order++, command));
  }
  ranked.sort((a, b) => a.$1 != b.$1 ? a.$1.compareTo(b.$1) : a.$2.compareTo(b.$2));
  return ranked.map((entry) => entry.$3).toList(growable: false);
}

String? slashQueryForComposerText(String text, {required bool selectionValid}) {
  if (!selectionValid ||
      !text.startsWith('/') ||
      text.contains(RegExp(r'\s'))) {
    return null;
  }
  return text.substring(1).trim();
}
