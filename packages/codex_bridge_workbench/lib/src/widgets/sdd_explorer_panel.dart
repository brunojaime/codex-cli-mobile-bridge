import 'package:flutter/material.dart';

import '../models/sdd_project.dart';
import '../models/sdd_submission_result.dart';
import '../services/mermaid_renderer.dart';
import '../services/sdd_explorer_client.dart';

typedef SddExplorerLoader = Future<SddProject?> Function(String bridgeUrl);
typedef SddFeedbackSubmitter =
    Future<SddFeedbackSubmissionResult> Function(
      String bridgeUrl,
      SddFeedbackDraft draft,
    );
typedef SddCodexActionSubmitter =
    Future<SddCodexActionSubmissionResult> Function(
      String bridgeUrl,
      SddCodexActionDraft draft,
    );

class SddFeedbackDraft {
  const SddFeedbackDraft({required this.comment, required this.target});

  final String comment;
  final SddFeedbackTarget target;
}

class SddFeedbackTarget {
  const SddFeedbackTarget({
    required this.workspacePath,
    required this.artifactType,
    required this.artifactPath,
    required this.artifactTitle,
    required this.sourceExcerpt,
    this.specId,
    this.specTitle,
    this.diagramType,
    this.diagramScope,
  });

  final String workspacePath;
  final String artifactType;
  final String artifactPath;
  final String artifactTitle;
  final String sourceExcerpt;
  final String? specId;
  final String? specTitle;
  final String? diagramType;
  final String? diagramScope;

  bool get isDiagram => diagramType != null;

  String get feedbackKind => isDiagram ? 'sdd.diagram' : 'sdd.artifact';

  Map<String, Object?> toContextMetadata() {
    return <String, Object?>{
      'sdd': <String, Object?>{
        'workspacePath': workspacePath,
        'artifactType': artifactType,
        'artifactPath': artifactPath,
        'artifactTitle': artifactTitle,
        if (specId != null) 'specId': specId,
        if (specTitle != null) 'specTitle': specTitle,
        if (diagramType != null) 'diagramType': diagramType,
        if (diagramScope != null) 'diagramScope': diagramScope,
        'sourceExcerpt': sourceExcerpt,
      },
    };
  }
}

enum SddCodexActionKind {
  refineSpec,
  updatePlan,
  updateTasks,
  reviewSlice,
  updateDiagram,
  explainDiagramImpact,
  alignDiagramWithSpec,
  addressFeedback,
  auditSdd,
}

extension SddCodexActionKindLabel on SddCodexActionKind {
  String get apiValue => switch (this) {
    SddCodexActionKind.refineSpec => 'sdd.refine_spec',
    SddCodexActionKind.updatePlan => 'sdd.update_plan',
    SddCodexActionKind.updateTasks => 'sdd.update_tasks',
    SddCodexActionKind.reviewSlice => 'sdd.review_slice',
    SddCodexActionKind.updateDiagram => 'sdd.update_diagram',
    SddCodexActionKind.explainDiagramImpact => 'sdd.explain_diagram_impact',
    SddCodexActionKind.alignDiagramWithSpec => 'sdd.align_diagram_with_spec',
    SddCodexActionKind.addressFeedback => 'sdd.address_feedback',
    SddCodexActionKind.auditSdd => 'sdd.audit',
  };

  String get label => switch (this) {
    SddCodexActionKind.refineSpec => 'Refine spec.md',
    SddCodexActionKind.updatePlan => 'Update plan.md',
    SddCodexActionKind.updateTasks => 'Update tasks.md',
    SddCodexActionKind.reviewSlice => 'Review slice doc',
    SddCodexActionKind.updateDiagram => 'Update .mmd',
    SddCodexActionKind.explainDiagramImpact => 'Explain impact',
    SddCodexActionKind.alignDiagramWithSpec => 'Align with spec/task',
    SddCodexActionKind.addressFeedback => 'Address feedback',
    SddCodexActionKind.auditSdd => 'Audit SDD',
  };

  String get instruction => switch (this) {
    SddCodexActionKind.refineSpec =>
      'Refine the referenced spec so requirements, acceptance criteria, and open questions are clearer.',
    SddCodexActionKind.updatePlan =>
      'Update the referenced implementation plan so it matches the current spec and architecture context.',
    SddCodexActionKind.updateTasks =>
      'Update the referenced tasks so they are actionable, ordered, and traceable to the spec.',
    SddCodexActionKind.reviewSlice =>
      'Review the referenced slice doc and identify concrete corrections or missing implementation details.',
    SddCodexActionKind.updateDiagram =>
      'Update the referenced Mermaid source so the diagram communicates the intended architecture more accurately.',
    SddCodexActionKind.explainDiagramImpact =>
      'Explain the architecture impact represented by this diagram and call out inconsistencies with the SDD.',
    SddCodexActionKind.alignDiagramWithSpec =>
      'Align the referenced diagram with the related spec, plan, tasks, and source context.',
    SddCodexActionKind.addressFeedback =>
      'Address the linked queued feedback using the referenced SDD artifact or diagram context.',
    SddCodexActionKind.auditSdd =>
      'Audit missing or incomplete SDD artifacts for this workspace and propose the next concrete fixes.',
  };
}

class SddCodexActionRequest {
  const SddCodexActionRequest({
    required this.kind,
    required this.target,
    this.linkedFeedbackIds = const <String>[],
  });

  final SddCodexActionKind kind;
  final SddFeedbackTarget target;
  final List<String> linkedFeedbackIds;
}

class SddCodexActionDraft {
  SddCodexActionDraft({
    required this.request,
    required this.prompt,
    String? executionWorkspacePath,
    this.executionWorkspaceLabel,
  }) : executionWorkspacePath =
           executionWorkspacePath ?? request.target.workspacePath;

  final SddCodexActionRequest request;
  final String prompt;
  final String executionWorkspacePath;
  final String? executionWorkspaceLabel;
}

class SddDashboardActivity {
  const SddDashboardActivity({
    this.lastFeedbackId,
    this.lastFeedbackTarget,
    this.lastActionLabel,
    this.lastActionSessionId,
  });

  final String? lastFeedbackId;
  final String? lastFeedbackTarget;
  final String? lastActionLabel;
  final String? lastActionSessionId;

  SddDashboardActivity copyWith({
    String? lastFeedbackId,
    String? lastFeedbackTarget,
    String? lastActionLabel,
    String? lastActionSessionId,
  }) {
    return SddDashboardActivity(
      lastFeedbackId: lastFeedbackId ?? this.lastFeedbackId,
      lastFeedbackTarget: lastFeedbackTarget ?? this.lastFeedbackTarget,
      lastActionLabel: lastActionLabel ?? this.lastActionLabel,
      lastActionSessionId: lastActionSessionId ?? this.lastActionSessionId,
    );
  }
}

String buildSddCodexActionPrompt(SddCodexActionRequest request) {
  final target = request.target;
  final buffer = StringBuffer()
    ..writeln('You are Codex working through Codex Mobile Bridge.')
    ..writeln()
    ..writeln('Action: ${request.kind.label}')
    ..writeln('Action kind: ${request.kind.apiValue}')
    ..writeln()
    ..writeln(request.kind.instruction)
    ..writeln()
    ..writeln('Constraints:')
    ..writeln('- Use the real workspace and existing Codex/message flow.')
    ..writeln('- Treat paths below as metadata from the SDD snapshot.')
    ..writeln('- Validate any path before reading or editing files.')
    ..writeln('- Do not invent mock data, placeholder URLs, or demo state.')
    ..writeln('- Keep SDD changes explicit and reviewable.')
    ..writeln()
    ..writeln('Context:')
    ..writeln('```yaml')
    ..writeln('workspace_path: ${target.workspacePath}')
    ..writeln('artifact_type: ${target.artifactType}')
    ..writeln('artifact_path: ${target.artifactPath}')
    ..writeln('artifact_title: ${target.artifactTitle}');
  if (target.specId != null) {
    buffer.writeln('spec_id: ${target.specId}');
  }
  if (target.specTitle != null) {
    buffer.writeln('spec_title: ${target.specTitle}');
  }
  if (target.diagramType != null) {
    buffer.writeln('diagram_type: ${target.diagramType}');
  }
  if (target.diagramScope != null) {
    buffer.writeln('diagram_scope: ${target.diagramScope}');
  }
  if (request.linkedFeedbackIds.isNotEmpty) {
    buffer
      ..writeln('linked_feedback_ids:')
      ..writeAll(request.linkedFeedbackIds.map((id) => '  - $id\n'));
  }
  buffer
    ..writeln('```')
    ..writeln();
  if (target.sourceExcerpt.isNotEmpty) {
    buffer
      ..writeln('Source excerpt:')
      ..writeln('```text')
      ..writeln(target.sourceExcerpt)
      ..writeln('```')
      ..writeln();
  }
  buffer.writeln(
    'Please perform this action and report what changed or what needs confirmation.',
  );
  return buffer.toString().trim();
}

class SddExplorerPanel extends StatefulWidget {
  const SddExplorerPanel({
    super.key,
    required this.bridgeUrl,
    required this.onClose,
    this.workspacePath,
    this.diagramRenderer = const WebViewMermaidDiagramRenderer(),
    this.loader,
    this.feedbackSubmitter,
    this.actionSubmitter,
  });

  final String bridgeUrl;
  final String? workspacePath;
  final VoidCallback onClose;
  final MermaidDiagramRenderer diagramRenderer;
  final SddExplorerLoader? loader;
  final SddFeedbackSubmitter? feedbackSubmitter;
  final SddCodexActionSubmitter? actionSubmitter;

  @override
  State<SddExplorerPanel> createState() => _SddExplorerPanelState();
}

class _SddExplorerPanelState extends State<SddExplorerPanel> {
  late Future<SddProject?> _projectFuture;
  SddDashboardActivity _activity = const SddDashboardActivity();

  @override
  void initState() {
    super.initState();
    _projectFuture = _load();
  }

  @override
  void didUpdateWidget(SddExplorerPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.bridgeUrl != widget.bridgeUrl ||
        oldWidget.workspacePath != widget.workspacePath ||
        oldWidget.loader != widget.loader) {
      _projectFuture = _load();
    }
  }

  Future<SddProject?> _load() {
    final loader = widget.loader;
    if (loader != null) {
      return loader(widget.bridgeUrl);
    }
    final client = SddExplorerClient(baseUrl: widget.bridgeUrl);
    final workspacePath = widget.workspacePath?.trim();
    if (workspacePath != null && workspacePath.isNotEmpty) {
      return client.getProject(workspacePath);
    }
    return client.loadDefaultProject();
  }

  void _retry() {
    setState(() {
      _projectFuture = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final panelWidth = width < 620
        ? width
        : width < 1100
        ? 620.0
        : 860.0;
    return Align(
      alignment: Alignment.centerRight,
      child: Material(
        color: _WorkbenchColors.background,
        elevation: 18,
        child: Theme(
          data: _workbenchTheme(context),
          child: SizedBox(
            width: panelWidth,
            height: double.infinity,
            child: SafeArea(
              child: Column(
                children: <Widget>[
                  _SddExplorerHeader(onClose: widget.onClose),
                  Expanded(
                    child: FutureBuilder<SddProject?>(
                      future: _projectFuture,
                      builder: (context, snapshot) {
                        if (snapshot.connectionState != ConnectionState.done) {
                          return const _SddExplorerLoading();
                        }
                        if (snapshot.hasError) {
                          return _SddExplorerError(
                            errorText: snapshot.error.toString(),
                            onRetry: _retry,
                          );
                        }
                        final project = snapshot.data;
                        if (project == null) {
                          return _SddExplorerEmpty(onRetry: _retry);
                        }
                        return _SddProjectView(
                          project: project,
                          activity: _activity,
                          diagramRenderer: widget.diagramRenderer,
                          onFeedback: _openFeedback,
                          onCodexAction: _openCodexAction,
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _openFeedback(SddFeedbackTarget target) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Theme(
          data: _workbenchTheme(dialogContext),
          child: _SddFeedbackDialog(
            bridgeUrl: widget.bridgeUrl,
            target: target,
            submitter: widget.feedbackSubmitter ?? _submitSddFeedback,
            onCodexAction: _openCodexAction,
            onFeedbackQueued: _recordFeedbackQueued,
          ),
        );
      },
    );
  }

  void _openCodexAction(SddCodexActionRequest request) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Theme(
          data: _workbenchTheme(dialogContext),
          child: _SddCodexActionDialog(
            bridgeUrl: widget.bridgeUrl,
            request: request,
            submitter: widget.actionSubmitter ?? _submitSddCodexAction,
            onActionSubmitted: _recordActionSubmitted,
          ),
        );
      },
    );
  }

  void _recordFeedbackQueued(
    SddFeedbackSubmissionResult item,
    SddFeedbackTarget target,
  ) {
    setState(() {
      _activity = _activity.copyWith(
        lastFeedbackId: item.id,
        lastFeedbackTarget: target.artifactTitle,
      );
    });
  }

  void _recordActionSubmitted(
    SddCodexActionSubmissionResult accepted,
    SddCodexActionRequest request,
  ) {
    setState(() {
      _activity = _activity.copyWith(
        lastActionLabel: request.kind.label,
        lastActionSessionId: accepted.sessionId,
      );
    });
  }
}

Future<SddFeedbackSubmissionResult> _submitSddFeedback(
  String bridgeUrl,
  SddFeedbackDraft draft,
) {
  throw UnsupportedError(
    'No SDD feedback submitter was provided by the host app.',
  );
}

Future<SddCodexActionSubmissionResult> _submitSddCodexAction(
  String bridgeUrl,
  SddCodexActionDraft draft,
) {
  throw UnsupportedError(
    'No SDD Codex action submitter was provided by the host app.',
  );
}

class _WorkbenchColors {
  static const background = Color(0xFF08111F);
  static const surface = Color(0xFF111A2E);
  static const surfaceHigh = Color(0xFF17233A);
  static const border = Color(0xFF334260);
  static const primary = Color(0xFF5EEAD4);
  static const onPrimary = Color(0xFF03201C);
  static const onBackground = Color(0xFFF4F7FB);
  static const secondaryText = Color(0xFFB2BED6);
  static const warning = Color(0xFFFFD166);
  static const warningSurface = Color(0xFF2C2414);
  static const sourceBackground = Color(0xFF050B15);
  static const sourceText = Color(0xFFE7EEF9);
}

ThemeData _workbenchTheme(BuildContext context) {
  final base = ThemeData.dark(useMaterial3: true);
  final textTheme = base.textTheme.apply(
    bodyColor: _WorkbenchColors.onBackground,
    displayColor: _WorkbenchColors.onBackground,
    decorationColor: _WorkbenchColors.onBackground,
  );
  final colorScheme =
      ColorScheme.fromSeed(
        seedColor: _WorkbenchColors.primary,
        brightness: Brightness.dark,
      ).copyWith(
        primary: _WorkbenchColors.primary,
        onPrimary: _WorkbenchColors.onPrimary,
        surface: _WorkbenchColors.surface,
        onSurface: _WorkbenchColors.onBackground,
        secondary: _WorkbenchColors.warning,
        onSecondary: _WorkbenchColors.background,
        error: _WorkbenchColors.warning,
        onError: _WorkbenchColors.background,
        outline: _WorkbenchColors.border,
      );
  return base.copyWith(
    colorScheme: colorScheme,
    scaffoldBackgroundColor: _WorkbenchColors.background,
    canvasColor: _WorkbenchColors.background,
    dividerColor: _WorkbenchColors.border,
    iconTheme: const IconThemeData(color: _WorkbenchColors.onBackground),
    textTheme: textTheme,
    primaryTextTheme: textTheme,
    tabBarTheme: const TabBarThemeData(
      labelColor: _WorkbenchColors.primary,
      unselectedLabelColor: _WorkbenchColors.secondaryText,
      indicatorColor: _WorkbenchColors.primary,
      dividerColor: _WorkbenchColors.border,
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: _WorkbenchColors.primary,
        disabledForegroundColor: _WorkbenchColors.secondaryText.withValues(
          alpha: 0.48,
        ),
        side: const BorderSide(color: _WorkbenchColors.primary, width: 1.2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        textStyle: const TextStyle(fontWeight: FontWeight.w800),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: _WorkbenchColors.primary,
        disabledForegroundColor: _WorkbenchColors.secondaryText.withValues(
          alpha: 0.48,
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w800),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: _WorkbenchColors.primary,
        foregroundColor: _WorkbenchColors.onPrimary,
        disabledBackgroundColor: _WorkbenchColors.border,
        disabledForegroundColor: _WorkbenchColors.secondaryText,
        textStyle: const TextStyle(fontWeight: FontWeight.w800),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: _WorkbenchColors.surfaceHigh,
      selectedColor: _WorkbenchColors.primary,
      disabledColor: _WorkbenchColors.border,
      labelStyle: const TextStyle(
        color: _WorkbenchColors.onBackground,
        fontWeight: FontWeight.w700,
      ),
      secondaryLabelStyle: const TextStyle(
        color: _WorkbenchColors.onPrimary,
        fontWeight: FontWeight.w800,
      ),
      side: const BorderSide(color: _WorkbenchColors.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
    dialogTheme: base.dialogTheme.copyWith(
      backgroundColor: _WorkbenchColors.surface,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: textTheme.titleLarge?.copyWith(
        color: _WorkbenchColors.onBackground,
        fontWeight: FontWeight.w900,
      ),
      contentTextStyle: textTheme.bodyMedium?.copyWith(
        color: _WorkbenchColors.onBackground,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: _WorkbenchColors.sourceBackground,
      labelStyle: const TextStyle(color: _WorkbenchColors.secondaryText),
      hintStyle: const TextStyle(color: _WorkbenchColors.secondaryText),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: _WorkbenchColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(
          color: _WorkbenchColors.primary,
          width: 1.4,
        ),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: _WorkbenchColors.warning),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(
          color: _WorkbenchColors.warning,
          width: 1.4,
        ),
      ),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
    ),
    popupMenuTheme: base.popupMenuTheme.copyWith(
      color: _WorkbenchColors.surfaceHigh,
      surfaceTintColor: Colors.transparent,
      textStyle: const TextStyle(color: _WorkbenchColors.onBackground),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        foregroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return _WorkbenchColors.onPrimary;
          }
          return _WorkbenchColors.onBackground;
        }),
        backgroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return _WorkbenchColors.primary;
          }
          return _WorkbenchColors.surfaceHigh;
        }),
        side: WidgetStateProperty.resolveWith((states) {
          final color = states.contains(WidgetState.selected)
              ? _WorkbenchColors.primary
              : _WorkbenchColors.border;
          return BorderSide(color: color);
        }),
        textStyle: WidgetStateProperty.all(
          const TextStyle(fontWeight: FontWeight.w800),
        ),
        visualDensity: VisualDensity.compact,
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return _WorkbenchColors.primary;
        }
        return _WorkbenchColors.secondaryText;
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return _WorkbenchColors.primary.withValues(alpha: 0.36);
        }
        return _WorkbenchColors.border;
      }),
    ),
  );
}

class _SddExplorerHeader extends StatelessWidget {
  const _SddExplorerHeader({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 6, 8, 6),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: _WorkbenchColors.border)),
      ),
      child: Row(
        children: <Widget>[
          const Icon(
            Icons.account_tree_outlined,
            color: _WorkbenchColors.primary,
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'SDD Workbench',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14),
            ),
          ),
          IconButton(
            tooltip: 'Close SDD Explorer',
            onPressed: onClose,
            icon: const Icon(Icons.close_rounded),
          ),
        ],
      ),
    );
  }
}

class _SddExplorerLoading extends StatelessWidget {
  const _SddExplorerLoading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Loading SDD Explorer'),
        ],
      ),
    );
  }
}

class _SddExplorerError extends StatelessWidget {
  const _SddExplorerError({required this.errorText, required this.onRetry});

  final String errorText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _StateMessage(
      icon: Icons.error_outline,
      title: 'Could not load SDD Explorer',
      detail: errorText,
      actionLabel: 'Retry',
      onPressed: onRetry,
    );
  }
}

class _SddExplorerEmpty extends StatelessWidget {
  const _SddExplorerEmpty({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _StateMessage(
      icon: Icons.folder_off_outlined,
      title: 'No SDD project found',
      detail: 'The Bridge did not return a project for this workspace.',
      actionLabel: 'Retry',
      onPressed: onRetry,
    );
  }
}

class _StateMessage extends StatelessWidget {
  const _StateMessage({
    required this.icon,
    required this.title,
    required this.detail,
    required this.actionLabel,
    required this.onPressed,
  });

  final IconData icon;
  final String title;
  final String detail;
  final String actionLabel;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: 42, color: _WorkbenchColors.secondaryText),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
            ),
            const SizedBox(height: 8),
            Text(
              detail,
              textAlign: TextAlign.center,
              style: const TextStyle(color: _WorkbenchColors.secondaryText),
            ),
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: onPressed,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(actionLabel),
            ),
          ],
        ),
      ),
    );
  }
}

class _SddProjectView extends StatelessWidget {
  const _SddProjectView({
    required this.project,
    required this.activity,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddProject project;
  final SddDashboardActivity activity;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _WorkbenchProjectHeader(project: project),
          const TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: <Widget>[
              Tab(text: 'Overview'),
              Tab(text: 'Specs'),
              Tab(text: 'Diagrams'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: <Widget>[
                _OverviewTab(
                  project: project,
                  activity: activity,
                  onCodexAction: onCodexAction,
                ),
                _SpecsTab(
                  project: project,
                  diagramRenderer: diagramRenderer,
                  onFeedback: onFeedback,
                  onCodexAction: onCodexAction,
                ),
                _DiagramsTab(
                  project: project,
                  diagramRenderer: diagramRenderer,
                  onFeedback: onFeedback,
                  onCodexAction: onCodexAction,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _WorkbenchProjectHeader extends StatelessWidget {
  const _WorkbenchProjectHeader({required this.project});

  final SddProject project;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 6),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              _projectDisplayName(project),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900),
            ),
          ),
        ],
      ),
    );
  }
}

class _OverviewTab extends StatelessWidget {
  const _OverviewTab({
    required this.project,
    required this.activity,
    required this.onCodexAction,
  });

  final SddProject project;
  final SddDashboardActivity activity;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    final diagrams = _allDiagrams(project);
    final progress = _projectTaskProgress(project);
    final overviewTarget = _overviewActionTarget(project);
    final firstSpec = project.specs.isEmpty ? null : project.specs.first;
    final firstDiagram = diagrams.isEmpty ? null : diagrams.first;
    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
      children: <Widget>[
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            _MetricTile(
              label: 'Constitution',
              value: project.constitution == null ? 'Missing' : 'Present',
              warning: project.constitution == null,
            ),
            _MetricTile(label: 'Specs', value: '${project.specs.length}'),
            _MetricTile(label: 'Diagrams', value: '${diagrams.length}'),
            _MetricTile(
              label: 'Tasks',
              value: progress == null
                  ? 'Source only'
                  : '${progress.completed}/${progress.total}',
              warning: progress == null || progress.completed < progress.total,
            ),
            _MetricTile(
              label: 'Slice docs',
              value: '${_sliceDocCount(project)}',
            ),
          ],
        ),
        const SizedBox(height: 14),
        _PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'Project identity',
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              _KeyValueLine(label: 'Name', value: _projectDisplayName(project)),
              _KeyValueLine(
                label: 'Manifest',
                value: project.manifest?.path ?? 'Missing',
                warning: project.manifest == null,
              ),
              _KeyValueLine(
                label: 'Workspace',
                value: _workspaceFolderName(project.workspacePath),
              ),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: Tooltip(
                  message: 'Audit missing or incomplete SDD artifacts',
                  child: OutlinedButton.icon(
                    onPressed: () {
                      onCodexAction(
                        SddCodexActionRequest(
                          kind: SddCodexActionKind.auditSdd,
                          target: overviewTarget,
                        ),
                      );
                    },
                    icon: const Icon(Icons.manage_search_rounded, size: 16),
                    label: const Text('Audit SDD'),
                  ),
                ),
              ),
            ],
          ),
        ),
        _PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'Next actions',
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  OutlinedButton.icon(
                    onPressed: () {
                      onCodexAction(
                        SddCodexActionRequest(
                          kind: SddCodexActionKind.auditSdd,
                          target: overviewTarget,
                        ),
                      );
                    },
                    icon: const Icon(Icons.manage_search_rounded, size: 16),
                    label: const Text('Audit SDD'),
                  ),
                  if (firstSpec?.spec != null)
                    OutlinedButton.icon(
                      onPressed: () {
                        onCodexAction(
                          SddCodexActionRequest(
                            kind: SddCodexActionKind.refineSpec,
                            target: _fileFeedbackTarget(
                              project: project,
                              spec: firstSpec,
                              file: firstSpec!.spec,
                              artifactType: 'spec',
                              fallbackTitle: 'spec.md',
                            )!,
                          ),
                        );
                      },
                      icon: const Icon(Icons.description_outlined, size: 16),
                      label: const Text('Refine first spec'),
                    ),
                  if (firstDiagram != null)
                    OutlinedButton.icon(
                      onPressed: () {
                        onCodexAction(
                          SddCodexActionRequest(
                            kind: SddCodexActionKind.explainDiagramImpact,
                            target: _diagramFeedbackTarget(
                              project: project,
                              diagram: firstDiagram,
                            ),
                          ),
                        );
                      },
                      icon: const Icon(Icons.account_tree_outlined, size: 16),
                      label: const Text('Explain first diagram'),
                    ),
                ],
              ),
            ],
          ),
        ),
        _PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'Last known activity',
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              _KeyValueLine(
                label: 'Feedback',
                value: activity.lastFeedbackId == null
                    ? 'No feedback queued from this overview yet'
                    : '${activity.lastFeedbackId} · ${activity.lastFeedbackTarget ?? 'SDD artifact'}',
              ),
              _KeyValueLine(
                label: 'Action',
                value: activity.lastActionLabel == null
                    ? 'No Codex action submitted from this overview yet'
                    : '${activity.lastActionLabel} · ${activity.lastActionSessionId ?? 'session pending'}',
              ),
            ],
          ),
        ),
        if (project.missingRequired.isNotEmpty)
          _MissingArtifacts(items: project.missingRequired),
        if (project.specs.isEmpty)
          const _InfoCard(
            title: 'No specs',
            detail: 'This project has no readable SDD specs yet.',
          ),
      ],
    );
  }
}

class _SpecsTab extends StatefulWidget {
  const _SpecsTab({
    required this.project,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddProject project;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  State<_SpecsTab> createState() => _SpecsTabState();
}

class _SpecsTabState extends State<_SpecsTab> {
  _SpecArtifactSelection _selection = const _SpecArtifactSelection(
    specIndex: 0,
    kind: _SpecArtifactKind.spec,
  );

  @override
  void didUpdateWidget(_SpecsTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.project != widget.project) {
      _selection = _validatedSelection(_selection, widget.project.specs);
    }
  }

  void _select(_SpecArtifactSelection selection) {
    setState(() {
      _selection = _validatedSelection(selection, widget.project.specs);
    });
  }

  @override
  Widget build(BuildContext context) {
    final specs = widget.project.specs;
    if (specs.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(18),
        child: _InfoCard(
          title: 'No specs',
          detail: 'This project has no readable SDD specs yet.',
        ),
      );
    }
    final selection = _validatedSelection(_selection, specs);
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 720;
        final navigator = _SpecTraceNavigator(
          specs: specs,
          selection: selection,
          onSelected: _select,
        );
        final inspector = _SpecArtifactInspector(
          project: widget.project,
          spec: specs[selection.specIndex],
          selection: selection,
          diagramRenderer: widget.diagramRenderer,
          onFeedback: widget.onFeedback,
          onCodexAction: widget.onCodexAction,
        );
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
          child: wide
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    SizedBox(width: 280, child: navigator),
                    const SizedBox(width: 14),
                    Expanded(child: inspector),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    navigator,
                    const SizedBox(height: 12),
                    inspector,
                  ],
                ),
        );
      },
    );
  }
}

enum _SpecArtifactKind { spec, plan, tasks, slice, diagram }

class _SpecArtifactSelection {
  const _SpecArtifactSelection({
    required this.specIndex,
    required this.kind,
    this.artifactIndex = 0,
  });

  final int specIndex;
  final _SpecArtifactKind kind;
  final int artifactIndex;

  @override
  bool operator ==(Object other) {
    return other is _SpecArtifactSelection &&
        other.specIndex == specIndex &&
        other.kind == kind &&
        other.artifactIndex == artifactIndex;
  }

  @override
  int get hashCode => Object.hash(specIndex, kind, artifactIndex);
}

_SpecArtifactSelection _validatedSelection(
  _SpecArtifactSelection selection,
  List<SddSpec> specs,
) {
  if (specs.isEmpty) return selection;
  final specIndex = selection.specIndex.clamp(0, specs.length - 1).toInt();
  final spec = specs[specIndex];
  final maxIndex = switch (selection.kind) {
    _SpecArtifactKind.spec => spec.allSpecFiles.length - 1,
    _SpecArtifactKind.plan => spec.allPlanFiles.length - 1,
    _SpecArtifactKind.tasks => spec.allTaskFiles.length - 1,
    _SpecArtifactKind.slice => spec.sliceDocs.length - 1,
    _SpecArtifactKind.diagram => spec.diagrams.length - 1,
  };
  if (maxIndex >= 0) {
    return _SpecArtifactSelection(
      specIndex: specIndex,
      kind: selection.kind,
      artifactIndex: selection.artifactIndex.clamp(0, maxIndex).toInt(),
    );
  }
  final first = _firstAvailableArtifact(spec);
  return _SpecArtifactSelection(specIndex: specIndex, kind: first);
}

_SpecArtifactKind _firstAvailableArtifact(SddSpec spec) {
  if (spec.allSpecFiles.isNotEmpty) return _SpecArtifactKind.spec;
  if (spec.allPlanFiles.isNotEmpty) return _SpecArtifactKind.plan;
  if (spec.allTaskFiles.isNotEmpty) return _SpecArtifactKind.tasks;
  if (spec.sliceDocs.isNotEmpty) return _SpecArtifactKind.slice;
  if (spec.diagrams.isNotEmpty) return _SpecArtifactKind.diagram;
  return _SpecArtifactKind.spec;
}

class _SpecTraceNavigator extends StatelessWidget {
  const _SpecTraceNavigator({
    required this.specs,
    required this.selection,
    required this.onSelected,
  });

  final List<SddSpec> specs;
  final _SpecArtifactSelection selection;
  final ValueChanged<_SpecArtifactSelection> onSelected;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(
                Icons.account_tree_outlined,
                size: 16,
                color: _WorkbenchColors.primary,
              ),
              SizedBox(width: 8),
              Text('SDD trace', style: TextStyle(fontWeight: FontWeight.w900)),
            ],
          ),
          const SizedBox(height: 8),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 520),
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: specs.length,
              itemBuilder: (context, index) {
                return _SpecTraceSpecNode(
                  spec: specs[index],
                  specIndex: index,
                  selection: selection,
                  onSelected: onSelected,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SpecTraceSpecNode extends StatelessWidget {
  const _SpecTraceSpecNode({
    required this.spec,
    required this.specIndex,
    required this.selection,
    required this.onSelected,
  });

  final SddSpec spec;
  final int specIndex;
  final _SpecArtifactSelection selection;
  final ValueChanged<_SpecArtifactSelection> onSelected;

  @override
  Widget build(BuildContext context) {
    final selectedSpec = selection.specIndex == specIndex;
    final specFiles = spec.allSpecFiles;
    final planFiles = spec.allPlanFiles;
    final taskFiles = spec.allTaskFiles;
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        initiallyExpanded: selectedSpec,
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(left: 8, bottom: 8),
        leading: Icon(
          selectedSpec
              ? Icons.folder_open_outlined
              : Icons.folder_copy_outlined,
          size: 18,
          color: selectedSpec
              ? _WorkbenchColors.primary
              : _WorkbenchColors.secondaryText,
        ),
        title: Text(
          spec.title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: 13,
            fontWeight: selectedSpec ? FontWeight.w900 : FontWeight.w700,
          ),
        ),
        subtitle: Text(
          spec.id,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: _WorkbenchColors.secondaryText,
            fontSize: 11,
          ),
        ),
        children: <Widget>[
          if (spec.missing.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(left: 32, bottom: 6),
              child: Text(
                'Missing: ${spec.missing.join(', ')}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: _WorkbenchColors.warning,
                  fontSize: 11,
                ),
              ),
            ),
          ..._traceFileTiles(
            specIndex: specIndex,
            kind: _SpecArtifactKind.spec,
            files: specFiles,
            fallbackLabel: 'spec.md',
            icon: Icons.description_outlined,
          ),
          if (planFiles.isNotEmpty) const _TraceGroupLabel(label: 'Plans'),
          if (planFiles.isEmpty && taskFiles.isNotEmpty)
            const _TraceGroupLabel(label: 'Tasks'),
          if (planFiles.isEmpty)
            ..._traceFileTiles(
              specIndex: specIndex,
              kind: _SpecArtifactKind.tasks,
              files: taskFiles,
              fallbackLabel: 'tasks.md',
              icon: Icons.checklist_rounded,
              indent: 18,
            )
          else
            ..._planTraceTiles(planFiles, taskFiles),
          if (spec.sliceDocs.isNotEmpty)
            const _TraceGroupLabel(label: 'Slices'),
          ..._traceFileTiles(
            specIndex: specIndex,
            kind: _SpecArtifactKind.slice,
            files: spec.sliceDocs,
            fallbackLabel: 'slice.md',
            icon: Icons.view_agenda_outlined,
          ),
          if (spec.diagrams.isNotEmpty)
            const _TraceGroupLabel(label: 'Diagrams'),
          ...List<Widget>.generate(spec.diagrams.length, (index) {
            final diagram = spec.diagrams[index];
            return _TraceArtifactTile(
              label: diagram.title ?? '${diagram.diagramType} diagram',
              path: diagram.path,
              icon: Icons.account_tree_outlined,
              indent: 18,
              selected: _isSelected(_SpecArtifactKind.diagram, index),
              onTap: () {
                onSelected(
                  _SpecArtifactSelection(
                    specIndex: specIndex,
                    kind: _SpecArtifactKind.diagram,
                    artifactIndex: index,
                  ),
                );
              },
            );
          }),
        ],
      ),
    );
  }

  List<Widget> _planTraceTiles(
    List<SddFile> planFiles,
    List<SddFile> taskFiles,
  ) {
    return List<Widget>.generate(planFiles.length, (planIndex) {
      final taskIndexes = taskFiles.length == planFiles.length
          ? <int>[planIndex]
          : planIndex == 0
          ? List<int>.generate(taskFiles.length, (index) => index)
          : const <int>[];
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _TraceArtifactTile(
            label: _artifactLabel(planFiles[planIndex], 'plan.md'),
            path: planFiles[planIndex].path,
            icon: Icons.route_outlined,
            indent: 18,
            selected: _isSelected(_SpecArtifactKind.plan, planIndex),
            onTap: () {
              onSelected(
                _SpecArtifactSelection(
                  specIndex: specIndex,
                  kind: _SpecArtifactKind.plan,
                  artifactIndex: planIndex,
                ),
              );
            },
          ),
          ...taskIndexes.map((taskIndex) {
            final file = taskFiles[taskIndex];
            return _TraceArtifactTile(
              label: _artifactLabel(file, 'tasks.md'),
              path: file.path,
              icon: Icons.checklist_rounded,
              indent: 36,
              selected: _isSelected(_SpecArtifactKind.tasks, taskIndex),
              onTap: () {
                onSelected(
                  _SpecArtifactSelection(
                    specIndex: specIndex,
                    kind: _SpecArtifactKind.tasks,
                    artifactIndex: taskIndex,
                  ),
                );
              },
            );
          }),
        ],
      );
    });
  }

  List<Widget> _traceFileTiles({
    required int specIndex,
    required _SpecArtifactKind kind,
    required List<SddFile> files,
    required String fallbackLabel,
    required IconData icon,
    double indent = 18,
  }) {
    return List<Widget>.generate(files.length, (index) {
      final file = files[index];
      return _TraceArtifactTile(
        label: _artifactLabel(file, fallbackLabel),
        path: file.path,
        icon: icon,
        indent: indent,
        selected: _isSelected(kind, index),
        onTap: () {
          onSelected(
            _SpecArtifactSelection(
              specIndex: specIndex,
              kind: kind,
              artifactIndex: index,
            ),
          );
        },
      );
    });
  }

  bool _isSelected(_SpecArtifactKind kind, int index) {
    return selection.specIndex == specIndex &&
        selection.kind == kind &&
        selection.artifactIndex == index;
  }
}

class _TraceGroupLabel extends StatelessWidget {
  const _TraceGroupLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 8, 0, 4),
      child: Text(
        label,
        style: const TextStyle(
          color: _WorkbenchColors.secondaryText,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _TraceArtifactTile extends StatelessWidget {
  const _TraceArtifactTile({
    required this.label,
    required this.path,
    required this.icon,
    required this.indent,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final String path;
  final IconData icon;
  final double indent;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected
          ? _WorkbenchColors.primary.withValues(alpha: 0.14)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.fromLTRB(indent, 7, 8, 7),
          child: Row(
            children: <Widget>[
              Icon(
                icon,
                size: 16,
                color: selected
                    ? _WorkbenchColors.primary
                    : _WorkbenchColors.secondaryText,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: selected
                            ? FontWeight.w900
                            : FontWeight.w700,
                      ),
                    ),
                    Text(
                      path,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.secondaryText,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SpecArtifactInspector extends StatelessWidget {
  const _SpecArtifactInspector({
    required this.project,
    required this.spec,
    required this.selection,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddProject project;
  final SddSpec spec;
  final _SpecArtifactSelection selection;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          spec.title,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 3),
        Text(
          spec.path,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: _WorkbenchColors.secondaryText,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            _TraceChip(label: '${spec.allPlanFiles.length} plans'),
            _TraceChip(label: '${spec.allTaskFiles.length} task files'),
            _TraceChip(label: '${spec.sliceDocs.length} slices'),
          ],
        ),
        const SizedBox(height: 10),
        if (spec.missing.isNotEmpty) _MissingArtifacts(items: spec.missing),
        _buildSelectedArtifact(),
      ],
    );
  }

  Widget _buildSelectedArtifact() {
    switch (selection.kind) {
      case _SpecArtifactKind.spec:
        final file = _fileAt(spec.allSpecFiles, selection.artifactIndex);
        return _SddFileSection(
          title: _artifactLabel(file, 'spec.md'),
          file: file,
          feedbackTarget: _fileFeedbackTarget(
            project: project,
            spec: spec,
            file: file,
            artifactType: 'spec',
            fallbackTitle: 'spec.md',
          ),
          onFeedback: onFeedback,
          actions: const <SddCodexActionKind>[SddCodexActionKind.refineSpec],
          onCodexAction: onCodexAction,
        );
      case _SpecArtifactKind.plan:
        final file = _fileAt(spec.allPlanFiles, selection.artifactIndex);
        return _SddFileSection(
          title: _artifactLabel(file, 'plan.md'),
          file: file,
          feedbackTarget: _fileFeedbackTarget(
            project: project,
            spec: spec,
            file: file,
            artifactType: 'plan',
            fallbackTitle: 'plan.md',
          ),
          onFeedback: onFeedback,
          actions: const <SddCodexActionKind>[SddCodexActionKind.updatePlan],
          onCodexAction: onCodexAction,
        );
      case _SpecArtifactKind.tasks:
        final file = _fileAt(spec.allTaskFiles, selection.artifactIndex);
        return _TaskFileSection(
          title: _artifactLabel(file, 'tasks.md'),
          file: file,
          feedbackTarget: _fileFeedbackTarget(
            project: project,
            spec: spec,
            file: file,
            artifactType: 'tasks',
            fallbackTitle: 'tasks.md',
          ),
          onFeedback: onFeedback,
          actions: const <SddCodexActionKind>[SddCodexActionKind.updateTasks],
          onCodexAction: onCodexAction,
        );
      case _SpecArtifactKind.slice:
        final file = _fileAt(spec.sliceDocs, selection.artifactIndex);
        return _SddFileSection(
          title: _artifactLabel(file, 'slice.md'),
          file: file,
          feedbackTarget: _fileFeedbackTarget(
            project: project,
            spec: spec,
            file: file,
            artifactType: 'slice',
            fallbackTitle: 'slice.md',
          ),
          onFeedback: onFeedback,
          actions: const <SddCodexActionKind>[SddCodexActionKind.reviewSlice],
          onCodexAction: onCodexAction,
        );
      case _SpecArtifactKind.diagram:
        final diagram = _fileAt(spec.diagrams, selection.artifactIndex);
        if (diagram == null) {
          return const _InfoCard(
            title: 'Spec diagrams',
            detail: 'No diagrams found',
          );
        }
        return _DiagramCard(
          diagram: diagram,
          diagramRenderer: diagramRenderer,
          feedbackTarget: _diagramFeedbackTarget(
            project: project,
            spec: spec,
            diagram: diagram,
          ),
          onFeedback: onFeedback,
          onCodexAction: onCodexAction,
        );
    }
  }
}

class _TraceChip extends StatelessWidget {
  const _TraceChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(visualDensity: VisualDensity.compact, label: Text(label));
  }
}

class _DiagramsTab extends StatefulWidget {
  const _DiagramsTab({
    required this.project,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddProject project;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  State<_DiagramsTab> createState() => _DiagramsTabState();
}

class _DiagramsTabState extends State<_DiagramsTab> {
  String _typeFilter = 'all';

  @override
  Widget build(BuildContext context) {
    final diagrams = _allDiagramItems(widget.project);
    final types = <String>{
      'all',
      ...diagrams.map((item) => item.diagram.diagramType),
    }.toList(growable: false);
    final filtered = _typeFilter == 'all'
        ? diagrams
        : diagrams
              .where((item) => item.diagram.diagramType == _typeFilter)
              .toList(growable: false);
    final grouped = <String, List<_DiagramListItem>>{};
    for (final item in filtered) {
      grouped
          .putIfAbsent(item.diagram.scope, () => <_DiagramListItem>[])
          .add(item);
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
      children: <Widget>[
        if (diagrams.isEmpty)
          const _InfoCard(title: 'Diagrams', detail: 'No diagrams found')
        else ...[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              _DiagramFilterMenu(
                types: types,
                selectedType: _typeFilter,
                onSelected: (type) {
                  setState(() {
                    _typeFilter = type;
                  });
                },
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...grouped.entries.map(
            (entry) => _DiagramListGroup(
              title: entry.key == 'architecture'
                  ? 'Architecture diagrams'
                  : '${entry.key} diagrams',
              items: entry.value,
              diagramRenderer: widget.diagramRenderer,
              project: widget.project,
              onFeedback: widget.onFeedback,
              onCodexAction: widget.onCodexAction,
            ),
          ),
        ],
      ],
    );
  }
}

class _DiagramFilterMenu extends StatelessWidget {
  const _DiagramFilterMenu({
    required this.types,
    required this.selectedType,
    required this.onSelected,
  });

  final List<String> types;
  final String selectedType;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final selectedLabel = selectedType == 'all' ? 'All diagrams' : selectedType;
    final menuItems = types
        .map(
          (type) => PopupMenuItem<String>(
            value: type,
            child: Row(
              children: <Widget>[
                Icon(
                  selectedType == type
                      ? Icons.check_rounded
                      : Icons.account_tree_outlined,
                  size: 16,
                  color: selectedType == type
                      ? _WorkbenchColors.primary
                      : _WorkbenchColors.secondaryText,
                ),
                const SizedBox(width: 8),
                Text(type == 'all' ? 'All diagrams' : type),
              ],
            ),
          ),
        )
        .toList(growable: false);
    return PopupMenuButton<String>(
      tooltip: 'Filter diagrams',
      onSelected: onSelected,
      itemBuilder: (context) => menuItems,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: _WorkbenchColors.surfaceHigh,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: _WorkbenchColors.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(
              Icons.filter_list_rounded,
              size: 16,
              color: _WorkbenchColors.primary,
            ),
            const SizedBox(width: 8),
            Text(
              selectedLabel,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            const Icon(Icons.arrow_drop_down_rounded, size: 18),
          ],
        ),
      ),
    );
  }
}

class _DiagramListItem {
  const _DiagramListItem({required this.diagram, this.spec});

  final SddDiagram diagram;
  final SddSpec? spec;
}

class _DiagramListGroup extends StatelessWidget {
  const _DiagramListGroup({
    required this.title,
    required this.items,
    required this.diagramRenderer,
    required this.project,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final String title;
  final List<_DiagramListItem> items;
  final MermaidDiagramRenderer diagramRenderer;
  final SddProject project;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return _InfoCard(title: title, detail: 'No diagrams found');
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: _PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              title,
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15),
            ),
            const SizedBox(height: 8),
            ...items.map(
              (item) => _DiagramListTile(
                item: item,
                project: project,
                diagramRenderer: diagramRenderer,
                onFeedback: onFeedback,
                onCodexAction: onCodexAction,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DiagramListTile extends StatelessWidget {
  const _DiagramListTile({
    required this.item,
    required this.project,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final _DiagramListItem item;
  final SddProject project;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    final diagram = item.diagram;
    final target = _diagramFeedbackTarget(
      project: project,
      spec: item.spec,
      diagram: diagram,
    );
    final title = diagram.title ?? '${diagram.diagramType} diagram';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openFullscreen(context, diagram),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            children: <Widget>[
              const Icon(
                Icons.account_tree_outlined,
                size: 18,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w900),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      item.spec == null
                          ? diagram.path
                          : '${item.spec!.title} / ${diagram.path}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.secondaryText,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Add diagram feedback',
                onPressed: () => onFeedback(target),
                icon: const Icon(Icons.rate_review_outlined, size: 18),
              ),
              PopupMenuButton<SddCodexActionKind>(
                tooltip: 'Open diagram Codex actions',
                onSelected: (kind) {
                  onCodexAction(
                    SddCodexActionRequest(kind: kind, target: target),
                  );
                },
                itemBuilder: (context) =>
                    const <SddCodexActionKind>[
                          SddCodexActionKind.updateDiagram,
                          SddCodexActionKind.explainDiagramImpact,
                          SddCodexActionKind.alignDiagramWithSpec,
                        ]
                        .map(
                          (kind) => PopupMenuItem<SddCodexActionKind>(
                            value: kind,
                            child: Text(kind.label),
                          ),
                        )
                        .toList(growable: false),
                icon: const Icon(Icons.auto_fix_high_rounded, size: 18),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openFullscreen(BuildContext context, SddDiagram diagram) {
    showDialog<void>(
      context: context,
      useSafeArea: false,
      builder: (dialogContext) {
        return Theme(
          data: _workbenchTheme(dialogContext),
          child: _FullscreenDiagramDialog(
            diagram: diagram,
            diagramRenderer: _fullscreenRenderer(diagramRenderer),
            sourceText: diagram.content ?? '',
          ),
        );
      },
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    this.warning = false,
  });

  final String label;
  final String value;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 132,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: warning
            ? _WorkbenchColors.warningSurface
            : _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: warning ? _WorkbenchColors.warning : _WorkbenchColors.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _WorkbenchColors.secondaryText,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: warning
                  ? _WorkbenchColors.warning
                  : _WorkbenchColors.onBackground,
              fontWeight: FontWeight.w900,
              fontSize: 16,
            ),
          ),
        ],
      ),
    );
  }
}

class _KeyValueLine extends StatelessWidget {
  const _KeyValueLine({
    required this.label,
    required this.value,
    this.warning = false,
  });

  final String label;
  final String value;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 84,
            child: Text(
              label,
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                color: warning
                    ? _WorkbenchColors.warning
                    : _WorkbenchColors.onBackground,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MissingArtifacts extends StatelessWidget {
  const _MissingArtifacts({required this.items});

  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Missing required artifacts',
            style: TextStyle(
              color: _WorkbenchColors.warning,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          ...items.map(
            (item) => Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('- $item'),
            ),
          ),
        ],
      ),
    );
  }
}

class _TaskFileSection extends StatelessWidget {
  const _TaskFileSection({
    required this.file,
    this.title = 'tasks.md',
    this.feedbackTarget,
    this.onFeedback,
    this.actions = const <SddCodexActionKind>[],
    this.onCodexAction,
  });

  final String title;
  final SddFile? file;
  final SddFeedbackTarget? feedbackTarget;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final List<SddCodexActionKind> actions;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;

  @override
  Widget build(BuildContext context) {
    final progress = _taskProgress(file?.content);
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _FileHeader(
            title: title,
            file: file ?? const SddFile(path: 'tasks.md', sizeBytes: 0),
          ),
          _ArtifactControls(
            target: feedbackTarget,
            onFeedback: onFeedback,
            actions: actions,
            onCodexAction: onCodexAction,
          ),
          if (file == null) ...[
            const SizedBox(height: 8),
            const Text(
              'Missing file',
              style: TextStyle(color: _WorkbenchColors.warning),
            ),
          ] else ...[
            if (progress != null) ...[
              const SizedBox(height: 10),
              _TaskProgressBar(progress: progress),
            ],
            if (file!.error != null) ...[
              const SizedBox(height: 8),
              Text(
                file!.error!,
                style: const TextStyle(color: _WorkbenchColors.warning),
              ),
            ],
            if (file!.hasContent) ...[
              const SizedBox(height: 10),
              _SourceBlock(text: file!.content!),
            ],
          ],
        ],
      ),
    );
  }
}

class _TaskProgressBar extends StatelessWidget {
  const _TaskProgressBar({required this.progress});

  final _TaskProgress progress;

  @override
  Widget build(BuildContext context) {
    final value = progress.total == 0
        ? 0.0
        : progress.completed / progress.total;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            const Icon(
              Icons.checklist_rounded,
              size: 16,
              color: _WorkbenchColors.primary,
            ),
            const SizedBox(width: 8),
            Text(
              '${progress.completed}/${progress.total} tasks complete',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12),
            ),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(value: value),
      ],
    );
  }
}

class _TaskProgress {
  const _TaskProgress({required this.completed, required this.total});

  final int completed;
  final int total;
}

List<SddDiagram> _allDiagrams(SddProject project) {
  return <SddDiagram>[
    ...project.architectureDiagrams,
    ...project.specs.expand((spec) => spec.diagrams),
  ];
}

List<_DiagramListItem> _allDiagramItems(SddProject project) {
  return <_DiagramListItem>[
    ...project.architectureDiagrams.map(
      (diagram) => _DiagramListItem(diagram: diagram),
    ),
    ...project.specs.expand(
      (spec) => spec.diagrams.map(
        (diagram) => _DiagramListItem(diagram: diagram, spec: spec),
      ),
    ),
  ];
}

int _sliceDocCount(SddProject project) {
  return project.specs.fold<int>(
    0,
    (total, spec) => total + spec.sliceDocs.length,
  );
}

_TaskProgress? _projectTaskProgress(SddProject project) {
  var completed = 0;
  var total = 0;
  for (final spec in project.specs) {
    for (final file in spec.allTaskFiles) {
      final progress = _taskProgress(file.content);
      if (progress == null) continue;
      completed += progress.completed;
      total += progress.total;
    }
  }
  if (total == 0) return null;
  return _TaskProgress(completed: completed, total: total);
}

_TaskProgress? _taskProgress(String? content) {
  if (content == null || content.trim().isEmpty) return null;
  var completed = 0;
  var total = 0;
  final checkbox = RegExp(r'^\s*-\s+\[([ xX])\]');
  for (final line in content.split('\n')) {
    final match = checkbox.firstMatch(line);
    if (match == null) continue;
    total += 1;
    if ((match.group(1) ?? '').toLowerCase() == 'x') {
      completed += 1;
    }
  }
  if (total == 0) return null;
  return _TaskProgress(completed: completed, total: total);
}

String _projectDisplayName(SddProject project) {
  return _manifestValue(project.manifest, const <String>[
        'display_name',
        'displayName',
        'name',
        'source_app',
        'sourceApp',
      ]) ??
      project.workspaceName;
}

String _workspaceFolderName(String workspacePath) {
  final parts = workspacePath
      .split('/')
      .where((part) => part.trim().isNotEmpty)
      .toList(growable: false);
  if (parts.isEmpty) return workspacePath;
  return parts.last;
}

String? _manifestValue(SddFile? manifest, List<String> keys) {
  final content = manifest?.content;
  if (content == null) return null;
  for (final line in content.split('\n')) {
    final separator = line.indexOf(':');
    if (separator <= 0) continue;
    final key = line.substring(0, separator).trim();
    if (!keys.contains(key)) continue;
    final value = line.substring(separator + 1).trim();
    if (value.isEmpty) continue;
    return value.replaceAll(RegExp(r'''^['"]|['"]$'''), '');
  }
  return null;
}

SddFeedbackTarget? _fileFeedbackTarget({
  required SddProject project,
  required SddFile? file,
  required String artifactType,
  required String fallbackTitle,
  SddSpec? spec,
}) {
  if (file == null) return null;
  return SddFeedbackTarget(
    workspacePath: project.workspacePath,
    artifactType: artifactType,
    artifactPath: _safeMetadataPath(file.path),
    artifactTitle: file.title ?? fallbackTitle,
    sourceExcerpt: _sourceExcerpt(file.content),
    specId: spec?.id,
    specTitle: spec?.title,
  );
}

SddFeedbackTarget _diagramFeedbackTarget({
  required SddProject project,
  required SddDiagram diagram,
  SddSpec? spec,
}) {
  return SddFeedbackTarget(
    workspacePath: project.workspacePath,
    artifactType: 'diagram',
    artifactPath: _safeMetadataPath(diagram.path),
    artifactTitle: diagram.title ?? '${diagram.diagramType} diagram',
    sourceExcerpt: _sourceExcerpt(diagram.content),
    specId: spec?.id,
    specTitle: spec?.title,
    diagramType: diagram.diagramType,
    diagramScope: diagram.scope,
  );
}

SddFeedbackTarget _overviewActionTarget(SddProject project) {
  final progress = _projectTaskProgress(project);
  final diagrams = _allDiagrams(project);
  final source = <String>[
    'workspace: ${project.workspacePath}',
    'specs: ${project.specs.length}',
    'diagrams: ${diagrams.length}',
    'tasks: ${progress == null ? 'source only' : '${progress.completed}/${progress.total}'}',
    if (project.missingRequired.isNotEmpty)
      'missing: ${project.missingRequired.join(', ')}',
  ].join('\n');
  return SddFeedbackTarget(
    workspacePath: project.workspacePath,
    artifactType: 'overview',
    artifactPath: '(project)',
    artifactTitle: 'SDD project overview',
    sourceExcerpt: source,
  );
}

T? _fileAt<T>(List<T> files, int index) {
  if (index < 0 || index >= files.length) return null;
  return files[index];
}

String _artifactLabel(SddFile? file, String fallback) {
  final title = file?.title?.trim();
  if (title != null && title.isNotEmpty) return title;
  final path = file?.path.trim();
  if (path == null || path.isEmpty) return fallback;
  return path.split('/').last;
}

String _safeMetadataPath(String path) {
  return path
      .split('/')
      .where((part) => part.isNotEmpty && part != '.' && part != '..')
      .join('/');
}

String _sourceExcerpt(String? source) {
  final trimmed = (source ?? '').trim();
  if (trimmed.length <= 1200) return trimmed;
  return '${trimmed.substring(0, 1200)}...';
}

class _SddFileSection extends StatelessWidget {
  const _SddFileSection({
    required this.title,
    required this.file,
    this.feedbackTarget,
    this.onFeedback,
    this.actions = const <SddCodexActionKind>[],
    this.onCodexAction,
  });

  final String title;
  final SddFile? file;
  final SddFeedbackTarget? feedbackTarget;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final List<SddCodexActionKind> actions;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;

  @override
  Widget build(BuildContext context) {
    final value = file;
    if (value == null) {
      return _InfoCard(title: title, detail: 'Missing file');
    }
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _FileHeader(title: title, file: value),
          _ArtifactControls(
            target: feedbackTarget,
            onFeedback: onFeedback,
            actions: actions,
            onCodexAction: onCodexAction,
          ),
          if (value.error != null) ...[
            const SizedBox(height: 8),
            Text(
              value.error!,
              style: const TextStyle(color: _WorkbenchColors.warning),
            ),
          ],
          if (value.hasContent) ...[
            const SizedBox(height: 10),
            _SourceBlock(text: value.content!),
          ],
        ],
      ),
    );
  }
}

enum _DiagramMode { preview, source }

class _DiagramCard extends StatefulWidget {
  const _DiagramCard({
    required this.diagram,
    required this.diagramRenderer,
    required this.feedbackTarget,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddDiagram diagram;
  final MermaidDiagramRenderer diagramRenderer;
  final SddFeedbackTarget feedbackTarget;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  State<_DiagramCard> createState() => _DiagramCardState();
}

class _DiagramCardState extends State<_DiagramCard> {
  _DiagramMode _mode = _DiagramMode.preview;
  late Future<MermaidRenderResult> _renderFuture;

  @override
  void initState() {
    super.initState();
    _renderFuture = _render();
  }

  @override
  void didUpdateWidget(_DiagramCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.diagram != widget.diagram ||
        oldWidget.diagramRenderer != widget.diagramRenderer) {
      _renderFuture = _render();
    }
  }

  Future<MermaidRenderResult> _render() {
    return widget.diagramRenderer.render(widget.diagram);
  }

  void _retryRender() {
    setState(() {
      _renderFuture = _render();
      _mode = _DiagramMode.preview;
    });
  }

  @override
  Widget build(BuildContext context) {
    final diagram = widget.diagram;
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _FileHeader(
            title: '${diagram.diagramType} diagram',
            file: diagram,
            subtitle: diagram.scope,
          ),
          _ArtifactControls(
            target: widget.feedbackTarget,
            onFeedback: widget.onFeedback,
            actions: const <SddCodexActionKind>[
              SddCodexActionKind.updateDiagram,
              SddCodexActionKind.explainDiagramImpact,
              SddCodexActionKind.alignDiagramWithSpec,
            ],
            onCodexAction: widget.onCodexAction,
          ),
          if (diagram.error != null) ...[
            const SizedBox(height: 8),
            Text(
              diagram.error!,
              style: const TextStyle(color: _WorkbenchColors.warning),
            ),
          ],
          if (diagram.hasContent) ...[
            const SizedBox(height: 12),
            _DiagramModeSwitch(
              mode: _mode,
              onChanged: (mode) {
                setState(() {
                  _mode = mode;
                });
              },
            ),
            const SizedBox(height: 10),
            if (_mode == _DiagramMode.source)
              _SourceBlock(text: diagram.content!)
            else
              _DiagramPreview(
                diagram: diagram,
                diagramRenderer: widget.diagramRenderer,
                renderFuture: _renderFuture,
                sourceText: diagram.content!,
                onRetry: _retryRender,
              ),
          ] else
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: Text(
                'No diagram source available.',
                style: TextStyle(color: _WorkbenchColors.secondaryText),
              ),
            ),
        ],
      ),
    );
  }
}

class _DiagramModeSwitch extends StatelessWidget {
  const _DiagramModeSwitch({required this.mode, required this.onChanged});

  final _DiagramMode mode;
  final ValueChanged<_DiagramMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<_DiagramMode>(
      showSelectedIcon: false,
      style: const ButtonStyle(visualDensity: VisualDensity.compact),
      segments: const <ButtonSegment<_DiagramMode>>[
        ButtonSegment<_DiagramMode>(
          value: _DiagramMode.preview,
          icon: Icon(Icons.account_tree_outlined, size: 16),
          label: Text('Preview'),
        ),
        ButtonSegment<_DiagramMode>(
          value: _DiagramMode.source,
          icon: Icon(Icons.code_rounded, size: 16),
          label: Text('Source'),
        ),
      ],
      selected: <_DiagramMode>{mode},
      onSelectionChanged: (selection) => onChanged(selection.single),
    );
  }
}

class _DiagramPreview extends StatelessWidget {
  const _DiagramPreview({
    required this.diagram,
    required this.diagramRenderer,
    required this.renderFuture,
    required this.sourceText,
    required this.onRetry,
  });

  final SddDiagram diagram;
  final MermaidDiagramRenderer diagramRenderer;
  final Future<MermaidRenderResult> renderFuture;
  final String sourceText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Align(
          alignment: Alignment.centerRight,
          child: Tooltip(
            message: 'Open diagram in full screen',
            child: TextButton.icon(
              onPressed: () => _openFullscreen(context),
              icon: const Icon(Icons.fullscreen_rounded, size: 16),
              label: const Text('Full screen'),
            ),
          ),
        ),
        FutureBuilder<MermaidRenderResult>(
          future: renderFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const _PreviewFrame(
                child: SizedBox(
                  width: 720,
                  height: 300,
                  child: Center(child: CircularProgressIndicator()),
                ),
              );
            }
            if (snapshot.hasError) {
              return _DiagramRenderError(
                message: snapshot.error.toString(),
                sourceText: sourceText,
                onRetry: onRetry,
              );
            }
            final result = snapshot.data;
            if (result == null || !result.isSuccess) {
              return _DiagramRenderError(
                message: result?.error ?? 'Could not render diagram preview.',
                sourceText: sourceText,
                onRetry: onRetry,
              );
            }
            return _PreviewFrame(child: result.preview!);
          },
        ),
      ],
    );
  }

  void _openFullscreen(BuildContext context) {
    showDialog<void>(
      context: context,
      useSafeArea: false,
      builder: (dialogContext) {
        return Theme(
          data: _workbenchTheme(dialogContext),
          child: _FullscreenDiagramDialog(
            diagram: diagram,
            diagramRenderer: _fullscreenRenderer(diagramRenderer),
            sourceText: sourceText,
          ),
        );
      },
    );
  }
}

MermaidDiagramRenderer _fullscreenRenderer(MermaidDiagramRenderer renderer) {
  if (renderer is WebViewMermaidDiagramRenderer) {
    return WebViewMermaidDiagramRenderer(
      assetBundle: renderer.assetBundle,
      previewWidth: 1400,
      previewHeight: 900,
    );
  }
  return renderer;
}

class _FullscreenDiagramDialog extends StatefulWidget {
  const _FullscreenDiagramDialog({
    required this.diagram,
    required this.diagramRenderer,
    required this.sourceText,
  });

  final SddDiagram diagram;
  final MermaidDiagramRenderer diagramRenderer;
  final String sourceText;

  @override
  State<_FullscreenDiagramDialog> createState() =>
      _FullscreenDiagramDialogState();
}

class _FullscreenDiagramDialogState extends State<_FullscreenDiagramDialog> {
  _DiagramMode _mode = _DiagramMode.preview;
  late Future<MermaidRenderResult> _renderFuture;

  @override
  void initState() {
    super.initState();
    _renderFuture = widget.diagramRenderer.render(widget.diagram);
  }

  void _retry() {
    setState(() {
      _renderFuture = widget.diagramRenderer.render(widget.diagram);
      _mode = _DiagramMode.preview;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Dialog.fullscreen(
      backgroundColor: _WorkbenchColors.background,
      child: Scaffold(
        backgroundColor: _WorkbenchColors.background,
        appBar: AppBar(
          backgroundColor: _WorkbenchColors.surface,
          surfaceTintColor: Colors.transparent,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                widget.diagram.title ?? '${widget.diagram.diagramType} diagram',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              Text(
                widget.diagram.path,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: _WorkbenchColors.secondaryText,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          actions: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: _DiagramModeSwitch(
                mode: _mode,
                onChanged: (mode) {
                  setState(() {
                    _mode = mode;
                  });
                },
              ),
            ),
            IconButton(
              tooltip: 'Close full screen diagram',
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.close_rounded),
            ),
          ],
        ),
        body: Padding(
          padding: const EdgeInsets.all(14),
          child: _mode == _DiagramMode.source
              ? _FullscreenSourceBlock(text: widget.sourceText)
              : FutureBuilder<MermaidRenderResult>(
                  future: _renderFuture,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const _FullscreenPreviewFrame(
                        child: SizedBox(
                          width: 1400,
                          height: 900,
                          child: Center(child: CircularProgressIndicator()),
                        ),
                      );
                    }
                    if (snapshot.hasError) {
                      return _DiagramRenderError(
                        message: snapshot.error.toString(),
                        sourceText: widget.sourceText,
                        onRetry: _retry,
                      );
                    }
                    final result = snapshot.data;
                    if (result == null || !result.isSuccess) {
                      return _DiagramRenderError(
                        message:
                            result?.error ??
                            'Could not render diagram preview.',
                        sourceText: widget.sourceText,
                        onRetry: _retry,
                      );
                    }
                    return _FullscreenPreviewFrame(child: result.preview!);
                  },
                ),
        ),
      ),
    );
  }
}

class _FullscreenPreviewFrame extends StatelessWidget {
  const _FullscreenPreviewFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InteractiveViewer(
        minScale: 0.25,
        maxScale: 5,
        boundaryMargin: const EdgeInsets.all(240),
        constrained: false,
        child: child,
      ),
    );
  }
}

class _FullscreenSourceBlock extends StatelessWidget {
  const _FullscreenSourceBlock({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: SingleChildScrollView(
        child: SelectableText(
          text,
          style: const TextStyle(
            fontFamily: 'monospace',
            color: _WorkbenchColors.sourceText,
            fontSize: 12,
          ),
        ),
      ),
    );
  }
}

class _PreviewFrame extends StatelessWidget {
  const _PreviewFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 320,
      width: double.infinity,
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InteractiveViewer(
        minScale: 0.55,
        maxScale: 3,
        boundaryMargin: const EdgeInsets.all(96),
        constrained: false,
        child: child,
      ),
    );
  }
}

class _DiagramRenderError extends StatelessWidget {
  const _DiagramRenderError({
    required this.message,
    required this.sourceText,
    required this.onRetry,
  });

  final String message;
  final String sourceText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _WorkbenchColors.warningSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.warning),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.warning_amber_rounded,
                color: _WorkbenchColors.warning,
                size: 18,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Diagram preview failed',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
              TextButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Retry'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            message,
            style: const TextStyle(color: _WorkbenchColors.warning),
          ),
          const SizedBox(height: 10),
          _SourceBlock(text: sourceText),
        ],
      ),
    );
  }
}

class _ArtifactControls extends StatelessWidget {
  const _ArtifactControls({
    required this.target,
    required this.onFeedback,
    required this.actions,
    required this.onCodexAction,
  });

  final SddFeedbackTarget? target;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final List<SddCodexActionKind> actions;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;

  @override
  Widget build(BuildContext context) {
    final value = target;
    if (value == null) {
      return const SizedBox.shrink();
    }
    return Align(
      alignment: Alignment.centerRight,
      child: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Wrap(
          spacing: 6,
          runSpacing: 6,
          alignment: WrapAlignment.end,
          children: <Widget>[
            if (onFeedback != null)
              Tooltip(
                message: 'Add SDD feedback for ${value.artifactPath}',
                child: TextButton.icon(
                  onPressed: () => onFeedback!(value),
                  icon: const Icon(Icons.rate_review_outlined, size: 16),
                  label: const Text('Feedback'),
                ),
              ),
            if (actions.isNotEmpty && onCodexAction != null)
              _CodexActionMenuButton(
                target: value,
                actions: actions,
                onCodexAction: onCodexAction!,
              ),
          ],
        ),
      ),
    );
  }
}

class _CodexActionMenuButton extends StatelessWidget {
  const _CodexActionMenuButton({
    required this.target,
    required this.actions,
    required this.onCodexAction,
  });

  final SddFeedbackTarget target;
  final List<SddCodexActionKind> actions;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<SddCodexActionKind>(
      tooltip: 'Open Codex actions for ${target.artifactPath}',
      onSelected: (kind) {
        onCodexAction(SddCodexActionRequest(kind: kind, target: target));
      },
      itemBuilder: (context) => actions
          .map(
            (kind) => PopupMenuItem<SddCodexActionKind>(
              value: kind,
              child: Text(kind.label),
            ),
          )
          .toList(growable: false),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.auto_fix_high_rounded, size: 16),
            SizedBox(width: 6),
            Text('Codex'),
            Icon(Icons.arrow_drop_down_rounded, size: 18),
          ],
        ),
      ),
    );
  }
}

class _SddFeedbackDialog extends StatefulWidget {
  const _SddFeedbackDialog({
    required this.bridgeUrl,
    required this.target,
    required this.submitter,
    required this.onCodexAction,
    required this.onFeedbackQueued,
  });

  final String bridgeUrl;
  final SddFeedbackTarget target;
  final SddFeedbackSubmitter submitter;
  final ValueChanged<SddCodexActionRequest> onCodexAction;
  final void Function(
    SddFeedbackSubmissionResult item,
    SddFeedbackTarget target,
  )
  onFeedbackQueued;

  @override
  State<_SddFeedbackDialog> createState() => _SddFeedbackDialogState();
}

class _SddFeedbackDialogState extends State<_SddFeedbackDialog> {
  final TextEditingController _commentController = TextEditingController();
  bool _submitting = false;
  bool _queued = false;
  String? _errorText;
  SddFeedbackSubmissionResult? _queuedItem;

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final comment = _commentController.text.trim();
    if (comment.isEmpty) {
      setState(() {
        _errorText = 'Write feedback before submitting.';
      });
      return;
    }
    setState(() {
      _submitting = true;
      _errorText = null;
    });
    try {
      final item = await widget.submitter(
        widget.bridgeUrl,
        SddFeedbackDraft(comment: comment, target: widget.target),
      );
      if (!mounted) return;
      widget.onFeedbackQueued(item, widget.target);
      setState(() {
        _queued = true;
        _queuedItem = item;
        _submitting = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _errorText = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final target = widget.target;
    return AlertDialog(
      title: const Text('SDD feedback'),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _FeedbackTargetSummary(target: target),
              const SizedBox(height: 12),
              TextField(
                controller: _commentController,
                enabled: !_submitting && !_queued,
                minLines: 4,
                maxLines: 7,
                decoration: const InputDecoration(
                  labelText: 'Feedback',
                  hintText: 'Describe what should change or be clarified.',
                ),
              ),
              if (target.sourceExcerpt.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Text(
                  'Source context',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                _SourceBlock(text: target.sourceExcerpt),
              ],
              if (_errorText != null) ...[
                const SizedBox(height: 10),
                Text(
                  _errorText!,
                  style: const TextStyle(color: _WorkbenchColors.warning),
                ),
              ],
              if (_queued) ...[
                const SizedBox(height: 10),
                Row(
                  children: <Widget>[
                    const Icon(
                      Icons.check_circle_outline_rounded,
                      color: _WorkbenchColors.primary,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(child: Text('Feedback queued')),
                  ],
                ),
                if (_queuedItem?.id.isNotEmpty == true) ...[
                  const SizedBox(height: 4),
                  Text(
                    _queuedItem!.id,
                    style: const TextStyle(
                      color: _WorkbenchColors.secondaryText,
                      fontSize: 12,
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () {
                    final feedbackId = _queuedItem?.id;
                    Navigator.of(context).pop();
                    widget.onCodexAction(
                      SddCodexActionRequest(
                        kind: SddCodexActionKind.addressFeedback,
                        target: widget.target,
                        linkedFeedbackIds:
                            feedbackId == null || feedbackId.trim().isEmpty
                            ? const <String>[]
                            : <String>[feedbackId],
                      ),
                    );
                  },
                  icon: const Icon(Icons.auto_fix_high_rounded, size: 16),
                  label: const Text('Ask Codex to address feedback'),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _submitting
              ? null
              : () {
                  Navigator.of(context).pop();
                },
          child: Text(_queued ? 'Close' : 'Cancel'),
        ),
        FilledButton.icon(
          onPressed: _submitting || _queued ? null : _submit,
          icon: _submitting
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send_rounded, size: 16),
          label: Text(_submitting ? 'Submitting' : 'Submit feedback'),
        ),
      ],
    );
  }
}

class _SddCodexActionDialog extends StatefulWidget {
  const _SddCodexActionDialog({
    required this.bridgeUrl,
    required this.request,
    required this.submitter,
    required this.onActionSubmitted,
  });

  final String bridgeUrl;
  final SddCodexActionRequest request;
  final SddCodexActionSubmitter submitter;
  final void Function(
    SddCodexActionSubmissionResult accepted,
    SddCodexActionRequest request,
  )
  onActionSubmitted;

  @override
  State<_SddCodexActionDialog> createState() => _SddCodexActionDialogState();
}

class _SddCodexActionDialogState extends State<_SddCodexActionDialog> {
  late final TextEditingController _promptController;
  bool _submitting = false;
  SddCodexActionSubmissionResult? _accepted;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    _promptController = TextEditingController(
      text: buildSddCodexActionPrompt(widget.request),
    );
  }

  @override
  void dispose() {
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty) {
      setState(() {
        _errorText = 'Write a prompt before submitting.';
      });
      return;
    }
    setState(() {
      _submitting = true;
      _errorText = null;
    });
    try {
      final accepted = await widget.submitter(
        widget.bridgeUrl,
        SddCodexActionDraft(request: widget.request, prompt: prompt),
      );
      if (!mounted) return;
      widget.onActionSubmitted(accepted, widget.request);
      setState(() {
        _accepted = accepted;
        _submitting = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _errorText = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final request = widget.request;
    final accepted = _accepted;
    return AlertDialog(
      title: Text(request.kind.label),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _FeedbackTargetSummary(target: request.target),
              if (request.linkedFeedbackIds.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  'Linked feedback: ${request.linkedFeedbackIds.join(', ')}',
                  style: const TextStyle(
                    color: _WorkbenchColors.secondaryText,
                    fontSize: 12,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: _promptController,
                enabled: !_submitting && accepted == null,
                minLines: 12,
                maxLines: 18,
                decoration: const InputDecoration(
                  labelText: 'Codex prompt',
                  alignLabelWithHint: true,
                ),
              ),
              if (_errorText != null) ...[
                const SizedBox(height: 10),
                Text(
                  _errorText!,
                  style: const TextStyle(color: _WorkbenchColors.warning),
                ),
              ],
              if (accepted != null) ...[
                const SizedBox(height: 10),
                Row(
                  children: <Widget>[
                    const Icon(
                      Icons.check_circle_outline_rounded,
                      color: _WorkbenchColors.primary,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        accepted.sessionId.isEmpty
                            ? 'Codex action submitted'
                            : 'Codex action submitted to session ${accepted.sessionId}',
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text(
                  'Close the Workbench to continue in the existing chat surface.',
                  style: TextStyle(
                    color: _WorkbenchColors.secondaryText,
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _submitting
              ? null
              : () {
                  Navigator.of(context).pop();
                },
          child: Text(accepted == null ? 'Cancel' : 'Close'),
        ),
        FilledButton.icon(
          onPressed: _submitting || accepted != null ? null : _submit,
          icon: _submitting
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send_rounded, size: 16),
          label: Text(_submitting ? 'Submitting' : 'Submit to Codex'),
        ),
      ],
    );
  }
}

class _FeedbackTargetSummary extends StatelessWidget {
  const _FeedbackTargetSummary({required this.target});

  final SddFeedbackTarget target;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            target.artifactTitle,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          Text(
            target.artifactPath,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _WorkbenchColors.secondaryText,
              fontSize: 12,
            ),
          ),
          if (target.specTitle != null) ...[
            const SizedBox(height: 4),
            Text(
              target.specTitle!,
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
              ),
            ),
          ],
          if (target.diagramType != null) ...[
            const SizedBox(height: 4),
            Text(
              '${target.diagramType} · ${target.diagramScope ?? 'diagram'}',
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FileHeader extends StatelessWidget {
  const _FileHeader({required this.title, required this.file, this.subtitle});

  final String title;
  final SddFile file;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final secondary = subtitle == null || subtitle!.trim().isEmpty
        ? '${file.path} - ${file.sizeBytes} bytes'
        : '${file.path} - $subtitle - ${file.sizeBytes} bytes';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 3),
        Text(
          secondary,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: _WorkbenchColors.secondaryText,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}

class _SourceBlock extends StatelessWidget {
  const _SourceBlock({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxHeight: 260),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: SingleChildScrollView(
        child: SelectableText(
          text,
          style: const TextStyle(
            fontFamily: 'monospace',
            color: _WorkbenchColors.sourceText,
            fontSize: 12,
          ),
        ),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.title, required this.detail});

  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text(
            detail,
            style: const TextStyle(color: _WorkbenchColors.secondaryText),
          ),
        ],
      ),
    );
  }
}

class _PanelCard extends StatelessWidget {
  const _PanelCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: child,
    );
  }
}
