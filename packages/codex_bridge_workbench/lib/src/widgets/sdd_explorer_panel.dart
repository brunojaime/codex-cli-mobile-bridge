import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/sdd_project.dart';
import '../models/sdd_submission_result.dart';
import '../services/mermaid_renderer.dart';
import '../services/sdd_explorer_client.dart';

typedef SddExplorerLoader = Future<SddProject?> Function(String bridgeUrl);
typedef SddMediaAttachmentPicker = Future<SddMediaAttachmentDraft?> Function();
typedef SddStructuredAttachmentPicker =
    Future<SddStagedMediaAttachment?> Function();
typedef SddImageCropper =
    Future<SddMediaAttachmentDraft> Function(
      SddStagedMediaAttachment source,
      SddMediaCropSelection selection,
    );
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
    this.invocationSource = 'codex_bridge_workbench',
    this.releaseTarget = 'target_workspace',
    this.targetWorkspaceName,
    this.hostWorkspacePath,
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
  final String invocationSource;
  final String releaseTarget;
  final String? targetWorkspaceName;
  final String? hostWorkspacePath;
  final String? specId;
  final String? specTitle;
  final String? diagramType;
  final String? diagramScope;

  bool get isDiagram => diagramType != null;

  String get feedbackKind => isDiagram ? 'sdd.diagram' : 'sdd.artifact';

  Map<String, Object?> toContextMetadata() {
    return <String, Object?>{
      'sdd': <String, Object?>{
        'invocationSource': invocationSource,
        'workspacePath': workspacePath,
        'targetWorkspacePath': workspacePath,
        if (targetWorkspaceName != null)
          'targetWorkspaceName': targetWorkspaceName,
        if (hostWorkspacePath != null) 'hostWorkspacePath': hostWorkspacePath,
        'releaseTarget': releaseTarget,
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
    ..writeln(
      '- For release, deploy, publish, or installable build requests, use '
      'target_workspace_path as the target repository by default.',
    )
    ..writeln(
      '- Do not release the Bridge/Workbench host repository unless the user '
      'explicitly asks for that host app.',
    )
    ..writeln('- Validate any path before reading or editing files.')
    ..writeln('- Do not invent mock data, placeholder URLs, or demo state.')
    ..writeln('- Keep SDD changes explicit and reviewable.')
    ..writeln()
    ..writeln('Context:')
    ..writeln('```yaml')
    ..writeln('invocation_source: ${target.invocationSource}')
    ..writeln('workspace_path: ${target.workspacePath}')
    ..writeln('target_workspace_path: ${target.workspacePath}')
    ..writeln('release_target: ${target.releaseTarget}')
    ..writeln('artifact_type: ${target.artifactType}')
    ..writeln('artifact_path: ${target.artifactPath}')
    ..writeln('artifact_title: ${target.artifactTitle}');
  if (target.targetWorkspaceName != null) {
    buffer.writeln('target_workspace_name: ${target.targetWorkspaceName}');
  }
  if (target.hostWorkspacePath != null) {
    buffer.writeln('host_workspace_path: ${target.hostWorkspacePath}');
  }
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
    this.metaWorkspacePath,
    this.metaWorkspaceLabel = 'Codex Bridge Workbench',
    this.diagramRenderer = const WebViewMermaidDiagramRenderer(),
    this.loader,
    this.specIntakeClient,
    this.mediaAttachmentPicker,
    this.audioAttachmentPicker,
    this.structuredAttachmentPicker,
    this.imageCropper,
    this.feedbackSubmitter,
    this.actionSubmitter,
  });

  final String bridgeUrl;
  final String? workspacePath;
  final String? metaWorkspacePath;
  final String metaWorkspaceLabel;
  final VoidCallback onClose;
  final MermaidDiagramRenderer diagramRenderer;
  final SddExplorerLoader? loader;
  final SddExplorerClient? specIntakeClient;
  final SddMediaAttachmentPicker? mediaAttachmentPicker;
  final SddMediaAttachmentPicker? audioAttachmentPicker;
  final SddStructuredAttachmentPicker? structuredAttachmentPicker;
  final SddImageCropper? imageCropper;
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
        oldWidget.metaWorkspacePath != widget.metaWorkspacePath ||
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
      return client.loadProject(workspacePath);
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
      child: Theme(
        data: _workbenchTheme(context),
        child: Material(
          color: _WorkbenchColors.background,
          elevation: 18,
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
                          bridgeUrl: widget.bridgeUrl,
                          project: project,
                          activity: _activity,
                          showOverviewCurator:
                              widget.specIntakeClient != null ||
                              widget.loader == null,
                          diagramRenderer: widget.diagramRenderer,
                          specIntakeClient: widget.specIntakeClient,
                          mediaAttachmentPicker: widget.mediaAttachmentPicker,
                          audioAttachmentPicker: widget.audioAttachmentPicker,
                          structuredAttachmentPicker:
                              widget.structuredAttachmentPicker,
                          imageCropper: widget.imageCropper,
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
            metaWorkspacePath: widget.metaWorkspacePath,
            metaWorkspaceLabel: widget.metaWorkspaceLabel,
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
  static const border = Color(0xFF405173);
  static const primary = Color(0xFF5EEAD4);
  static const onPrimary = Color(0xFF03201C);
  static const onBackground = Color(0xFFF4F7FB);
  static const secondaryText = Color(0xFFC1CBE0);
  static const warning = Color(0xFFFFD166);
  static const warningSurface = Color(0xFF342A14);
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
      prefixIconColor: _WorkbenchColors.secondaryText,
      suffixIconColor: _WorkbenchColors.secondaryText,
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
      shadowColor: Colors.black,
      textStyle: const TextStyle(color: _WorkbenchColors.onBackground),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: _WorkbenchColors.surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: _WorkbenchColors.primary.withValues(alpha: 0.18),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return IconThemeData(
          color: selected
              ? _WorkbenchColors.primary
              : _WorkbenchColors.secondaryText,
          size: selected ? 25 : 23,
        );
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return TextStyle(
          color: selected
              ? _WorkbenchColors.primary
              : _WorkbenchColors.secondaryText,
          fontSize: 10.5,
          fontWeight: selected ? FontWeight.w900 : FontWeight.w700,
        );
      }),
      height: 64,
    ),
    dropdownMenuTheme: DropdownMenuThemeData(
      textStyle: const TextStyle(color: _WorkbenchColors.onBackground),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: _WorkbenchColors.sourceBackground,
        labelStyle: const TextStyle(color: _WorkbenchColors.secondaryText),
        hintStyle: const TextStyle(color: _WorkbenchColors.secondaryText),
        prefixIconColor: _WorkbenchColors.secondaryText,
        suffixIconColor: _WorkbenchColors.secondaryText,
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
      ),
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
      padding: const EdgeInsets.fromLTRB(14, 2, 4, 2),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: _WorkbenchColors.border)),
      ),
      child: Row(
        children: <Widget>[
          const Icon(
            Icons.account_tree_outlined,
            size: 18,
            color: _WorkbenchColors.primary,
          ),
          const SizedBox(width: 8),
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
            visualDensity: VisualDensity.compact,
            constraints: const BoxConstraints.tightFor(width: 38, height: 34),
            padding: EdgeInsets.zero,
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

class _SddProjectView extends StatefulWidget {
  const _SddProjectView({
    required this.bridgeUrl,
    required this.project,
    required this.activity,
    required this.showOverviewCurator,
    required this.diagramRenderer,
    required this.specIntakeClient,
    required this.mediaAttachmentPicker,
    required this.audioAttachmentPicker,
    required this.structuredAttachmentPicker,
    required this.imageCropper,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final String bridgeUrl;
  final SddProject project;
  final SddDashboardActivity activity;
  final bool showOverviewCurator;
  final MermaidDiagramRenderer diagramRenderer;
  final SddExplorerClient? specIntakeClient;
  final SddMediaAttachmentPicker? mediaAttachmentPicker;
  final SddMediaAttachmentPicker? audioAttachmentPicker;
  final SddStructuredAttachmentPicker? structuredAttachmentPicker;
  final SddImageCropper? imageCropper;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  State<_SddProjectView> createState() => _SddProjectViewState();
}

class _SddProjectViewState extends State<_SddProjectView> {
  int _selectedIndex = 0;

  void _selectTab(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  void _openSpecIntake() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Theme(
          data: _workbenchTheme(dialogContext),
          child: _SpecIntakeDialog(
            bridgeUrl: widget.bridgeUrl,
            project: widget.project,
            client: widget.specIntakeClient,
            mediaAttachmentPicker: widget.mediaAttachmentPicker,
            audioAttachmentPicker: widget.audioAttachmentPicker,
            structuredAttachmentPicker: widget.structuredAttachmentPicker,
            imageCropper: widget.imageCropper,
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final client =
        widget.specIntakeClient ?? SddExplorerClient(baseUrl: widget.bridgeUrl);
    const destinations = <_WorkbenchNavigationDestination>[
      _WorkbenchNavigationDestination(
        label: 'Overview',
        compactLabel: 'Home',
        icon: Icons.dashboard_outlined,
        selectedIcon: Icons.dashboard_rounded,
      ),
      _WorkbenchNavigationDestination(
        label: 'Kanban',
        compactLabel: 'Kan',
        icon: Icons.view_kanban_outlined,
        selectedIcon: Icons.view_kanban_rounded,
      ),
      _WorkbenchNavigationDestination(
        label: 'Specs',
        compactLabel: 'Spec',
        icon: Icons.view_list_outlined,
        selectedIcon: Icons.view_list_rounded,
      ),
      _WorkbenchNavigationDestination(
        label: 'Diagrams',
        compactLabel: 'Diag',
        icon: Icons.account_tree_outlined,
        selectedIcon: Icons.account_tree_rounded,
      ),
      _WorkbenchNavigationDestination(
        label: 'Governance',
        compactLabel: 'Gov',
        icon: Icons.verified_outlined,
        selectedIcon: Icons.verified_rounded,
      ),
    ];
    final pages = <Widget>[
      _OverviewTab(
        project: widget.project,
        activity: widget.activity,
        client: client,
        showCuratorUpdate: widget.showOverviewCurator,
        onNavigate: _selectTab,
      ),
      _KanbanTab(client: client, project: widget.project),
      _SpecsTab(
        bridgeUrl: widget.bridgeUrl,
        project: widget.project,
        diagramRenderer: widget.diagramRenderer,
        specIntakeClient: widget.specIntakeClient,
        mediaAttachmentPicker: widget.mediaAttachmentPicker,
        audioAttachmentPicker: widget.audioAttachmentPicker,
        structuredAttachmentPicker: widget.structuredAttachmentPicker,
        imageCropper: widget.imageCropper,
        onFeedback: widget.onFeedback,
        onCodexAction: widget.onCodexAction,
      ),
      _DiagramsTab(
        project: widget.project,
        diagramRenderer: widget.diagramRenderer,
        onFeedback: widget.onFeedback,
        onCodexAction: widget.onCodexAction,
      ),
      _GovernanceTab(project: widget.project),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final useBottomNavigation = constraints.maxWidth < 620;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _WorkbenchProjectHeader(project: widget.project),
            if (!useBottomNavigation)
              _WorkbenchTopNavigation(
                destinations: destinations,
                selectedIndex: _selectedIndex,
                onSelected: _selectTab,
              ),
            Expanded(
              child: Stack(
                children: <Widget>[
                  Positioned.fill(child: pages[_selectedIndex]),
                  if (_selectedIndex == 2)
                    Positioned(
                      right: 16,
                      bottom: 16,
                      child: FloatingActionButton(
                        heroTag: 'sdd-spec-intake-fab',
                        tooltip: 'New functionality',
                        onPressed: _openSpecIntake,
                        child: const Icon(Icons.add_rounded),
                      ),
                    ),
                ],
              ),
            ),
            if (useBottomNavigation)
              _WorkbenchBottomNavigation(
                destinations: destinations,
                selectedIndex: _selectedIndex,
                onSelected: _selectTab,
              ),
          ],
        );
      },
    );
  }
}

class _WorkbenchNavigationDestination {
  const _WorkbenchNavigationDestination({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    this.compactLabel,
  });

  final String label;
  final String? compactLabel;
  final IconData icon;
  final IconData selectedIcon;
}

class _WorkbenchTopNavigation extends StatelessWidget {
  const _WorkbenchTopNavigation({
    required this.destinations,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<_WorkbenchNavigationDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: _WorkbenchColors.border),
          bottom: BorderSide(color: _WorkbenchColors.border),
        ),
      ),
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            children: <Widget>[
              for (var index = 0; index < destinations.length; index++)
                Expanded(
                  child: _WorkbenchTopNavigationButton(
                    destination: destinations[index],
                    selected: selectedIndex == index,
                    onTap: () => onSelected(index),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WorkbenchTopNavigationButton extends StatelessWidget {
  const _WorkbenchTopNavigationButton({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final _WorkbenchNavigationDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? _WorkbenchColors.primary
        : _WorkbenchColors.secondaryText;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: Material(
        color: selected
            ? _WorkbenchColors.primary.withValues(alpha: 0.08)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          borderRadius: BorderRadius.circular(6),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 9),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Icon(
                  selected ? destination.selectedIcon : destination.icon,
                  color: color,
                  size: 17,
                ),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(
                    destination.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: color, fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _WorkbenchBottomNavigation extends StatelessWidget {
  const _WorkbenchBottomNavigation({
    required this.destinations,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<_WorkbenchNavigationDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: _WorkbenchColors.surface,
        border: Border(top: BorderSide(color: _WorkbenchColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          key: const Key('sdd-workbench-bottom-navigation'),
          height: 64,
          child: Row(
            children: <Widget>[
              for (var index = 0; index < destinations.length; index++)
                Expanded(
                  child: _WorkbenchBottomNavigationButton(
                    destination: destinations[index],
                    selected: selectedIndex == index,
                    onTap: () => onSelected(index),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WorkbenchBottomNavigationButton extends StatelessWidget {
  const _WorkbenchBottomNavigationButton({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final _WorkbenchNavigationDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? _WorkbenchColors.primary
        : _WorkbenchColors.secondaryText;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                selected ? destination.selectedIcon : destination.icon,
                color: color,
                size: 22,
              ),
              const SizedBox(height: 3),
              Text(
                destination.compactLabel ?? destination.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: color,
                  fontSize: 11,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
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
      padding: const EdgeInsets.fromLTRB(14, 5, 14, 2),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              _projectDisplayName(project),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: _WorkbenchColors.onBackground,
                fontSize: 14,
                fontWeight: FontWeight.w900,
              ),
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
    required this.client,
    required this.showCuratorUpdate,
    required this.onNavigate,
  });

  final SddProject project;
  final SddDashboardActivity activity;
  final SddExplorerClient client;
  final bool showCuratorUpdate;
  final ValueChanged<int> onNavigate;

  @override
  Widget build(BuildContext context) {
    final diagrams = _allDiagrams(project);
    final progress = _projectTaskProgress(project);
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
      children: <Widget>[
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            _MetricTile(
              label: 'Constitution',
              value: project.constitution == null ? 'Missing' : 'Present',
              warning: project.constitution == null,
              onTap: () => onNavigate(0),
            ),
            _MetricTile(
              label: 'Specs',
              value: '${project.specs.length}',
              onTap: () => onNavigate(2),
            ),
            _MetricTile(
              label: 'Diagrams',
              value: '${diagrams.length}',
              onTap: () => onNavigate(3),
            ),
            _MetricTile(
              label: 'Tasks',
              value: progress == null
                  ? 'Source only'
                  : '${progress.completed}/${progress.total}',
              warning: progress == null || progress.completed < progress.total,
              onTap: () => onNavigate(1),
            ),
            _MetricTile(
              label: 'Slice docs',
              value: '${_sliceDocCount(project)}',
              onTap: () => onNavigate(2),
            ),
          ],
        ),
        const SizedBox(height: 14),
        if (showCuratorUpdate && MediaQuery.sizeOf(context).width >= 620)
          _LatestCuratorOverviewCard(
            client: client,
            project: project,
            onOpenKanban: () => onNavigate(1),
          ),
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

class _LatestCuratorOverviewCard extends StatelessWidget {
  const _LatestCuratorOverviewCard({
    required this.client,
    required this.project,
    required this.onOpenKanban,
  });

  final SddExplorerClient client;
  final SddProject project;
  final VoidCallback onOpenKanban;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<SddWorkbenchKanban>(
      future: client.getKanban(workspacePath: project.workspacePath),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _PanelCard(
            child: _InlineLoading(label: 'Loading Curator update'),
          );
        }
        if (snapshot.hasError) {
          return _PanelCard(
            child: Text(
              'Curator update unavailable: ${snapshot.error}',
              style: const TextStyle(color: _WorkbenchColors.secondaryText),
            ),
          );
        }
        final update = snapshot.data?.latestUpdate;
        if (update == null) {
          return const SizedBox.shrink();
        }
        return _PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Icon(
                    Icons.auto_awesome_outlined,
                    size: 18,
                    color: _WorkbenchColors.primary,
                  ),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'Latest Curator update',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                  TextButton(
                    onPressed: onOpenKanban,
                    child: const Text('Kanban'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                update.title,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(
                update.summary,
                style: const TextStyle(color: _WorkbenchColors.secondaryText),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _KanbanTab extends StatefulWidget {
  const _KanbanTab({required this.client, required this.project});

  final SddExplorerClient client;
  final SddProject project;

  @override
  State<_KanbanTab> createState() => _KanbanTabState();
}

class _KanbanTabState extends State<_KanbanTab> {
  late Future<SddWorkbenchKanban> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void didUpdateWidget(_KanbanTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.project.workspacePath != widget.project.workspacePath ||
        oldWidget.client != widget.client) {
      _future = _load();
    }
  }

  Future<SddWorkbenchKanban> _load() {
    return widget.client.getKanban(workspacePath: widget.project.workspacePath);
  }

  void _refresh() {
    setState(() {
      _future = widget.client.refreshKanban(
        workspacePath: widget.project.workspacePath,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<SddWorkbenchKanban>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _KanbanLoading();
        }
        if (snapshot.hasError) {
          return _KanbanError(
            errorText: snapshot.error.toString(),
            onRetry: _refresh,
          );
        }
        final kanban = snapshot.data;
        if (kanban == null || kanban.board.cards.isEmpty) {
          return _KanbanEmpty(onRetry: _refresh);
        }
        return _KanbanContent(
          kanban: kanban,
          client: widget.client,
          workspacePath: widget.project.workspacePath,
          onRefresh: _refresh,
        );
      },
    );
  }
}

class _KanbanContent extends StatelessWidget {
  const _KanbanContent({
    required this.kanban,
    required this.client,
    required this.workspacePath,
    required this.onRefresh,
  });

  final SddWorkbenchKanban kanban;
  final SddExplorerClient client;
  final String workspacePath;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 720;
        final board = compact
            ? Column(
                children: <Widget>[
                  for (final column in kanban.board.columns)
                    _KanbanColumnView(column: column, kanban: kanban),
                ],
              )
            : SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    for (final column in kanban.board.columns)
                      SizedBox(
                        width: 238,
                        child: _KanbanColumnView(
                          column: column,
                          kanban: kanban,
                        ),
                      ),
                  ],
                ),
              );
        return ListView(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
          children: <Widget>[
            _KanbanHeader(
              kanban: kanban,
              client: client,
              workspacePath: workspacePath,
              onRefresh: onRefresh,
            ),
            if (kanban.latestUpdate != null)
              _CuratorUpdatePanel(update: kanban.latestUpdate!),
            board,
          ],
        );
      },
    );
  }
}

class _KanbanHeader extends StatelessWidget {
  const _KanbanHeader({
    required this.kanban,
    required this.client,
    required this.workspacePath,
    required this.onRefresh,
  });

  final SddWorkbenchKanban kanban;
  final SddExplorerClient client;
  final String workspacePath;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.view_kanban_outlined,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  kanban.scope.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontWeight: FontWeight.w900,
                    fontSize: 16,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Refresh Kanban',
                onPressed: onRefresh,
                icon: const Icon(Icons.refresh_rounded),
              ),
              TextButton.icon(
                onPressed: () => _showKanbanHistory(
                  context,
                  client: client,
                  workspacePath: workspacePath,
                  scopeId: kanban.scope.id,
                ),
                icon: const Icon(Icons.history_rounded, size: 18),
                label: const Text('View history'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              _StatusPill(label: 'Scope', value: kanban.scope.type),
              _StatusPill(label: 'Snapshot', value: kanban.board.snapshotId),
              _StatusPill(
                label: 'Polling',
                value:
                    '${kanban.board.refresh['pollingFallbackSeconds'] ?? 30}s',
              ),
              _StatusPill(
                label: 'Read-only Curator',
                value: kanban.curator['readOnly'] == true ? 'on' : 'off',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CuratorUpdatePanel extends StatelessWidget {
  const _CuratorUpdatePanel({required this.update});

  final SddCuratorUpdate update;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Curator update',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          Text(
            update.title,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          Text(update.summary),
          if (update.blockers.isNotEmpty) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              'Blockers: ${update.blockers.join(', ')}',
              style: const TextStyle(color: _WorkbenchColors.warning),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            update.nextWatch,
            style: const TextStyle(color: _WorkbenchColors.secondaryText),
          ),
        ],
      ),
    );
  }
}

class _KanbanColumnView extends StatelessWidget {
  const _KanbanColumnView({required this.column, required this.kanban});

  final SddKanbanColumn column;
  final SddWorkbenchKanban kanban;

  @override
  Widget build(BuildContext context) {
    final cards = column.cardIds
        .map(kanban.board.cardById)
        .whereType<SddKanbanCard>()
        .toList(growable: false);
    return Container(
      margin: const EdgeInsets.only(right: 10, bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  column.label,
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              _CountBadge(count: column.count),
            ],
          ),
          const SizedBox(height: 8),
          if (cards.isEmpty)
            const Text(
              'No cards',
              style: TextStyle(color: _WorkbenchColors.secondaryText),
            )
          else
            for (final card in cards) _KanbanCardView(card: card),
        ],
      ),
    );
  }
}

class _KanbanCardView extends StatelessWidget {
  const _KanbanCardView({required this.card});

  final SddKanbanCard card;

  @override
  Widget build(BuildContext context) {
    final warning = card.column == 'blocked';
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: warning
            ? _WorkbenchColors.warningSurface
            : _WorkbenchColors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: warning ? _WorkbenchColors.warning : _WorkbenchColors.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(card.title, style: const TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: <Widget>[
              _SmallBadge(card.type),
              _SmallBadge(card.status),
              _SmallBadge(card.confirmed ? 'confirmed' : card.confidence),
              if (card.inferred) const _SmallBadge('inferred'),
              for (final badge in card.badges.take(3)) _SmallBadge(badge),
            ],
          ),
          if (card.detail.isNotEmpty) ...<Widget>[
            const SizedBox(height: 6),
            Text(
              card.detail,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
              ),
            ),
          ],
          const SizedBox(height: 6),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  card.sourcePath,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _WorkbenchColors.secondaryText,
                    fontSize: 11,
                  ),
                ),
              ),
              if (card.manualCommands.isNotEmpty)
                IconButton(
                  tooltip: 'Copy manual command',
                  onPressed: () => Clipboard.setData(
                    ClipboardData(text: card.manualCommands.join(' ')),
                  ),
                  icon: const Icon(Icons.content_copy_rounded, size: 16),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InlineLoading extends StatelessWidget {
  const _InlineLoading({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        const SizedBox(width: 10),
        Text(label),
      ],
    );
  }
}

class _KanbanLoading extends StatelessWidget {
  const _KanbanLoading();

  @override
  Widget build(BuildContext context) {
    return const Center(child: _InlineLoading(label: 'Loading Kanban'));
  }
}

class _KanbanError extends StatelessWidget {
  const _KanbanError({required this.errorText, required this.onRetry});

  final String errorText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
      children: <Widget>[
        _InfoCard(title: 'Kanban unavailable', detail: errorText),
        OutlinedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: const Text('Retry Kanban'),
        ),
      ],
    );
  }
}

class _KanbanEmpty extends StatelessWidget {
  const _KanbanEmpty({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
      children: <Widget>[
        const _InfoCard(
          title: 'No Kanban cards',
          detail:
              'No SDD tasks, run steps, or Project Factory evidence is visible.',
        ),
        OutlinedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: const Text('Refresh Kanban'),
        ),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: _WorkbenchColors.background,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Text('$label: $value', style: const TextStyle(fontSize: 12)),
    );
  }
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: _WorkbenchColors.secondaryText,
          fontSize: 11,
        ),
      ),
    );
  }
}

class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 26,
      height: 22,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: _WorkbenchColors.primary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        '$count',
        style: const TextStyle(
          color: _WorkbenchColors.primary,
          fontWeight: FontWeight.w900,
          fontSize: 12,
        ),
      ),
    );
  }
}

void _showKanbanHistory(
  BuildContext context, {
  required SddExplorerClient client,
  required String workspacePath,
  required String scopeId,
}) {
  showDialog<void>(
    context: context,
    builder: (dialogContext) {
      return Theme(
        data: _workbenchTheme(dialogContext),
        child: AlertDialog(
          title: const Text('Curator history'),
          content: SizedBox(
            width: 520,
            child: FutureBuilder<SddKanbanHistory>(
              future: client.getKanbanHistory(
                workspacePath: workspacePath,
                scopeId: scopeId,
              ),
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const _InlineLoading(label: 'Loading history');
                }
                if (snapshot.hasError) {
                  return Text('History unavailable: ${snapshot.error}');
                }
                final items =
                    snapshot.data?.items ?? const <SddCuratorUpdate>[];
                if (items.isEmpty) {
                  return const Text('No Curator updates yet.');
                }
                return SizedBox(
                  height: 360,
                  child: ListView.separated(
                    itemCount: items.length,
                    separatorBuilder: (context, index) =>
                        const Divider(color: _WorkbenchColors.border),
                    itemBuilder: (context, index) {
                      final item = items[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(item.title),
                        subtitle: Text(
                          '${item.timestamp}\n${item.summary}',
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                        isThreeLine: true,
                        trailing: item.blockers.isEmpty
                            ? null
                            : const Icon(
                                Icons.warning_amber_rounded,
                                color: _WorkbenchColors.warning,
                              ),
                        onTap: () => _showKanbanHistoryDetail(
                          dialogContext,
                          client: client,
                          workspacePath: workspacePath,
                          scopeId: scopeId,
                          updateId: item.id,
                        ),
                      );
                    },
                  ),
                );
              },
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    },
  );
}

void _showKanbanHistoryDetail(
  BuildContext context, {
  required SddExplorerClient client,
  required String workspacePath,
  required String scopeId,
  required String updateId,
}) {
  showDialog<void>(
    context: context,
    builder: (dialogContext) {
      return Theme(
        data: _workbenchTheme(dialogContext),
        child: AlertDialog(
          title: const Text('Curator update detail'),
          content: SizedBox(
            width: 520,
            child: FutureBuilder<SddCuratorUpdate>(
              future: client.getKanbanHistoryItem(
                updateId: updateId,
                workspacePath: workspacePath,
                scopeId: scopeId,
              ),
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const _InlineLoading(label: 'Loading update');
                }
                if (snapshot.hasError) {
                  return Text('Update unavailable: ${snapshot.error}');
                }
                final update = snapshot.data;
                if (update == null) return const Text('Update not found.');
                return SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        update.title,
                        style: const TextStyle(fontWeight: FontWeight.w900),
                      ),
                      const SizedBox(height: 8),
                      Text(update.summary),
                      const SizedBox(height: 10),
                      _KeyValueLine(
                        label: 'Changed',
                        value: update.changedCards.isEmpty
                            ? 'None'
                            : update.changedCards.join(', '),
                      ),
                      _KeyValueLine(
                        label: 'Blockers',
                        value: update.blockers.isEmpty
                            ? 'None'
                            : update.blockers.join(', '),
                        warning: update.blockers.isNotEmpty,
                      ),
                      _KeyValueLine(label: 'Next', value: update.nextWatch),
                    ],
                  ),
                );
              },
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    },
  );
}

class _SpecsTab extends StatefulWidget {
  const _SpecsTab({
    required this.bridgeUrl,
    required this.project,
    required this.diagramRenderer,
    required this.specIntakeClient,
    required this.mediaAttachmentPicker,
    required this.audioAttachmentPicker,
    required this.structuredAttachmentPicker,
    required this.imageCropper,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final String bridgeUrl;
  final SddProject project;
  final MermaidDiagramRenderer diagramRenderer;
  final SddExplorerClient? specIntakeClient;
  final SddMediaAttachmentPicker? mediaAttachmentPicker;
  final SddMediaAttachmentPicker? audioAttachmentPicker;
  final SddStructuredAttachmentPicker? structuredAttachmentPicker;
  final SddImageCropper? imageCropper;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  State<_SpecsTab> createState() => _SpecsTabState();
}

class _SpecsTabState extends State<_SpecsTab> {
  final ScrollController _detailScrollController = ScrollController();
  late SddProject _project;
  final Set<String> _loadingSpecIds = <String>{};
  final Map<String, String> _specErrors = <String, String>{};
  _SpecArtifactSelection _selection = const _SpecArtifactSelection(
    specIndex: 0,
    kind: _SpecArtifactKind.spec,
  );
  bool _showDetail = false;

  @override
  void initState() {
    super.initState();
    _project = widget.project;
  }

  @override
  void didUpdateWidget(_SpecsTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.project != widget.project) {
      _project = widget.project;
      _selection = _validatedSelection(_selection, _project.specs);
      _loadingSpecIds.clear();
      _specErrors.clear();
      _showDetail = false;
    }
  }

  @override
  void dispose() {
    _detailScrollController.dispose();
    super.dispose();
  }

  void _select(_SpecArtifactSelection selection, {bool showDetail = true}) {
    final nextSelection = _validatedSelection(selection, _project.specs);
    setState(() {
      _selection = nextSelection;
      _showDetail = showDetail;
    });
    if (showDetail) {
      _hydrateSpecIfNeeded(nextSelection.specIndex);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_detailScrollController.hasClients) {
          _detailScrollController.jumpTo(0);
        }
      });
    }
  }

  Future<void> _hydrateSpecIfNeeded(int specIndex) async {
    if (specIndex < 0 || specIndex >= _project.specs.length) return;
    final spec = _project.specs[specIndex];
    if (!_specNeedsDetail(spec) || _loadingSpecIds.contains(spec.id)) return;
    setState(() {
      _loadingSpecIds.add(spec.id);
      _specErrors.remove(spec.id);
    });
    final client =
        widget.specIntakeClient ?? SddExplorerClient(baseUrl: widget.bridgeUrl);
    try {
      final detailed = await client.getSpec(_project.workspacePath, spec.id);
      if (!mounted) return;
      setState(() {
        final specs = List<SddSpec>.of(_project.specs);
        final replacementIndex = specs.indexWhere((item) => item.id == spec.id);
        if (replacementIndex != -1) {
          specs[replacementIndex] = detailed;
          _project = _project.copyWith(specs: specs);
          _selection = _validatedSelection(_selection, _project.specs);
        }
        _loadingSpecIds.remove(spec.id);
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loadingSpecIds.remove(spec.id);
        _specErrors[spec.id] = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final specs = _project.specs;
    if (specs.isEmpty) {
      return const SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(14, 12, 14, 96),
        child: _InfoCard(
          title: 'No specs',
          detail: 'This project has no readable SDD specs yet.',
        ),
      );
    }
    final selection = _validatedSelection(_selection, specs);
    final selectedSpec = specs[selection.specIndex];
    final selectedSpecLoading =
        _loadingSpecIds.contains(selectedSpec.id) &&
        _specNeedsDetail(selectedSpec);
    final selectedSpecError = _specErrors[selectedSpec.id];
    final showSpecFileBeforeNavigator =
        selection.kind == _SpecArtifactKind.treeSpec;
    if (_showDetail) {
      return SingleChildScrollView(
        controller: _detailScrollController,
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _SelectedSpecSummary(
              spec: selectedSpec,
              onBack: () => setState(() => _showDetail = false),
            ),
            const SizedBox(height: 10),
            if (selectedSpecLoading) ...[
              const _InfoCard(
                title: 'Loading spec detail',
                detail:
                    'Fetching plans, tasks, diagrams, and files for this spec.',
              ),
              const SizedBox(height: 10),
            ] else if (selectedSpecError != null) ...[
              _SpecDetailErrorCard(
                errorText: selectedSpecError,
                onRetry: () => _hydrateSpecIfNeeded(selection.specIndex),
              ),
              const SizedBox(height: 10),
            ],
            if (showSpecFileBeforeNavigator) ...[
              _SpecArtifactInspector(
                project: _project,
                spec: selectedSpec,
                selection: selection,
                showHeading: false,
                diagramRenderer: widget.diagramRenderer,
                onFeedback: widget.onFeedback,
                onCodexAction: widget.onCodexAction,
                onSelected: _select,
              ),
              const SizedBox(height: 10),
            ],
            _SpecTraceNavigator(
              specs: specs,
              selection: selection,
              onSelected: _select,
              title: 'Inside this spec',
              allowSpecSwitch: false,
            ),
            if (!showSpecFileBeforeNavigator) ...[
              const SizedBox(height: 10),
              _SpecArtifactInspector(
                project: _project,
                spec: selectedSpec,
                selection: selection,
                showHeading: false,
                diagramRenderer: widget.diagramRenderer,
                onFeedback: widget.onFeedback,
                onCodexAction: widget.onCodexAction,
                onSelected: _select,
              ),
            ],
          ],
        ),
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 96),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _SpecListOverview(
            specs: specs,
            selection: selection,
            onSelected: (index) => _select(
              _SpecArtifactSelection(
                specIndex: index,
                kind: _firstAvailableArtifact(specs[index]),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SpecIntakeDialog extends StatelessWidget {
  const _SpecIntakeDialog({
    required this.bridgeUrl,
    required this.project,
    this.client,
    this.mediaAttachmentPicker,
    this.audioAttachmentPicker,
    this.structuredAttachmentPicker,
    this.imageCropper,
  });

  final String bridgeUrl;
  final SddProject project;
  final SddExplorerClient? client;
  final SddMediaAttachmentPicker? mediaAttachmentPicker;
  final SddMediaAttachmentPicker? audioAttachmentPicker;
  final SddStructuredAttachmentPicker? structuredAttachmentPicker;
  final SddImageCropper? imageCropper;

  @override
  Widget build(BuildContext context) {
    return Dialog.fullscreen(
      backgroundColor: _WorkbenchColors.background,
      child: Scaffold(
        backgroundColor: _WorkbenchColors.background,
        appBar: AppBar(
          backgroundColor: _WorkbenchColors.surface,
          surfaceTintColor: Colors.transparent,
          title: const Text('Spec intake'),
          actions: <Widget>[
            IconButton(
              tooltip: 'Close spec intake',
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.close_rounded),
            ),
          ],
        ),
        body: SafeArea(
          top: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: _SpecIntakeComposer(
                  bridgeUrl: bridgeUrl,
                  project: project,
                  client: client,
                  mediaAttachmentPicker: mediaAttachmentPicker,
                  audioAttachmentPicker: audioAttachmentPicker,
                  structuredAttachmentPicker: structuredAttachmentPicker,
                  imageCropper: imageCropper,
                  initiallyExpanded: true,
                  showHeader: false,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SpecIntakeComposer extends StatefulWidget {
  const _SpecIntakeComposer({
    required this.bridgeUrl,
    required this.project,
    this.client,
    this.mediaAttachmentPicker,
    this.audioAttachmentPicker,
    this.structuredAttachmentPicker,
    this.imageCropper,
    this.initiallyExpanded = false,
    this.showHeader = true,
  });

  final String bridgeUrl;
  final SddProject project;
  final SddExplorerClient? client;
  final SddMediaAttachmentPicker? mediaAttachmentPicker;
  final SddMediaAttachmentPicker? audioAttachmentPicker;
  final SddStructuredAttachmentPicker? structuredAttachmentPicker;
  final SddImageCropper? imageCropper;
  final bool initiallyExpanded;
  final bool showHeader;

  @override
  State<_SpecIntakeComposer> createState() => _SpecIntakeComposerState();
}

class _SpecIntakeComposerState extends State<_SpecIntakeComposer> {
  final TextEditingController _textController = TextEditingController();
  SddSpecIntakeMode _mode = SddSpecIntakeMode.newSpec;
  String _artifact = 'tasks';
  String? _selectedSpecId;
  bool _busy = false;
  String? _error;
  SddSpecIntakePlan? _preview;
  SddSpecIntakeApplyResult? _apply;
  SddCodexJobStatus? _job;
  SddCodexJobReview? _review;
  SddCodexJobApplyResult? _reviewApply;
  SddActivitySnapshot? _activity;
  final List<SddStagedMediaAttachment> _attachments =
      <SddStagedMediaAttachment>[];
  String? _attachmentStatus;
  late bool _expanded;

  SddExplorerClient get _client =>
      widget.client ?? SddExplorerClient(baseUrl: widget.bridgeUrl);

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
    _selectedSpecId = widget.project.specs.isEmpty
        ? null
        : widget.project.specs.first.id;
  }

  @override
  void didUpdateWidget(_SpecIntakeComposer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.project.specs.any((spec) => spec.id == _selectedSpecId)) {
      _selectedSpecId = widget.project.specs.isEmpty
          ? null
          : widget.project.specs.first.id;
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<void> _dryRun() async {
    await _run(() async {
      final result = await _client.dryRunSpecIntake(_draft());
      setState(() {
        _preview = result;
        _clearGeneratedOutput();
      });
    });
  }

  Future<void> _applyPreview() async {
    await _run(() async {
      final result = await _client.applySpecIntake(_draft());
      setState(() {
        _apply = result;
        _job = result.job;
        _activity =
            result.job?.activity ?? _localActivity('apply', result.status);
        _review = null;
        _reviewApply = null;
      });
    });
  }

  Future<void> _attachImage() async {
    final picker = widget.mediaAttachmentPicker;
    if (picker == null) {
      return;
    }
    await _attachMedia(picker: picker, kind: 'image');
  }

  Future<void> _attachAudio() async {
    final picker = widget.audioAttachmentPicker;
    if (picker == null) {
      return;
    }
    await _attachMedia(picker: picker, kind: 'audio');
  }

  Future<void> _attachStructured() async {
    final picker = widget.structuredAttachmentPicker;
    if (picker == null) {
      return;
    }
    await _run(() async {
      final attachment = await picker();
      if (attachment == null) return;
      setState(() {
        _attachments.add(attachment);
        _attachmentStatus = 'staged: ${attachment.mediaKind}';
        _preview = null;
        _clearGeneratedOutput();
      });
    });
  }

  Future<void> _attachMedia({
    required SddMediaAttachmentPicker picker,
    required String kind,
  }) async {
    await _run(() async {
      final attachment = await picker();
      if (attachment == null) return;
      final staged = await _client.uploadSpecMedia(
        workspacePath: widget.project.workspacePath,
        attachment: attachment,
        kind: kind,
      );
      setState(() {
        _attachments.add(staged);
        _attachmentStatus = 'staged: ${staged.filename}';
        _preview = null;
        _clearGeneratedOutput();
      });
    });
  }

  Future<void> _removeAttachment(int index) async {
    if (index < 0 || index >= _attachments.length) return;
    final attachment = _attachments[index];
    final stagedPath = attachment.stagedPath;
    await _run(() async {
      if (stagedPath != null && stagedPath.isNotEmpty) {
        await _client.deleteSpecMedia(
          workspacePath: widget.project.workspacePath,
          stagedPath: stagedPath,
        );
      }
      setState(() {
        if (index < _attachments.length && _attachments[index] == attachment) {
          _attachments.removeAt(index);
        } else {
          _attachments.remove(attachment);
        }
        _attachmentStatus = 'deleted: ${attachment.filename}';
        _preview = null;
        _clearGeneratedOutput();
      });
    });
  }

  Future<void> _annotateAttachment(int index) async {
    if (index < 0 || index >= _attachments.length) return;
    final source = _attachments[index];
    if (!source.isImage || source.previewBytes.isEmpty) {
      setState(() {
        _attachmentStatus = 'blocked: image preview unavailable';
      });
      return;
    }
    final region = await showDialog<SddMediaCropSelection>(
      context: context,
      builder: (context) => _MediaRegionDialog(source: source),
    );
    if (region == null) return;
    final sourceRef =
        source.intakeItem['payload_ref']?.toString() ?? source.stagedPath;
    if (sourceRef == null || sourceRef.isEmpty) {
      setState(() {
        _attachmentStatus = 'blocked: image payload_ref missing';
      });
      return;
    }
    if (region.generateCrop) {
      await _run(() async {
        final cropDraft = await (widget.imageCropper ?? _cropImageDraft)(
          source,
          region,
        );
        final crop = await _client.uploadSpecMedia(
          workspacePath: widget.project.workspacePath,
          attachment: cropDraft,
          kind: 'crop',
          sourceRef: sourceRef,
          region: region.toJson(),
        );
        setState(() {
          _attachments.removeWhere(
            (attachment) =>
                attachment.mediaKind == 'crop' &&
                attachment.intakeItem['source_ref'] == sourceRef,
          );
          final sourceIndex = _attachments.indexOf(source);
          _attachments.insert(
            sourceIndex < 0 ? _attachments.length : sourceIndex + 1,
            crop,
          );
          _attachmentStatus = 'staged: crop image';
          _preview = null;
          _clearGeneratedOutput();
        });
      });
      return;
    }
    final marker = _markedRegionAttachment(source, sourceRef, region);
    setState(() {
      _attachments.removeWhere(
        (attachment) =>
            attachment.mediaKind == 'marked_region' &&
            attachment.intakeItem['source_ref'] == sourceRef,
      );
      final sourceIndex = _attachments.indexOf(source);
      _attachments.insert(
        sourceIndex < 0 ? _attachments.length : sourceIndex + 1,
        marker,
      );
      _attachmentStatus = 'staged: marked region';
      _preview = null;
      _clearGeneratedOutput();
    });
  }

  void _clearGeneratedOutput() {
    _apply = null;
    _job = null;
    _review = null;
    _reviewApply = null;
    _activity = null;
  }

  Future<void> _runJob() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final job = await _client.runCodexJob(jobId);
      setState(() {
        _job = job;
        _activity = job.activity ?? _localActivity('job', job.status);
        _review = null;
        _reviewApply = null;
      });
    });
  }

  Future<void> _refreshJobActivity() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final activity = await _client.getCodexJobActivity(jobId);
      setState(() {
        _activity = activity;
      });
    });
  }

  Future<void> _cancelJob() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final job = await _client.cancelCodexJob(jobId);
      setState(() {
        _job = job;
        _activity = job.activity ?? _localActivity('cancelled', job.status);
      });
    });
  }

  Future<void> _retryJob() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final result = await _client.retryCodexJob(jobId);
      setState(() {
        _job = result.job ?? _job;
        _activity =
            result.activity ??
            _mergeActivity(_activity, _localActivity('retry', result.status));
        _review = null;
        _reviewApply = null;
      });
    });
  }

  Future<void> _reviewJob() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final review = await _client.reviewCodexJob(jobId);
      setState(() {
        _review = review;
        _activity = _mergeActivity(
          _activity,
          _localActivity('review-ready', review.status),
        );
        _reviewApply = null;
      });
    });
  }

  Future<void> _applyReviewedJob() async {
    final jobId = _job?.id;
    if (jobId == null || jobId.isEmpty) return;
    await _run(() async {
      final result = await _client.applyCodexJob(jobId);
      setState(() {
        _reviewApply = result;
        _activity = _mergeActivity(
          _activity,
          _localActivity('reviewed-apply', result.status),
        );
      });
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
        });
      }
    }
  }

  SddSpecIntakeDraft _draft() {
    return SddSpecIntakeDraft(
      workspacePath: widget.project.workspacePath,
      mode: _mode,
      requestText: _textController.text.trim(),
      specId: _mode == SddSpecIntakeMode.newSpec ? null : _selectedSpecId,
      artifact: _mode == SddSpecIntakeMode.newSpec ? 'spec' : _artifact,
      attachments: List<SddStagedMediaAttachment>.unmodifiable(_attachments),
    );
  }

  bool get _canSubmit =>
      !_busy &&
      widget.project.workspacePath.trim().isNotEmpty &&
      _textController.text.trim().isNotEmpty &&
      (_mode == SddSpecIntakeMode.newSpec || _selectedSpecId != null);

  bool get _canUploadImage =>
      !_busy && widget.project.workspacePath.trim().isNotEmpty;

  bool get _canUploadAudio =>
      !_busy && widget.project.workspacePath.trim().isNotEmpty;

  bool get _canAttachStructured =>
      !_busy && widget.project.workspacePath.trim().isNotEmpty;

  List<_IntakeJobAction> get _jobActions {
    return <_IntakeJobAction>[
      if (_job?.status == 'queued') _IntakeJobAction.run,
      if (_job?.status == 'completed') _IntakeJobAction.review,
      if (_review?.canApply == true) _IntakeJobAction.applyReviewed,
      if (_job?.id.isNotEmpty == true) _IntakeJobAction.refresh,
      if (_job?.status == 'queued' || _job?.status == 'running')
        _IntakeJobAction.cancel,
      if (_isRetryableJob(_job)) _IntakeJobAction.retry,
    ];
  }

  Future<void> _runJobAction(_IntakeJobAction action) {
    return switch (action) {
      _IntakeJobAction.run => _runJob(),
      _IntakeJobAction.review => _reviewJob(),
      _IntakeJobAction.applyReviewed => _applyReviewedJob(),
      _IntakeJobAction.refresh => _refreshJobActivity(),
      _IntakeJobAction.cancel => _cancelJob(),
      _IntakeJobAction.retry => _retryJob(),
    };
  }

  @override
  Widget build(BuildContext context) {
    final jobActions = _busy ? const <_IntakeJobAction>[] : _jobActions;
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (widget.showHeader)
            Row(
              children: <Widget>[
                const Icon(
                  Icons.add_task_rounded,
                  size: 17,
                  color: _WorkbenchColors.primary,
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Spec intake',
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                ),
                if (!_expanded)
                  TextButton.icon(
                    onPressed: () => setState(() => _expanded = true),
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('New functionality'),
                  ),
                if (_busy)
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
          if (_expanded) ...[
            if (widget.showHeader) const SizedBox(height: 10),
            SegmentedButton<SddSpecIntakeMode>(
              segments: const <ButtonSegment<SddSpecIntakeMode>>[
                ButtonSegment<SddSpecIntakeMode>(
                  value: SddSpecIntakeMode.newSpec,
                  label: Text('New spec'),
                ),
                ButtonSegment<SddSpecIntakeMode>(
                  value: SddSpecIntakeMode.existingSpec,
                  label: Text('Existing'),
                ),
              ],
              selected: <SddSpecIntakeMode>{_mode},
              onSelectionChanged: (values) {
                setState(() {
                  _mode = values.single;
                  _preview = null;
                  _clearGeneratedOutput();
                });
              },
            ),
            const SizedBox(height: 10),
            if (_mode == SddSpecIntakeMode.newSpec)
              _IntakeTargetSummary(
                detail: 'A new spec id will be generated automatically.',
              )
            else
              _ExistingSpecTargetControls(
                specs: widget.project.specs,
                selectedSpecId: _selectedSpecId,
                artifact: _artifact,
                onSpecChanged: (value) =>
                    setState(() => _selectedSpecId = value),
                onArtifactChanged: (value) => setState(() => _artifact = value),
              ),
            const SizedBox(height: 10),
            _IntakeRequestBox(
              controller: _textController,
              onChanged: (_) => setState(() {}),
              onAudio: _canUploadAudio ? _attachAudio : null,
              onImage: _canUploadImage ? _attachImage : null,
              onStructured: _canAttachStructured ? _attachStructured : null,
              audioConfigured: widget.audioAttachmentPicker != null,
              imageConfigured: widget.mediaAttachmentPicker != null,
              structuredConfigured: widget.structuredAttachmentPicker != null,
            ),
            if (_attachmentStatus != null || _attachments.isNotEmpty) ...[
              const SizedBox(height: 8),
              _AttachmentList(
                status: _attachmentStatus,
                attachments: _attachments,
                onRemove: _busy ? null : (index) => _removeAttachment(index),
                onAnnotate: _busy
                    ? null
                    : (index) => _annotateAttachment(index),
              ),
            ],
            const SizedBox(height: 10),
            OverflowBar(
              alignment: MainAxisAlignment.end,
              spacing: 8,
              overflowSpacing: 8,
              children: <Widget>[
                if (!widget.showHeader)
                  TextButton.icon(
                    onPressed: _busy ? null : () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.keyboard_return_rounded),
                    label: const Text('Leave intake'),
                  ),
                if (jobActions.isNotEmpty)
                  PopupMenuButton<_IntakeJobAction>(
                    tooltip: 'More intake actions',
                    onSelected: _runJobAction,
                    itemBuilder: (context) {
                      return jobActions
                          .map(
                            (action) => PopupMenuItem<_IntakeJobAction>(
                              value: action,
                              child: Row(
                                children: <Widget>[
                                  Icon(
                                    action.icon,
                                    size: 17,
                                    color: _WorkbenchColors.primary,
                                  ),
                                  const SizedBox(width: 8),
                                  Text(action.label),
                                ],
                              ),
                            ),
                          )
                          .toList(growable: false);
                    },
                    child: const _IntakeOverflowButton(),
                  ),
                FilledButton.icon(
                  onPressed: _canSubmit ? _dryRun : null,
                  icon: const Icon(Icons.fact_check_outlined),
                  label: const Text('Preview'),
                ),
                FilledButton.icon(
                  onPressed: _preview?.status == 'dry-run' && _canSubmit
                      ? _applyPreview
                      : null,
                  icon: Icon(
                    _mode == SddSpecIntakeMode.newSpec
                        ? Icons.create_new_folder_outlined
                        : Icons.playlist_add_check_rounded,
                  ),
                  label: Text(
                    _mode == SddSpecIntakeMode.newSpec ? 'Create' : 'Queue job',
                  ),
                ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              _StatusLines(
                title: 'Error',
                icon: Icons.error_outline,
                items: <String>[_error!],
                warning: true,
              ),
            ],
            if (_preview != null) ...[
              const SizedBox(height: 10),
              _SpecIntakePlanView(title: 'Preview', plan: _preview!),
            ],
            if (_apply != null) ...[
              const SizedBox(height: 10),
              _SpecIntakePlanView(title: 'Apply', plan: _apply!),
            ],
            if (_job != null) ...[
              const SizedBox(height: 10),
              _JobStatusView(job: _job!),
            ],
            if (_activity != null) ...[
              const SizedBox(height: 10),
              _ActivityTimelineView(activity: _activity!),
            ],
            if (_review != null) ...[
              const SizedBox(height: 10),
              _ReviewStatusView(review: _review!),
            ],
            if (_reviewApply != null) ...[
              const SizedBox(height: 10),
              _StatusLines(
                title: 'Reviewed apply',
                icon: Icons.done_all_rounded,
                items: <String>[
                  'status: ${_reviewApply!.status}',
                  ..._reviewApply!.applied,
                  ..._reviewApply!.blocked,
                  ..._reviewApply!.conflicts,
                  ..._reviewApply!.nextActions,
                ],
                warning: _reviewApply!.status != 'applied',
              ),
            ],
          ],
        ],
      ),
    );
  }
}

enum _IntakeJobAction { run, review, applyReviewed, refresh, cancel, retry }

extension _IntakeJobActionStyle on _IntakeJobAction {
  String get label => switch (this) {
    _IntakeJobAction.run => 'Run job',
    _IntakeJobAction.review => 'Review',
    _IntakeJobAction.applyReviewed => 'Apply reviewed',
    _IntakeJobAction.refresh => 'Refresh',
    _IntakeJobAction.cancel => 'Cancel',
    _IntakeJobAction.retry => 'Retry',
  };

  IconData get icon => switch (this) {
    _IntakeJobAction.run => Icons.play_arrow_rounded,
    _IntakeJobAction.review => Icons.rate_review_outlined,
    _IntakeJobAction.applyReviewed => Icons.done_all_rounded,
    _IntakeJobAction.refresh => Icons.refresh_rounded,
    _IntakeJobAction.cancel => Icons.cancel_outlined,
    _IntakeJobAction.retry => Icons.replay_rounded,
  };
}

class _IntakeRequestBox extends StatelessWidget {
  const _IntakeRequestBox({
    required this.controller,
    required this.onChanged,
    required this.onAudio,
    required this.onImage,
    required this.onStructured,
    required this.audioConfigured,
    required this.imageConfigured,
    required this.structuredConfigured,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback? onAudio;
  final VoidCallback? onImage;
  final VoidCallback? onStructured;
  final bool audioConfigured;
  final bool imageConfigured;
  final bool structuredConfigured;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            TextField(
              controller: controller,
              onChanged: onChanged,
              minLines: 4,
              maxLines: 7,
              decoration: const InputDecoration(
                labelText: 'Request',
                hintText: 'Describe the change or add context for Codex.',
                prefixIcon: Icon(Icons.forum_outlined),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                _IntakeAttachmentAction(
                  tooltip: audioConfigured
                      ? 'Attach audio note'
                      : 'Audio is unavailable in this app',
                  icon: Icons.mic_none_rounded,
                  label: 'Audio',
                  configured: audioConfigured,
                  onPressed: onAudio,
                ),
                _IntakeAttachmentAction(
                  tooltip: imageConfigured
                      ? 'Attach image'
                      : 'Image upload is unavailable in this app',
                  icon: Icons.image_outlined,
                  label: 'Image',
                  configured: imageConfigured,
                  onPressed: onImage,
                ),
                _IntakeAttachmentAction(
                  tooltip: structuredConfigured
                      ? 'Attach structured media'
                      : 'Structured media is unavailable in this app',
                  icon: Icons.crop_free_rounded,
                  label: 'Structured',
                  configured: structuredConfigured,
                  onPressed: onStructured,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _IntakeAttachmentAction extends StatelessWidget {
  const _IntakeAttachmentAction({
    required this.tooltip,
    required this.icon,
    required this.label,
    required this.configured,
    required this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final String label;
  final bool configured;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final color = configured
        ? _WorkbenchColors.primary
        : _WorkbenchColors.secondaryText;
    return Tooltip(
      message: tooltip,
      child: Material(
        color: configured
            ? _WorkbenchColors.primary.withValues(alpha: 0.10)
            : _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: configured ? onPressed : null,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            width: 112,
            constraints: const BoxConstraints(minHeight: 38),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: configured
                    ? _WorkbenchColors.primary
                    : _WorkbenchColors.border,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(icon, size: 17, color: color),
                const SizedBox(width: 7),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: color,
                      fontWeight: FontWeight.w800,
                      fontSize: 12,
                    ),
                  ),
                ),
                if (!configured) ...[
                  const SizedBox(width: 6),
                  Icon(
                    Icons.block_rounded,
                    size: 14,
                    color: _WorkbenchColors.secondaryText.withValues(
                      alpha: 0.82,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _IntakeOverflowButton extends StatelessWidget {
  const _IntakeOverflowButton();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(Icons.more_horiz_rounded, size: 18),
          SizedBox(width: 6),
          Text('Job actions', style: TextStyle(fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}

class _AttachmentList extends StatelessWidget {
  const _AttachmentList({
    required this.status,
    required this.attachments,
    required this.onRemove,
    required this.onAnnotate,
  });

  final String? status;
  final List<SddStagedMediaAttachment> attachments;
  final void Function(int index)? onRemove;
  final void Function(int index)? onAnnotate;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Icon(
                  Icons.attach_file_rounded,
                  size: 16,
                  color: _WorkbenchColors.primary,
                ),
                const SizedBox(width: 6),
                const Expanded(
                  child: Text(
                    'Attachments',
                    style: TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
            if (status != null) ...[
              const SizedBox(height: 4),
              Text(
                status!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: _WorkbenchColors.secondaryText,
                  fontSize: 12,
                ),
              ),
            ],
            for (final entry in attachments.indexed) ...[
              const SizedBox(height: 6),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: _WorkbenchColors.background,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: _WorkbenchColors.border),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(8, 6, 4, 6),
                  child: Row(
                    children: <Widget>[
                      Icon(_attachmentIcon(entry.$2), size: 16),
                      const SizedBox(width: 7),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '${entry.$2.filename} · ${entry.$2.mediaKind}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              entry.$2.stagedPath ?? entry.$2.status,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: _WorkbenchColors.secondaryText,
                                fontSize: 11,
                              ),
                            ),
                            if (entry.$2.blocked.isNotEmpty ||
                                entry.$2.nextActions.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Text(
                                <String>[
                                  ...entry.$2.blocked,
                                  ...entry.$2.nextActions,
                                ].take(2).join(' · '),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: entry.$2.blocked.isEmpty
                                      ? _WorkbenchColors.secondaryText
                                      : _WorkbenchColors.warning,
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      if (entry.$2.isImage &&
                          entry.$2.mediaKind == 'image' &&
                          onAnnotate != null)
                        IconButton(
                          tooltip: 'Mark region ${entry.$2.filename}',
                          onPressed: () => onAnnotate!(entry.$1),
                          visualDensity: VisualDensity.compact,
                          constraints: const BoxConstraints.tightFor(
                            width: 32,
                            height: 30,
                          ),
                          padding: EdgeInsets.zero,
                          icon: const Icon(Icons.crop_free_rounded, size: 18),
                        ),
                      IconButton(
                        tooltip: 'Remove attachment ${entry.$2.filename}',
                        onPressed: onRemove == null
                            ? null
                            : () => onRemove!(entry.$1),
                        visualDensity: VisualDensity.compact,
                        constraints: const BoxConstraints.tightFor(
                          width: 32,
                          height: 30,
                        ),
                        padding: EdgeInsets.zero,
                        icon: const Icon(Icons.close_rounded, size: 18),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _IntakeTargetSummary extends StatelessWidget {
  const _IntakeTargetSummary({required this.detail});

  final String detail;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Icon(
              Icons.auto_awesome_motion_outlined,
              size: 18,
              color: _WorkbenchColors.primary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text(
                    'New spec',
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    detail,
                    style: const TextStyle(
                      color: _WorkbenchColors.secondaryText,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MediaRegionDialog extends StatefulWidget {
  const _MediaRegionDialog({required this.source});

  final SddStagedMediaAttachment source;

  @override
  State<_MediaRegionDialog> createState() => _MediaRegionDialogState();
}

class _MediaRegionDialogState extends State<_MediaRegionDialog> {
  Rect? _region;
  Offset? _dragStart;
  Size? _canvasSize;
  String? _error;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      insetPadding: const EdgeInsets.all(20),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Icon(
                    Icons.crop_free_rounded,
                    size: 18,
                    color: _WorkbenchColors.primary,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Mark region',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              AspectRatio(
                aspectRatio: 16 / 10,
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final size = Size(
                      constraints.maxWidth,
                      constraints.maxHeight,
                    );
                    _canvasSize = size;
                    return GestureDetector(
                      key: const Key('sdd-media-region-canvas'),
                      onPanStart: (details) {
                        setState(() {
                          _dragStart = _clampOffset(
                            details.localPosition,
                            size,
                          );
                          _region = Rect.fromPoints(_dragStart!, _dragStart!);
                          _error = null;
                        });
                      },
                      onPanUpdate: (details) {
                        final start = _dragStart;
                        if (start == null) return;
                        setState(() {
                          _region = Rect.fromPoints(
                            start,
                            _clampOffset(details.localPosition, size),
                          );
                          _error = null;
                        });
                      },
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Stack(
                          fit: StackFit.expand,
                          children: <Widget>[
                            Image.memory(
                              Uint8List.fromList(widget.source.previewBytes),
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) =>
                                  Container(
                                    color: _WorkbenchColors.sourceBackground,
                                    alignment: Alignment.center,
                                    child: const Icon(
                                      Icons.image_outlined,
                                      color: _WorkbenchColors.secondaryText,
                                      size: 32,
                                    ),
                                  ),
                            ),
                            CustomPaint(painter: _MediaRegionPainter(_region)),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Text(
                  _error!,
                  key: const Key('sdd-media-region-error'),
                  style: const TextStyle(
                    color: _WorkbenchColors.warning,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Wrap(
                alignment: WrapAlignment.end,
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  FilledButton.icon(
                    key: const Key('sdd-media-region-apply'),
                    onPressed: () => _applyRegion(generateCrop: false),
                    icon: const Icon(Icons.check_rounded),
                    label: const Text('Use region'),
                  ),
                  FilledButton.icon(
                    key: const Key('sdd-media-crop-apply'),
                    onPressed: () => _applyRegion(generateCrop: true),
                    icon: const Icon(Icons.crop_rounded),
                    label: const Text('Crop image'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _applyRegion({required bool generateCrop}) {
    final region = _region;
    if (region == null || region.width < 2 || region.height < 2) {
      setState(() {
        _error = 'Draw a non-empty region before submitting.';
      });
      return;
    }
    Navigator.of(context).pop(
      SddMediaCropSelection(
        x: region.left.round(),
        y: region.top.round(),
        width: region.width.round(),
        height: region.height.round(),
        canvasWidth: _canvasSize?.width ?? region.right,
        canvasHeight: _canvasSize?.height ?? region.bottom,
        generateCrop: generateCrop,
      ),
    );
  }
}

class _MediaRegionPainter extends CustomPainter {
  const _MediaRegionPainter(this.region);

  final Rect? region;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = region;
    final overlay = Paint()..color = Colors.black.withValues(alpha: 0.20);
    canvas.drawRect(Offset.zero & size, overlay);
    if (rect == null || rect.width <= 0 || rect.height <= 0) return;

    final selected = RRect.fromRectAndRadius(rect, const Radius.circular(8));
    final fill = Paint()
      ..color = _WorkbenchColors.primary.withValues(alpha: 0.12)
      ..style = PaintingStyle.fill;
    final border = Paint()
      ..color = _WorkbenchColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawRRect(selected, fill);
    canvas.drawRRect(selected, border);
  }

  @override
  bool shouldRepaint(covariant _MediaRegionPainter oldDelegate) {
    return oldDelegate.region != region;
  }
}

class SddMediaCropSelection {
  const SddMediaCropSelection({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
    required this.canvasWidth,
    required this.canvasHeight,
    this.generateCrop = false,
  });

  final int x;
  final int y;
  final int width;
  final int height;
  final double canvasWidth;
  final double canvasHeight;
  final bool generateCrop;

  Map<String, Object?> toJson() {
    return <String, Object?>{'x': x, 'y': y, 'width': width, 'height': height};
  }
}

SddStagedMediaAttachment _markedRegionAttachment(
  SddStagedMediaAttachment source,
  String sourceRef,
  SddMediaCropSelection region,
) {
  final sourceItem = source.intakeItem;
  return SddStagedMediaAttachment(
    status: 'staged',
    intakeItem: <String, Object?>{
      'kind': 'marked_region',
      'mime_type': sourceItem['mime_type'] ?? 'image/png',
      'byte_size': sourceItem['byte_size'] ?? 0,
      'filename': '${_filenameStem(source.filename)}-region.png',
      if (sourceItem['sha256'] != null) 'sha256': sourceItem['sha256'],
      'source_ref': sourceRef,
      'payload_ref': sourceRef,
      'region': region.toJson(),
    },
    nextActions: const <String>[
      'Region metadata is staged; pixel crop generation is pending.',
    ],
  );
}

Future<SddMediaAttachmentDraft> _cropImageDraft(
  SddStagedMediaAttachment source,
  SddMediaCropSelection region,
) async {
  if (source.previewBytes.isEmpty) {
    throw StateError('image preview unavailable for crop generation');
  }
  final codec = await ui.instantiateImageCodec(
    Uint8List.fromList(source.previewBytes),
  );
  final frame = await codec.getNextFrame();
  final image = frame.image;
  try {
    final scaleX = image.width / region.canvasWidth;
    final scaleY = image.height / region.canvasHeight;
    final sourceRect =
        Rect.fromLTWH(
          (region.x * scaleX).clamp(0, image.width - 1).toDouble(),
          (region.y * scaleY).clamp(0, image.height - 1).toDouble(),
          (region.width * scaleX).clamp(1, image.width).toDouble(),
          (region.height * scaleY).clamp(1, image.height).toDouble(),
        ).intersect(
          Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
        );
    if (sourceRect.width < 1 || sourceRect.height < 1) {
      throw StateError('selected crop region is outside image bounds');
    }
    final cropWidth = sourceRect.width.round().clamp(1, image.width);
    final cropHeight = sourceRect.height.round().clamp(1, image.height);
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    canvas.drawImageRect(
      image,
      sourceRect,
      Rect.fromLTWH(0, 0, cropWidth.toDouble(), cropHeight.toDouble()),
      Paint(),
    );
    final cropped = await recorder.endRecording().toImage(
      cropWidth,
      cropHeight,
    );
    try {
      final byteData = await cropped.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) {
        throw StateError('crop image encoding failed');
      }
      return SddMediaAttachmentDraft(
        filename: '${_filenameStem(source.filename)}-crop.png',
        mimeType: 'image/png',
        bytes: byteData.buffer.asUint8List(),
      );
    } finally {
      cropped.dispose();
    }
  } finally {
    image.dispose();
  }
}

String _filenameStem(String filename) {
  final dot = filename.lastIndexOf('.');
  if (dot <= 0) return filename;
  return filename.substring(0, dot);
}

IconData _attachmentIcon(SddStagedMediaAttachment attachment) {
  return switch (attachment.mediaKind) {
    'audio' => Icons.mic_none_rounded,
    'marked_region' => Icons.crop_free_rounded,
    'crop' => Icons.crop_rounded,
    'screenshot_batch' => Icons.collections_outlined,
    'image_sequence' => Icons.video_library_outlined,
    _ when attachment.isImage => Icons.image_outlined,
    _ => Icons.attach_file_rounded,
  };
}

Offset _clampOffset(Offset value, Size size) {
  return Offset(
    value.dx.clamp(0, size.width).toDouble(),
    value.dy.clamp(0, size.height).toDouble(),
  );
}

class _ExistingSpecTargetControls extends StatelessWidget {
  const _ExistingSpecTargetControls({
    required this.specs,
    required this.selectedSpecId,
    required this.artifact,
    required this.onSpecChanged,
    required this.onArtifactChanged,
  });

  final List<SddSpec> specs;
  final String? selectedSpecId;
  final String artifact;
  final ValueChanged<String?> onSpecChanged;
  final ValueChanged<String> onArtifactChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        DropdownButtonFormField<String>(
          initialValue: selectedSpecId,
          decoration: const InputDecoration(
            labelText: 'Spec',
            prefixIcon: Icon(Icons.description_outlined),
          ),
          items: specs
              .map(
                (spec) => DropdownMenuItem<String>(
                  value: spec.id,
                  child: Text(spec.title, overflow: TextOverflow.ellipsis),
                ),
              )
              .toList(growable: false),
          onChanged: specs.isEmpty ? null : onSpecChanged,
        ),
        const SizedBox(height: 10),
        SegmentedButton<String>(
          segments: const <ButtonSegment<String>>[
            ButtonSegment<String>(
              value: 'spec',
              icon: Icon(Icons.description_outlined),
              label: Text('Spec'),
            ),
            ButtonSegment<String>(
              value: 'plan',
              icon: Icon(Icons.route_outlined),
              label: Text('Plan'),
            ),
            ButtonSegment<String>(
              value: 'tasks',
              icon: Icon(Icons.checklist_rounded),
              label: Text('Tasks'),
            ),
          ],
          selected: <String>{artifact},
          onSelectionChanged: (values) => onArtifactChanged(values.single),
        ),
      ],
    );
  }
}

class _SpecIntakePlanView extends StatelessWidget {
  const _SpecIntakePlanView({required this.title, required this.plan});

  final String title;
  final SddSpecIntakePlan plan;

  @override
  Widget build(BuildContext context) {
    final details = <String>[
      'status: ${plan.status}',
      if (plan.specId != null) 'spec: ${plan.specId}',
      if (plan.selectedArtifact != null) 'artifact: ${plan.selectedArtifact}',
      if (plan.metadataTitle != null) 'title: ${plan.metadataTitle}',
      if (plan.metadataDescription != null)
        'description: ${plan.metadataDescription}',
      ...plan.plannedFiles,
      ...plan.blocked,
      ...plan.conflicts,
      ...plan.rejectedMedia,
      ...plan.nextActions,
    ];
    return _StatusLines(
      title: title,
      icon: plan.status == 'dry-run'
          ? Icons.fact_check_outlined
          : Icons.task_alt_rounded,
      items: details,
      warning: plan.status == 'blocked',
    );
  }
}

class _JobStatusView extends StatelessWidget {
  const _JobStatusView({required this.job});

  final SddCodexJobStatus job;

  @override
  Widget build(BuildContext context) {
    return _StatusLines(
      title: 'Job',
      icon: Icons.terminal_rounded,
      items: <String>[
        'status: ${job.status}',
        if (job.id.isNotEmpty) 'id: ${job.id}',
        if (job.targetArtifact != null) 'artifact: ${job.targetArtifact}',
        if (job.sandboxRoot != null) 'sandbox: ${job.sandboxRoot}',
        ...job.blockedReasons,
        ...job.nextActions,
      ],
      warning: job.status == 'blocked' || job.status == 'failed',
    );
  }
}

class _ReviewStatusView extends StatelessWidget {
  const _ReviewStatusView({required this.review});

  final SddCodexJobReview review;

  @override
  Widget build(BuildContext context) {
    return _StatusLines(
      title: 'Review',
      icon: Icons.rate_review_outlined,
      items: <String>[
        'status: ${review.status}',
        'validation: ${review.validationStatus}',
        ...review.changedFiles.map(
          (change) =>
              '${change.changeType}: ${change.path}${change.patchPath == null ? '' : ' · ${change.patchPath}'}',
        ),
        ...review.blockedPaths.map((path) => 'blocked: $path'),
        ...review.protectedBaselineImpacts.map((path) => 'protected: $path'),
        ...review.conflicts.map((conflict) => 'conflict: $conflict'),
        ...review.nextActions,
      ],
      warning: review.status != 'ready',
    );
  }
}

class _ActivityTimelineView extends StatelessWidget {
  const _ActivityTimelineView({required this.activity});

  final SddActivitySnapshot activity;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.timeline_rounded,
                size: 15,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  'Activity · ${activity.state}',
                  style: const TextStyle(
                    color: _WorkbenchColors.primary,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final event in activity.events.take(8)) ...[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Icon(
                    _activityIcon(event.status),
                    size: 14,
                    color: _activityColor(event.status),
                  ),
                ),
                const SizedBox(width: 7),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          event.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        if (event.detail != null &&
                            event.detail!.trim().isNotEmpty)
                          Text(
                            event.detail!,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _WorkbenchColors.secondaryText,
                              fontSize: 11,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
          if (activity.nextActions.isNotEmpty)
            Text(
              activity.nextActions.take(2).join(' · '),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 11,
              ),
            ),
        ],
      ),
    );
  }
}

IconData _activityIcon(String status) {
  return switch (status) {
    'completed' => Icons.check_circle_outline,
    'active' => Icons.sync_rounded,
    'blocked' || 'failed' => Icons.error_outline,
    _ => Icons.radio_button_unchecked,
  };
}

Color _activityColor(String status) {
  return switch (status) {
    'completed' || 'active' => _WorkbenchColors.primary,
    'blocked' || 'failed' => _WorkbenchColors.warning,
    _ => _WorkbenchColors.secondaryText,
  };
}

SddActivitySnapshot _localActivity(String state, String status) {
  final normalizedStatus = switch (status) {
    'applied' || 'completed' || 'ready' => 'completed',
    'queued' || 'running' || 'dry-run' => 'active',
    'blocked' || 'failed' || 'timed_out' || 'cancelled' => 'blocked',
    _ => status,
  };
  final label = switch (state) {
    'apply' => 'Apply ${status.replaceAll('_', ' ')}',
    'job' => 'Job ${status.replaceAll('_', ' ')}',
    'cancelled' => 'Job cancelled',
    'retry' => status == 'queued' ? 'Retry queued' : 'Retry blocked',
    'review-ready' => status == 'ready' ? 'Review ready' : 'Review blocked',
    'reviewed-apply' =>
      status == 'applied'
          ? 'Reviewed apply completed'
          : 'Reviewed apply blocked',
    _ => state.replaceAll('_', ' '),
  };
  final detail = switch (state) {
    'review-ready' => 'Generated output still requires explicit apply.',
    'reviewed-apply' => 'Only reviewed generated output was applied.',
    'retry' => 'Retry creates a new sandboxed job from the original handoff.',
    _ => 'Status reported by the spec intake flow.',
  };
  return SddActivitySnapshot(
    state: state,
    events: <SddActivityEvent>[
      SddActivityEvent(
        state: state,
        status: normalizedStatus,
        label: label,
        detail: detail,
      ),
    ],
  );
}

SddActivitySnapshot _mergeActivity(
  SddActivitySnapshot? current,
  SddActivitySnapshot next,
) {
  return SddActivitySnapshot(
    state: next.state,
    jobId: next.jobId ?? current?.jobId,
    events: <SddActivityEvent>[...?current?.events, ...next.events],
    nextActions: next.nextActions.isNotEmpty
        ? next.nextActions
        : current?.nextActions ?? const <String>[],
  );
}

bool _isRetryableJob(SddCodexJobStatus? job) {
  return switch (job?.status) {
    'failed' || 'timed_out' || 'cancelled' => true,
    _ => false,
  };
}

class _StatusLines extends StatelessWidget {
  const _StatusLines({
    required this.title,
    required this.icon,
    required this.items,
    this.warning = false,
  });

  final String title;
  final IconData icon;
  final List<String> items;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final color = warning ? _WorkbenchColors.warning : _WorkbenchColors.primary;
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: warning
            ? _WorkbenchColors.warningSurface
            : _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: warning ? color : _WorkbenchColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(icon, size: 15, color: color),
              const SizedBox(width: 7),
              Text(
                title,
                style: TextStyle(color: color, fontWeight: FontWeight.w900),
              ),
            ],
          ),
          const SizedBox(height: 7),
          ...items
              .take(10)
              .map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    item,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
              ),
        ],
      ),
    );
  }
}

enum _SpecArtifactKind {
  spec,
  plan,
  tasks,
  slice,
  diagramGroup,
  treeSpec,
  treePlan,
  treeTask,
}

class _SpecArtifactSelection {
  const _SpecArtifactSelection({
    required this.specIndex,
    required this.kind,
    this.artifactIndex = 0,
    this.taskIndex = 0,
  });

  final int specIndex;
  final _SpecArtifactKind kind;
  final int artifactIndex;
  final int taskIndex;

  @override
  bool operator ==(Object other) {
    return other is _SpecArtifactSelection &&
        other.specIndex == specIndex &&
        other.kind == kind &&
        other.artifactIndex == artifactIndex &&
        other.taskIndex == taskIndex;
  }

  @override
  int get hashCode => Object.hash(specIndex, kind, artifactIndex, taskIndex);
}

_SpecArtifactSelection _validatedSelection(
  _SpecArtifactSelection selection,
  List<SddSpec> specs,
) {
  if (specs.isEmpty) return selection;
  final specIndex = selection.specIndex.clamp(0, specs.length - 1).toInt();
  final spec = specs[specIndex];
  final tree = spec.tree;
  if (tree != null) {
    if (selection.kind == _SpecArtifactKind.treeSpec) {
      return _SpecArtifactSelection(
        specIndex: specIndex,
        kind: _SpecArtifactKind.treeSpec,
      );
    }
    if (selection.kind == _SpecArtifactKind.treePlan ||
        selection.kind == _SpecArtifactKind.treeTask) {
      if (tree.plans.isEmpty) {
        return _SpecArtifactSelection(
          specIndex: specIndex,
          kind: _SpecArtifactKind.treeSpec,
        );
      }
      final planIndex = selection.artifactIndex
          .clamp(0, tree.plans.length - 1)
          .toInt();
      if (selection.kind == _SpecArtifactKind.treePlan) {
        return _SpecArtifactSelection(
          specIndex: specIndex,
          kind: _SpecArtifactKind.treePlan,
          artifactIndex: planIndex,
        );
      }
      final plan = tree.plans[planIndex];
      if (plan.tasks.isEmpty) {
        return _SpecArtifactSelection(
          specIndex: specIndex,
          kind: _SpecArtifactKind.treePlan,
          artifactIndex: planIndex,
        );
      }
      return _SpecArtifactSelection(
        specIndex: specIndex,
        kind: _SpecArtifactKind.treeTask,
        artifactIndex: planIndex,
        taskIndex: selection.taskIndex.clamp(0, plan.tasks.length - 1).toInt(),
      );
    }
  }
  final maxIndex = switch (selection.kind) {
    _SpecArtifactKind.spec => spec.allSpecFiles.length - 1,
    _SpecArtifactKind.plan => spec.allPlanFiles.length - 1,
    _SpecArtifactKind.tasks => spec.allTaskFiles.length - 1,
    _SpecArtifactKind.slice => spec.sliceDocs.length - 1,
    _SpecArtifactKind.diagramGroup => spec.diagrams.isEmpty ? -1 : 0,
    _SpecArtifactKind.treeSpec ||
    _SpecArtifactKind.treePlan ||
    _SpecArtifactKind.treeTask => -1,
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
  if (spec.tree != null) return _SpecArtifactKind.treeSpec;
  if (spec.allSpecFiles.isNotEmpty) return _SpecArtifactKind.spec;
  if (spec.allPlanFiles.isNotEmpty) return _SpecArtifactKind.plan;
  if (spec.allTaskFiles.isNotEmpty) return _SpecArtifactKind.tasks;
  if (spec.sliceDocs.isNotEmpty) return _SpecArtifactKind.slice;
  if (spec.diagrams.isNotEmpty) return _SpecArtifactKind.diagramGroup;
  return _SpecArtifactKind.spec;
}

class _SpecListOverview extends StatelessWidget {
  const _SpecListOverview({
    required this.specs,
    required this.selection,
    required this.onSelected,
  });

  final List<SddSpec> specs;
  final _SpecArtifactSelection selection;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(
                Icons.view_list_rounded,
                size: 17,
                color: _WorkbenchColors.primary,
              ),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Specs',
                  style: TextStyle(
                    color: _WorkbenchColors.onBackground,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final entry in specs.indexed) ...[
            if (entry.$1 > 0)
              const Divider(height: 18, color: _WorkbenchColors.border),
            _SpecListRow(
              spec: entry.$2,
              selected: entry.$1 == selection.specIndex,
              onTap: () => onSelected(entry.$1),
            ),
          ],
        ],
      ),
    );
  }
}

class _SpecListRow extends StatelessWidget {
  const _SpecListRow({
    required this.spec,
    required this.selected,
    required this.onTap,
  });

  final SddSpec spec;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final progress = _specTaskProgress(spec);
    final description = _specDescription(spec);
    final updated = _formatShortDate(spec.updatedAt ?? spec.createdAt);
    final stale =
        spec.metadataStatus == 'stale' || spec.metadataStalePaths.isNotEmpty;
    final lifecycle = _specLifecycleStatus(spec);
    final traceability = _specTraceabilityStatus(spec);
    return Material(
      color: selected
          ? _WorkbenchColors.primary.withValues(alpha: 0.10)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: 3,
                height: 56,
                decoration: BoxDecoration(
                  color: selected
                      ? _WorkbenchColors.primary
                      : _WorkbenchColors.border,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: Text(
                            spec.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: _WorkbenchColors.onBackground,
                              fontWeight: selected
                                  ? FontWeight.w900
                                  : FontWeight.w800,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        _TinyStatusPill(
                          label: lifecycle,
                          warning:
                              stale || _normalizeStatus(lifecycle) == 'blocked',
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      description,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.secondaryText,
                        fontSize: 12,
                        height: 1.25,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Wrap(
                      spacing: 7,
                      runSpacing: 5,
                      children: <Widget>[
                        _TinyMetaChip(
                          icon: Icons.checklist_rounded,
                          label: progress == null
                              ? 'tasks: source only'
                              : '${progress.completed}/${progress.total} tasks',
                          warning:
                              progress == null ||
                              progress.completed < progress.total,
                        ),
                        _TinyMetaChip(
                          icon: Icons.account_tree_outlined,
                          label: _statusStyle(traceability).label,
                          warning: _normalizeStatus(traceability) != 'linked',
                        ),
                        if (updated != null)
                          _TinyMetaChip(
                            icon: Icons.update_rounded,
                            label: updated,
                          ),
                        if ((spec.lastRunState ?? '').trim().isNotEmpty)
                          _TinyMetaChip(
                            icon: Icons.play_circle_outline_rounded,
                            label: 'last run: ${spec.lastRunState}',
                            warning: spec.lastRunState == 'failed',
                          ),
                        if (stale)
                          const _TinyMetaChip(
                            icon: Icons.warning_amber_rounded,
                            label: 'metadata stale',
                            warning: true,
                          ),
                      ],
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

class _SelectedSpecSummary extends StatelessWidget {
  const _SelectedSpecSummary({required this.spec, this.onBack});

  final SddSpec spec;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final progress = _specTaskProgress(spec);
    final updated = _formatShortDate(spec.updatedAt ?? spec.createdAt);
    final stale =
        spec.metadataStatus == 'stale' || spec.metadataStalePaths.isNotEmpty;
    final lifecycle = _specLifecycleStatus(spec);
    final traceability = _specTraceabilityStatus(spec);
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              if (onBack != null) ...[
                IconButton(
                  tooltip: 'Back to specs',
                  onPressed: onBack,
                  icon: const Icon(Icons.arrow_back_rounded),
                  visualDensity: VisualDensity.compact,
                  constraints: const BoxConstraints.tightFor(
                    width: 34,
                    height: 34,
                  ),
                  padding: EdgeInsets.zero,
                ),
                const SizedBox(width: 4),
              ],
              const Icon(
                Icons.description_outlined,
                size: 17,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  spec.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _WorkbenchColors.onBackground,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _TinyStatusPill(
                label: lifecycle,
                warning: stale || _normalizeStatus(lifecycle) == 'blocked',
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 7,
            runSpacing: 5,
            children: <Widget>[
              _TinyMetaChip(
                icon: Icons.checklist_rounded,
                label: progress == null
                    ? 'tasks: source only'
                    : '${progress.completed}/${progress.total} tasks',
                warning:
                    progress == null || progress.completed < progress.total,
              ),
              _TinyMetaChip(
                icon: Icons.account_tree_outlined,
                label: _statusStyle(traceability).label,
                warning: _normalizeStatus(traceability) != 'linked',
              ),
              if (spec.sliceDocs.isNotEmpty)
                _TinyMetaChip(
                  icon: Icons.view_agenda_outlined,
                  label: '${spec.sliceDocs.length} slices',
                ),
              if (updated != null)
                _TinyMetaChip(icon: Icons.update_rounded, label: updated),
              if (stale)
                const _TinyMetaChip(
                  icon: Icons.warning_amber_rounded,
                  label: 'metadata stale',
                  warning: true,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TinyStatusPill extends StatelessWidget {
  const _TinyStatusPill({required this.label, this.warning = false});

  final String label;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final status = _statusStyle(label, warning: warning);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.16),
        border: Border.all(color: status.color.withValues(alpha: 0.56)),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(status.icon, size: 12, color: status.color),
            const SizedBox(width: 4),
            Text(
              status.label,
              style: TextStyle(
                color: status.color,
                fontWeight: FontWeight.w900,
                fontSize: 11,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WorkbenchStatusStyle {
  const _WorkbenchStatusStyle({
    required this.label,
    required this.icon,
    required this.color,
  });

  final String label;
  final IconData icon;
  final Color color;
}

_WorkbenchStatusStyle _statusStyle(String raw, {bool warning = false}) {
  final normalized = _normalizeStatus(raw);
  if (warning && normalized == 'unknown') {
    return const _WorkbenchStatusStyle(
      label: 'Needs attention',
      icon: Icons.warning_amber_rounded,
      color: _WorkbenchColors.warning,
    );
  }
  return switch (normalized) {
    'done' => const _WorkbenchStatusStyle(
      label: 'Done',
      icon: Icons.check_circle_rounded,
      color: Color(0xFF76E4A6),
    ),
    'planned' => const _WorkbenchStatusStyle(
      label: 'Planned',
      icon: Icons.radio_button_unchecked_rounded,
      color: Color(0xFF93C5FD),
    ),
    'ongoing' => const _WorkbenchStatusStyle(
      label: 'Ongoing',
      icon: Icons.autorenew_rounded,
      color: _WorkbenchColors.primary,
    ),
    'in_progress' => const _WorkbenchStatusStyle(
      label: 'In progress',
      icon: Icons.pending_actions_rounded,
      color: Color(0xFFA78BFA),
    ),
    'blocked' => const _WorkbenchStatusStyle(
      label: 'Blocked',
      icon: Icons.block_rounded,
      color: Color(0xFFFF8A8A),
    ),
    'validation' => const _WorkbenchStatusStyle(
      label: 'Validation',
      icon: Icons.fact_check_rounded,
      color: _WorkbenchColors.warning,
    ),
    'linked' => const _WorkbenchStatusStyle(
      label: 'Linked',
      icon: Icons.account_tree_rounded,
      color: Color(0xFF76E4A6),
    ),
    'active' => const _WorkbenchStatusStyle(
      label: 'Active',
      icon: Icons.play_circle_fill_rounded,
      color: _WorkbenchColors.primary,
    ),
    'draft' => const _WorkbenchStatusStyle(
      label: 'Draft',
      icon: Icons.edit_note_rounded,
      color: Color(0xFF93C5FD),
    ),
    'not_linked' => const _WorkbenchStatusStyle(
      label: 'Not linked',
      icon: Icons.link_off_rounded,
      color: _WorkbenchColors.warning,
    ),
    'needs_metadata' => const _WorkbenchStatusStyle(
      label: 'Needs metadata',
      icon: Icons.warning_amber_rounded,
      color: _WorkbenchColors.warning,
    ),
    'stale' || 'incomplete' => const _WorkbenchStatusStyle(
      label: 'Needs attention',
      icon: Icons.warning_amber_rounded,
      color: _WorkbenchColors.warning,
    ),
    _ => _WorkbenchStatusStyle(
      label: _humanStatusLabel(raw),
      icon: warning ? Icons.warning_amber_rounded : Icons.help_outline_rounded,
      color: warning
          ? _WorkbenchColors.warning
          : _WorkbenchColors.secondaryText,
    ),
  };
}

String _normalizeStatus(String raw) {
  final lower = raw
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[_-]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ');
  if (lower.isEmpty || lower == 'unknown') return 'unknown';
  if (lower == 'x' ||
      lower == 'done' ||
      lower == 'complete' ||
      lower == 'completed' ||
      lower == 'validated' ||
      lower == 'applied') {
    return 'done';
  }
  if (lower == 'todo' ||
      lower == 'to do' ||
      lower == 'pending' ||
      lower == 'queued' ||
      lower == 'open' ||
      lower == 'planned') {
    return 'planned';
  }
  if (lower == 'in progress' || lower == 'running' || lower == 'started') {
    return 'in_progress';
  }
  if (lower == 'ongoing' || lower == 'active') return lower;
  if (lower == 'blocked' || lower == 'failed' || lower == 'missing') {
    return 'blocked';
  }
  if (lower == 'validation' ||
      lower == 'validate' ||
      lower == 'review' ||
      lower == 'ready' ||
      lower == 'testing') {
    return 'validation';
  }
  if (lower == 'not linked' || lower == 'unlinked') return 'not_linked';
  if (lower == 'needs metadata' || lower == 'metadata missing') {
    return 'needs_metadata';
  }
  if (lower == 'linked' ||
      lower == 'draft' ||
      lower == 'stale' ||
      lower == 'incomplete') {
    return lower;
  }
  return 'unknown';
}

String _humanStatusLabel(String raw) {
  final words = raw
      .trim()
      .replaceAll(RegExp(r'[_-]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ');
  if (words.isEmpty || words.toLowerCase() == 'unknown') {
    return 'Needs metadata';
  }
  return '${words.substring(0, 1).toUpperCase()}${words.substring(1)}';
}

class _TinyMetaChip extends StatelessWidget {
  const _TinyMetaChip({
    required this.icon,
    required this.label,
    this.warning = false,
  });

  final IconData icon;
  final String label;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final color = warning
        ? _WorkbenchColors.warning
        : _WorkbenchColors.secondaryText;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 4),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w700,
            fontSize: 11,
          ),
        ),
      ],
    );
  }
}

class _SpecTraceNavigator extends StatelessWidget {
  const _SpecTraceNavigator({
    required this.specs,
    required this.selection,
    required this.onSelected,
    this.title = 'SDD trace',
    this.allowSpecSwitch = true,
  });

  final List<SddSpec> specs;
  final _SpecArtifactSelection selection;
  final ValueChanged<_SpecArtifactSelection> onSelected;
  final String title;
  final bool allowSpecSwitch;

  @override
  Widget build(BuildContext context) {
    final selectedSpec = specs[selection.specIndex];
    final tree = selectedSpec.tree;
    if (tree != null) {
      return _SpecTreeNavigator(
        specs: specs,
        spec: selectedSpec,
        tree: tree,
        selection: selection,
        onSelected: onSelected,
        title: title,
        allowSpecSwitch: allowSpecSwitch,
      );
    }
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.account_tree_outlined,
                size: 16,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: _WorkbenchColors.onBackground,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              if (allowSpecSwitch && specs.length > 1)
                _SpecSelectorMenu(
                  specs: specs,
                  selectedIndex: selection.specIndex,
                  onSelected: (index) {
                    onSelected(
                      _SpecArtifactSelection(
                        specIndex: index,
                        kind: _firstAvailableArtifact(specs[index]),
                      ),
                    );
                  },
                ),
            ],
          ),
          const SizedBox(height: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Text(
                    'Spec trace',
                    style: TextStyle(
                      color: _WorkbenchColors.primary,
                      fontSize: 12,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _artifactSelectionLabel(selectedSpec, selection),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.onBackground,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              _ArtifactSelectorBar(
                spec: selectedSpec,
                selection: selection,
                onSelected: onSelected,
              ),
            ],
          ),
          if (selectedSpec.missing.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Missing: ${selectedSpec.missing.join(', ')}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: _WorkbenchColors.warning,
                fontSize: 11,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ArtifactSelectorBar extends StatelessWidget {
  const _ArtifactSelectorBar({
    required this.spec,
    required this.selection,
    required this.onSelected,
  });

  final SddSpec spec;
  final _SpecArtifactSelection selection;
  final ValueChanged<_SpecArtifactSelection> onSelected;

  @override
  Widget build(BuildContext context) {
    final items = _artifactMenuItems(spec, selection.specIndex);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: items
          .map((item) {
            return _ArtifactSelectorChip(
              item: item,
              selected: item.selection == selection,
              onSelected: () => onSelected(item.selection),
            );
          })
          .toList(growable: false),
    );
  }
}

class _ArtifactSelectorChip extends StatelessWidget {
  const _ArtifactSelectorChip({
    required this.item,
    required this.selected,
    required this.onSelected,
  });

  final _ArtifactMenuItem item;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    final foreground = selected
        ? _WorkbenchColors.onPrimary
        : _WorkbenchColors.onBackground;
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected
            ? _WorkbenchColors.primary
            : _WorkbenchColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: onSelected,
          child: Container(
            constraints: const BoxConstraints(minHeight: 42),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: selected
                    ? _WorkbenchColors.primary
                    : _WorkbenchColors.border,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(
                  selected ? Icons.check_rounded : item.icon,
                  size: 16,
                  color: foreground,
                ),
                const SizedBox(width: 7),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      item.label,
                      style: TextStyle(
                        color: foreground,
                        fontSize: 12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    if (item.detail != null)
                      Text(
                        item.detail!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: selected
                              ? _WorkbenchColors.onPrimary.withValues(
                                  alpha: 0.82,
                                )
                              : _WorkbenchColors.secondaryText,
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SpecTreeNavigator extends StatelessWidget {
  const _SpecTreeNavigator({
    required this.specs,
    required this.spec,
    required this.tree,
    required this.selection,
    required this.onSelected,
    required this.title,
    required this.allowSpecSwitch,
  });

  final List<SddSpec> specs;
  final SddSpec spec;
  final SddSpecTree tree;
  final _SpecArtifactSelection selection;
  final ValueChanged<_SpecArtifactSelection> onSelected;
  final String title;
  final bool allowSpecSwitch;

  @override
  Widget build(BuildContext context) {
    final selectedPlan =
        selection.kind == _SpecArtifactKind.treePlan ||
            selection.kind == _SpecArtifactKind.treeTask
        ? _fileAt(tree.plans, selection.artifactIndex)
        : null;
    final selectedTask =
        selectedPlan != null && selection.kind == _SpecArtifactKind.treeTask
        ? _fileAt(selectedPlan.tasks, selection.taskIndex)
        : null;
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.account_tree_outlined,
                size: 16,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: _WorkbenchColors.onBackground,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              if (allowSpecSwitch && specs.length > 1)
                _SpecSelectorMenu(
                  specs: specs,
                  selectedIndex: selection.specIndex,
                  onSelected: (index) {
                    onSelected(
                      _SpecArtifactSelection(
                        specIndex: index,
                        kind: _firstAvailableArtifact(specs[index]),
                      ),
                    );
                  },
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (selection.kind == _SpecArtifactKind.treeSpec) ...[
            const Text(
              'Plans in this spec',
              style: TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 6),
            for (final planEntry in tree.plans.indexed)
              _TreeNodeRow(
                icon: Icons.route_outlined,
                label: 'Plan ${planEntry.$2.number}',
                title: planEntry.$2.title,
                selected: false,
                level: 0,
                status: planEntry.$2.status,
                trailing: '${planEntry.$2.tasks.length} tasks',
                onTap: () => onSelected(
                  _SpecArtifactSelection(
                    specIndex: selection.specIndex,
                    kind: _SpecArtifactKind.treePlan,
                    artifactIndex: planEntry.$1,
                  ),
                ),
              ),
            if (tree.plans.isEmpty) ...[
              const SizedBox(height: 6),
              const Text(
                'No plans defined in this spec tree.',
                style: TextStyle(
                  color: _WorkbenchColors.secondaryText,
                  fontSize: 12,
                ),
              ),
            ],
            if (tree.plans.any((plan) => plan.tasks.isNotEmpty)) ...[
              const SizedBox(height: 8),
              _AllSpecTasksExpansion(
                tree: tree,
                onSelected: (planIndex, taskIndex) {
                  onSelected(
                    _SpecArtifactSelection(
                      specIndex: selection.specIndex,
                      kind: _SpecArtifactKind.treeTask,
                      artifactIndex: planIndex,
                      taskIndex: taskIndex,
                    ),
                  );
                },
              ),
            ],
          ] else if (selectedPlan != null) ...[
            TextButton.icon(
              onPressed: () => onSelected(
                _SpecArtifactSelection(
                  specIndex: selection.specIndex,
                  kind: _SpecArtifactKind.treeSpec,
                ),
              ),
              icon: const Icon(Icons.arrow_back_rounded, size: 17),
              label: const Text('Back to spec plans'),
            ),
            if (selectedTask != null) ...[
              const SizedBox(height: 4),
              TextButton.icon(
                onPressed: () => onSelected(
                  _SpecArtifactSelection(
                    specIndex: selection.specIndex,
                    kind: _SpecArtifactKind.treePlan,
                    artifactIndex: selection.artifactIndex,
                  ),
                ),
                icon: const Icon(Icons.arrow_back_rounded, size: 17),
                label: Text('Back to Plan ${selectedPlan.number} tasks'),
              ),
            ],
          ] else
            const _InfoCard(title: 'Plan', detail: 'Missing plan node'),
        ],
      ),
    );
  }
}

class _AllSpecTasksExpansion extends StatefulWidget {
  const _AllSpecTasksExpansion({required this.tree, required this.onSelected});

  final SddSpecTree tree;
  final void Function(int planIndex, int taskIndex) onSelected;

  @override
  State<_AllSpecTasksExpansion> createState() => _AllSpecTasksExpansionState();
}

class _AllSpecTasksExpansionState extends State<_AllSpecTasksExpansion> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final taskCount = widget.tree.plans.fold<int>(
      0,
      (total, plan) => total + plan.tasks.length,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _expanded
            ? _WorkbenchColors.primary.withValues(alpha: 0.08)
            : _WorkbenchColors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Column(
        children: <Widget>[
          Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => setState(() => _expanded = !_expanded),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 9,
                ),
                child: Row(
                  children: <Widget>[
                    Icon(
                      _expanded
                          ? Icons.expand_less_rounded
                          : Icons.expand_more_rounded,
                      size: 19,
                      color: _WorkbenchColors.primary,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'See all tasks',
                        style: TextStyle(
                          color: _WorkbenchColors.onBackground,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                    _TinyMetaChip(
                      icon: Icons.checklist_rounded,
                      label: '$taskCount tasks',
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (_expanded) ...[
            const Divider(height: 1, color: _WorkbenchColors.border),
            for (final planEntry in widget.tree.plans.indexed)
              for (final taskEntry in planEntry.$2.tasks.indexed) ...[
                if (planEntry.$1 > 0 || taskEntry.$1 > 0)
                  const Divider(height: 1, color: _WorkbenchColors.border),
                _TreeNodeRow(
                  icon: Icons.checklist_rounded,
                  label:
                      'Plan ${planEntry.$2.number} · Task ${taskEntry.$2.number}',
                  title: taskEntry.$2.title,
                  selected: false,
                  level: 0,
                  status: taskEntry.$2.status,
                  trailing: 'Plan ${planEntry.$2.number}',
                  onTap: () => widget.onSelected(planEntry.$1, taskEntry.$1),
                ),
              ],
          ],
        ],
      ),
    );
  }
}

class _TreeNodeRow extends StatelessWidget {
  const _TreeNodeRow({
    required this.icon,
    required this.label,
    required this.title,
    required this.selected,
    required this.level,
    required this.onTap,
    this.status,
    this.trailing,
  });

  final IconData icon;
  final String label;
  final String title;
  final bool selected;
  final int level;
  final VoidCallback onTap;
  final String? status;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    final statusValue = status ?? '';
    return Semantics(
      button: true,
      child: Material(
        color: selected
            ? _WorkbenchColors.primary.withValues(alpha: 0.10)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: onTap,
          child: Padding(
            padding: EdgeInsets.fromLTRB(8 + (level * 18), 8, 8, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Icon(
                      icon,
                      size: 16,
                      color: selected
                          ? _WorkbenchColors.primary
                          : _WorkbenchColors.secondaryText,
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 52,
                      child: Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: selected
                              ? _WorkbenchColors.primary
                              : _WorkbenchColors.secondaryText,
                          fontSize: 11,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: _WorkbenchColors.onBackground,
                          fontSize: 12,
                          fontWeight: selected
                              ? FontWeight.w900
                              : FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 18,
                      color: selected
                          ? _WorkbenchColors.primary
                          : _WorkbenchColors.secondaryText,
                    ),
                  ],
                ),
                if (trailing != null || statusValue.trim().isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Padding(
                    padding: const EdgeInsets.only(left: 82),
                    child: Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: <Widget>[
                        if (trailing != null)
                          Text(
                            trailing!,
                            style: const TextStyle(
                              color: _WorkbenchColors.secondaryText,
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        if (statusValue.trim().isNotEmpty)
                          _TinyStatusPill(
                            label: statusValue,
                            warning: _normalizeStatus(statusValue) == 'blocked',
                          ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ArtifactMenuItem {
  const _ArtifactMenuItem({
    required this.selection,
    required this.label,
    required this.icon,
    this.detail,
  });

  final _SpecArtifactSelection selection;
  final String label;
  final IconData icon;
  final String? detail;
}

List<_ArtifactMenuItem> _artifactMenuItems(SddSpec spec, int specIndex) {
  final items = <_ArtifactMenuItem>[];

  void addTreeItems(SddSpecTree tree) {
    items.add(
      _ArtifactMenuItem(
        selection: _SpecArtifactSelection(
          specIndex: specIndex,
          kind: _SpecArtifactKind.treeSpec,
        ),
        label: 'Spec: ${spec.title}',
        icon: Icons.description_outlined,
        detail: '${tree.plans.length} plan(s)',
      ),
    );
    for (final planEntry in tree.plans.indexed) {
      final plan = planEntry.$2;
      items.add(
        _ArtifactMenuItem(
          selection: _SpecArtifactSelection(
            specIndex: specIndex,
            kind: _SpecArtifactKind.treePlan,
            artifactIndex: planEntry.$1,
          ),
          label: 'Plan ${plan.number}: ${plan.title}',
          icon: Icons.route_outlined,
          detail: '${plan.tasks.length} task(s)',
        ),
      );
      for (final taskEntry in plan.tasks.indexed) {
        final task = taskEntry.$2;
        items.add(
          _ArtifactMenuItem(
            selection: _SpecArtifactSelection(
              specIndex: specIndex,
              kind: _SpecArtifactKind.treeTask,
              artifactIndex: planEntry.$1,
              taskIndex: taskEntry.$1,
            ),
            label: 'Task ${task.number}: ${task.title}',
            icon: Icons.checklist_rounded,
            detail: 'Plan ${plan.number}',
          ),
        );
      }
    }
  }

  void addFiles({
    required _SpecArtifactKind kind,
    required List<SddFile> files,
    required String fallbackLabel,
    required IconData icon,
    String Function(SddFile file)? label,
    String? Function(int index, SddFile file)? detail,
  }) {
    for (final entry in files.indexed) {
      items.add(
        _ArtifactMenuItem(
          selection: _SpecArtifactSelection(
            specIndex: specIndex,
            kind: kind,
            artifactIndex: entry.$1,
          ),
          label:
              label?.call(entry.$2) ?? _artifactLabel(entry.$2, fallbackLabel),
          icon: icon,
          detail: detail?.call(entry.$1, entry.$2),
        ),
      );
    }
  }

  final tree = spec.tree;
  if (tree != null) {
    addTreeItems(tree);
    addFiles(
      kind: _SpecArtifactKind.slice,
      files: spec.sliceDocs,
      fallbackLabel: 'slice.md',
      icon: Icons.view_agenda_outlined,
      label: (file) => 'Slice: ${_artifactPathLabel(file, 'slice.md')}',
    );
    if (spec.diagrams.isNotEmpty) {
      items.add(
        _ArtifactMenuItem(
          selection: _SpecArtifactSelection(
            specIndex: specIndex,
            kind: _SpecArtifactKind.diagramGroup,
          ),
          label: 'Diagrams',
          icon: Icons.account_tree_outlined,
          detail: '${spec.diagrams.length} diagram(s)',
        ),
      );
    }
    return items;
  }

  addFiles(
    kind: _SpecArtifactKind.spec,
    files: spec.allSpecFiles,
    fallbackLabel: 'spec.md',
    icon: Icons.description_outlined,
    label: (file) => 'Spec: ${_artifactPathLabel(file, 'spec.md')}',
    detail: (index, file) => 'Spec body',
  );
  addFiles(
    kind: _SpecArtifactKind.plan,
    files: spec.allPlanFiles,
    fallbackLabel: 'plan.md',
    icon: Icons.route_outlined,
    label: (file) => 'Plan: ${_artifactPathLabel(file, 'plan.md')}',
  );
  if (spec.allPlanFiles.isEmpty) {
    addFiles(
      kind: _SpecArtifactKind.tasks,
      files: spec.allTaskFiles,
      fallbackLabel: 'tasks.md',
      icon: Icons.checklist_rounded,
      label: (file) => 'Tasks: ${_artifactPathLabel(file, 'tasks.md')}',
      detail: (index, file) => _taskPlanAssociation(spec, index, file),
    );
  } else {
    for (final entry in spec.allTaskFiles.indexed) {
      if (_taskPlanIndex(spec, entry.$1, entry.$2) != null) continue;
      items.add(
        _ArtifactMenuItem(
          selection: _SpecArtifactSelection(
            specIndex: specIndex,
            kind: _SpecArtifactKind.tasks,
            artifactIndex: entry.$1,
          ),
          label:
              'Tasks needing plan: ${_artifactPathLabel(entry.$2, 'tasks.md')}',
          icon: Icons.checklist_rtl_rounded,
          detail: _taskPlanAssociation(spec, entry.$1, entry.$2),
        ),
      );
    }
  }
  addFiles(
    kind: _SpecArtifactKind.slice,
    files: spec.sliceDocs,
    fallbackLabel: 'slice.md',
    icon: Icons.view_agenda_outlined,
    label: (file) => 'Slice: ${_artifactPathLabel(file, 'slice.md')}',
  );
  if (spec.diagrams.isNotEmpty) {
    items.add(
      _ArtifactMenuItem(
        selection: _SpecArtifactSelection(
          specIndex: specIndex,
          kind: _SpecArtifactKind.diagramGroup,
        ),
        label: 'Diagrams',
        icon: Icons.account_tree_outlined,
        detail: '${spec.diagrams.length} diagram(s)',
      ),
    );
  }
  return items;
}

String _artifactSelectionLabel(SddSpec spec, _SpecArtifactSelection selection) {
  final items = _artifactMenuItems(spec, selection.specIndex);
  for (final item in items) {
    if (item.selection == selection) {
      return item.detail == null
          ? item.label
          : '${item.label} · ${item.detail}';
    }
  }
  return spec.title;
}

String? _taskPlanAssociation(SddSpec spec, int taskIndex, SddFile taskFile) {
  if (spec.allPlanFiles.isEmpty) return 'Plan: Not linked';
  final planIndex = _taskPlanIndex(spec, taskIndex, taskFile);
  if (planIndex != null) {
    return 'Plan: ${_artifactLabel(spec.allPlanFiles[planIndex], 'plan.md')}';
  }
  return 'Plan: Needs metadata';
}

int? _taskPlanIndex(SddSpec spec, int taskIndex, SddFile taskFile) {
  final taskStem = _artifactStem(taskFile.path);
  for (final entry in spec.allPlanFiles.indexed) {
    final plan = entry.$2;
    final planStem = _artifactStem(plan.path);
    if (taskStem.isNotEmpty &&
        planStem.isNotEmpty &&
        (taskStem.contains(planStem) || planStem.contains(taskStem))) {
      return entry.$1;
    }
    if (taskStem.isEmpty &&
        planStem.isEmpty &&
        _artifactDirectory(taskFile.path) == _artifactDirectory(plan.path)) {
      return entry.$1;
    }
  }
  if (spec.allPlanFiles.length == 1 && taskStem.isEmpty) {
    return 0;
  }
  return null;
}

String _artifactDirectory(String path) {
  final normalized = path.trim();
  final slash = normalized.lastIndexOf('/');
  if (slash <= 0) return '';
  return normalized.substring(0, slash).toLowerCase();
}

String _artifactStem(String path) {
  final filename = path.split('/').last.toLowerCase();
  return filename
      .replaceAll(RegExp(r'\.(md|markdown)$'), '')
      .replaceAll(RegExp(r'[-_]*(plan|tasks?)$'), '')
      .trim();
}

class _SpecSelectorMenu extends StatelessWidget {
  const _SpecSelectorMenu({
    required this.specs,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<SddSpec> specs;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<int>(
      tooltip: 'Select spec',
      onSelected: onSelected,
      itemBuilder: (context) {
        return List<PopupMenuEntry<int>>.generate(specs.length, (index) {
          final spec = specs[index];
          return PopupMenuItem<int>(
            value: index,
            child: Row(
              children: <Widget>[
                Icon(
                  index == selectedIndex
                      ? Icons.check_rounded
                      : Icons.description_outlined,
                  size: 16,
                  color: index == selectedIndex
                      ? _WorkbenchColors.primary
                      : _WorkbenchColors.secondaryText,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    spec.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: _WorkbenchColors.onBackground,
                    ),
                  ),
                ),
              ],
            ),
          );
        });
      },
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              'Switch',
              style: TextStyle(
                color: _WorkbenchColors.primary,
                fontWeight: FontWeight.w800,
              ),
            ),
            Icon(
              Icons.arrow_drop_down_rounded,
              color: _WorkbenchColors.primary,
            ),
          ],
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
    required this.onSelected,
    this.showHeading = true,
  });

  final SddProject project;
  final SddSpec spec;
  final _SpecArtifactSelection selection;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;
  final ValueChanged<_SpecArtifactSelection> onSelected;
  final bool showHeading;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (showHeading) ...[
          Text(
            spec.title,
            style: const TextStyle(
              color: _WorkbenchColors.onBackground,
              fontSize: 17,
              fontWeight: FontWeight.w900,
            ),
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
              _TraceChip(label: 'status: ${_specLifecycleStatus(spec)}'),
              _TraceChip(label: 'trace: ${_specTraceabilityStatus(spec)}'),
              _TraceChip(label: '${_specPlanCount(spec)} plans'),
              _TraceChip(label: '${_specTaskCount(spec)} tasks'),
              _TraceChip(label: '${spec.sliceDocs.length} slices'),
            ],
          ),
          const SizedBox(height: 10),
        ],
        if (spec.missing.isNotEmpty) _MissingArtifacts(items: spec.missing),
        _buildSelectedArtifact(),
      ],
    );
  }

  Widget _buildSelectedArtifact() {
    switch (selection.kind) {
      case _SpecArtifactKind.treeSpec:
        return _buildSelectedTreeSpec();
      case _SpecArtifactKind.treePlan:
        return _buildSelectedTreePlan();
      case _SpecArtifactKind.treeTask:
        return _buildSelectedTreeTask();
      case _SpecArtifactKind.spec:
        final file = _fileAt(spec.allSpecFiles, selection.artifactIndex);
        return _SddFileSection(
          title: _artifactPathLabel(file, 'spec.md'),
          file: file,
          specBodyMode: true,
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
        final taskSections = _taskSectionsForPlan(
          project: project,
          spec: spec,
          planIndex: selection.artifactIndex,
        );
        return _PlanFileSection(
          title: _artifactLabel(file, 'plan.md'),
          file: file,
          taskSections: taskSections,
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
          planAssociation: file == null
              ? null
              : _taskPlanAssociation(spec, selection.artifactIndex, file),
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
      case _SpecArtifactKind.diagramGroup:
        return _SpecDiagramListCard(
          project: project,
          spec: spec,
          diagramRenderer: diagramRenderer,
          onFeedback: onFeedback,
          onCodexAction: onCodexAction,
        );
    }
  }

  Widget _buildSelectedTreeSpec() {
    final tree = spec.tree;
    final file = tree?.file ?? spec.spec;
    final diagrams = tree?.diagrams ?? const <SddDiagram>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _SddFileSection(
          title: _artifactPathLabel(file, 'spec.md'),
          file: file,
          specBodyMode: true,
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
        ),
        if (diagrams.isNotEmpty) ...[
          const SizedBox(height: 10),
          _ScopedDiagramListCard(
            title: 'Spec diagrams',
            diagrams: diagrams,
            project: project,
            spec: spec,
            diagramRenderer: diagramRenderer,
            onFeedback: onFeedback,
            onCodexAction: onCodexAction,
          ),
        ],
      ],
    );
  }

  Widget _buildSelectedTreePlan() {
    final tree = spec.tree;
    final plan = tree == null
        ? null
        : _fileAt(tree.plans, selection.artifactIndex);
    if (plan == null) {
      return const _InfoCard(title: 'Plan', detail: 'Missing plan node');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _TreeTaskListCard(
          project: project,
          spec: spec,
          plan: plan,
          onFeedback: onFeedback,
          onCodexAction: onCodexAction,
          onTaskSelected: (taskIndex) => onSelected(
            _SpecArtifactSelection(
              specIndex: selection.specIndex,
              kind: _SpecArtifactKind.treeTask,
              artifactIndex: selection.artifactIndex,
              taskIndex: taskIndex,
            ),
          ),
        ),
        if (plan.diagrams.isNotEmpty) ...[
          const SizedBox(height: 10),
          _ScopedDiagramListCard(
            title: 'Plan ${plan.number} diagrams',
            diagrams: plan.diagrams,
            project: project,
            spec: spec,
            diagramRenderer: diagramRenderer,
            onFeedback: onFeedback,
            onCodexAction: onCodexAction,
          ),
        ],
      ],
    );
  }

  Widget _buildSelectedTreeTask() {
    final tree = spec.tree;
    final plan = tree == null
        ? null
        : _fileAt(tree.plans, selection.artifactIndex);
    final task = plan == null ? null : _fileAt(plan.tasks, selection.taskIndex);
    if (plan == null || task == null) {
      return const _InfoCard(title: 'Task', detail: 'Missing task node');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _TreeTaskNodeSection(
          project: project,
          spec: spec,
          plan: plan,
          task: task,
          onFeedback: onFeedback,
          onCodexAction: onCodexAction,
        ),
        if (task.diagrams.isNotEmpty) ...[
          const SizedBox(height: 10),
          _ScopedDiagramListCard(
            title: 'Task ${task.number} diagrams',
            diagrams: task.diagrams,
            project: project,
            spec: spec,
            diagramRenderer: diagramRenderer,
            onFeedback: onFeedback,
            onCodexAction: onCodexAction,
          ),
        ],
      ],
    );
  }
}

class _PlanTaskSectionData {
  const _PlanTaskSectionData({
    required this.index,
    required this.file,
    required this.planAssociation,
    required this.feedbackTarget,
  });

  final int index;
  final SddFile file;
  final String planAssociation;
  final SddFeedbackTarget? feedbackTarget;
}

class _TreeTaskListCard extends StatelessWidget {
  const _TreeTaskListCard({
    required this.project,
    required this.spec,
    required this.plan,
    required this.onTaskSelected,
    this.onFeedback,
    this.onCodexAction,
  });

  final SddProject project;
  final SddSpec spec;
  final SddPlanNode plan;
  final ValueChanged<int> onTaskSelected;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;

  @override
  Widget build(BuildContext context) {
    final completed = plan.tasks
        .where((task) => _taskStatusIsComplete(task.status))
        .length;
    return _PanelCard(
      child: Column(
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
              Expanded(
                child: Text(
                  'Tasks in Plan ${plan.number}',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              _TinyMetaChip(
                icon: Icons.account_tree_outlined,
                label: '$completed/${plan.tasks.length} done',
                warning: completed < plan.tasks.length,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Plan ${plan.number}: ${plan.title}',
            style: const TextStyle(
              color: _WorkbenchColors.onBackground,
              fontWeight: FontWeight.w900,
            ),
          ),
          if (plan.description.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              plan.description,
              style: const TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
                height: 1.3,
              ),
            ),
          ],
          const SizedBox(height: 8),
          _ArtifactControls(
            target: _fileFeedbackTarget(
              project: project,
              spec: spec,
              file: plan.file,
              artifactType: 'plan',
              fallbackTitle: plan.title,
            ),
            onFeedback: onFeedback,
            actions: const <SddCodexActionKind>[SddCodexActionKind.updatePlan],
            onCodexAction: onCodexAction,
          ),
          if (plan.tasks.isEmpty) ...[
            const SizedBox(height: 8),
            const Text(
              'No tasks defined for this plan.',
              style: TextStyle(
                color: _WorkbenchColors.secondaryText,
                fontSize: 12,
              ),
            ),
          ] else ...[
            const SizedBox(height: 8),
            for (final entry in plan.tasks.indexed) ...[
              if (entry.$1 > 0)
                const Divider(height: 14, color: _WorkbenchColors.border),
              _TreeNodeRow(
                icon: Icons.checklist_rounded,
                label: 'Task ${entry.$2.number}',
                title: entry.$2.title,
                selected: false,
                level: 0,
                status: entry.$2.status,
                trailing: 'Open',
                onTap: () => onTaskSelected(entry.$1),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _TreeTaskNodeSection extends StatelessWidget {
  const _TreeTaskNodeSection({
    required this.project,
    required this.spec,
    required this.plan,
    required this.task,
    this.onFeedback,
    this.onCodexAction,
  });

  final SddProject project;
  final SddSpec spec;
  final SddPlanNode plan;
  final SddTaskNode task;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;

  @override
  Widget build(BuildContext context) {
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _FileHeader(
          title: 'Task ${task.number}: ${task.title}',
          file: task.file ?? const SddFile(path: 'task.md', sizeBytes: 0),
        ),
        _ArtifactControls(
          target: _fileFeedbackTarget(
            project: project,
            spec: spec,
            file: task.file,
            artifactType: 'tasks',
            fallbackTitle: task.title,
          ),
          onFeedback: onFeedback,
          actions: const <SddCodexActionKind>[SddCodexActionKind.updateTasks],
          onCodexAction: onCodexAction,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: <Widget>[
            _TinyMetaChip(
              icon: Icons.route_outlined,
              label: 'Plan ${plan.number}',
            ),
            _TinyStatusPill(label: task.status),
          ],
        ),
        if (task.description.trim().isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            task.description,
            style: const TextStyle(
              color: _WorkbenchColors.secondaryText,
              height: 1.35,
            ),
          ),
        ],
        if (task.file == null) ...[
          const SizedBox(height: 8),
          const Text(
            'Missing file',
            style: TextStyle(color: _WorkbenchColors.warning),
          ),
        ],
        if (task.file?.error != null) ...[
          const SizedBox(height: 8),
          Text(
            task.file!.error!,
            style: const TextStyle(color: _WorkbenchColors.warning),
          ),
        ],
        if (task.file?.hasContent ?? false) ...[
          const SizedBox(height: 8),
          _SourceExcerptDisclosure(text: task.file!.content!),
        ],
      ],
    );
    return _PanelCard(child: body);
  }
}

List<_PlanTaskSectionData> _taskSectionsForPlan({
  required SddProject project,
  required SddSpec spec,
  required int planIndex,
}) {
  final taskSections = <_PlanTaskSectionData>[];
  for (final entry in spec.allTaskFiles.indexed) {
    final ownerIndex = _taskPlanIndex(spec, entry.$1, entry.$2);
    if (ownerIndex != planIndex) continue;
    taskSections.add(
      _PlanTaskSectionData(
        index: entry.$1,
        file: entry.$2,
        planAssociation:
            _taskPlanAssociation(spec, entry.$1, entry.$2) ??
            'Plan: Not linked',
        feedbackTarget: _fileFeedbackTarget(
          project: project,
          spec: spec,
          file: entry.$2,
          artifactType: 'tasks',
          fallbackTitle: 'tasks.md',
        ),
      ),
    );
  }
  return taskSections;
}

class _TraceChip extends StatelessWidget {
  const _TraceChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(
        label,
        style: const TextStyle(color: _WorkbenchColors.onBackground),
      ),
    );
  }
}

class _GovernanceTab extends StatelessWidget {
  const _GovernanceTab({required this.project});

  final SddProject project;

  @override
  Widget build(BuildContext context) {
    final baselines = _baselineArtifacts(project);
    final traceRows = project.specs;
    final impactItems = _impactQueueItems(project);
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
      children: <Widget>[
        _PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'Architecture, domain, and data baselines',
                style: TextStyle(fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 8),
              if (baselines.isEmpty)
                const Text(
                  'No baseline artifacts loaded',
                  style: TextStyle(color: _WorkbenchColors.secondaryText),
                )
              else
                ...baselines.map(
                  (artifact) => _KeyValueLine(
                    label: artifact.kind,
                    value: artifact.label,
                    warning: artifact.warning,
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
                'Traceability matrix',
                style: TextStyle(fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 8),
              if (traceRows.isEmpty)
                const Text(
                  'No feature specs available',
                  style: TextStyle(color: _WorkbenchColors.secondaryText),
                )
              else
                ...traceRows.map(
                  (spec) => _KeyValueLine(
                    label: spec.id,
                    value:
                        '${_specLifecycleStatus(spec)} · ${_specTraceabilityStatus(spec)} · '
                        '${_specPlanCount(spec)} plan(s), '
                        '${_specTaskCount(spec)} task(s), '
                        '${spec.diagrams.length} diagram(s)',
                    warning:
                        spec.missing.isNotEmpty ||
                        _specTraceabilityStatus(spec) != 'linked',
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
                'Architecture, domain, and data impact queue',
                style: TextStyle(fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 8),
              if (impactItems.isEmpty)
                const Text(
                  'No baseline impact items pending',
                  style: TextStyle(color: _WorkbenchColors.secondaryText),
                )
              else
                ...impactItems.map(
                  (item) => _KeyValueLine(
                    label: item.kind,
                    value: item.label,
                    warning: true,
                  ),
                ),
            ],
          ),
        ),
      ],
    );
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
    final selectedLabel = selectedType == 'all'
        ? 'All diagrams'
        : _diagramTypeLabel(selectedType);
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
                Text(
                  type == 'all' ? 'All diagrams' : _diagramTypeLabel(type),
                  style: const TextStyle(color: _WorkbenchColors.onBackground),
                ),
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
              style: const TextStyle(
                color: _WorkbenchColors.onBackground,
                fontWeight: FontWeight.w800,
              ),
            ),
            const Icon(
              Icons.arrow_drop_down_rounded,
              size: 18,
              color: _WorkbenchColors.onBackground,
            ),
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
              style: const TextStyle(
                color: _WorkbenchColors.onBackground,
                fontWeight: FontWeight.w900,
                fontSize: 15,
              ),
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
    final title = _diagramDisplayLabel(diagram);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openFullscreenDiagram(context, diagram, diagramRenderer),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            children: <Widget>[
              Icon(
                _diagramIcon(diagram),
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
                      style: const TextStyle(
                        color: _WorkbenchColors.onBackground,
                        fontWeight: FontWeight.w900,
                      ),
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
                            child: Text(
                              kind.label,
                              style: const TextStyle(
                                color: _WorkbenchColors.onBackground,
                              ),
                            ),
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
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    this.warning = false,
    this.onTap,
  });

  final String label;
  final String value;
  final bool warning;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final borderColor = warning
        ? _WorkbenchColors.warning
        : _WorkbenchColors.border;
    final fillColor = warning
        ? _WorkbenchColors.warningSurface
        : _WorkbenchColors.surfaceHigh;
    return Material(
      color: fillColor,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Container(
          width: 132,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: borderColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.secondaryText,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  if (onTap != null)
                    const Icon(
                      Icons.chevron_right_rounded,
                      size: 16,
                      color: _WorkbenchColors.secondaryText,
                    ),
                ],
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
        ),
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

class _StructuredPlan {
  const _StructuredPlan({required this.title, required this.stages});

  final String title;
  final List<_PlanStage> stages;
}

class _PlanStage {
  const _PlanStage({
    required this.order,
    required this.title,
    required this.description,
    required this.status,
    this.details = const <String>[],
  });

  final int order;
  final String title;
  final String description;
  final String status;
  final List<String> details;
}

_StructuredPlan? _parseStructuredPlan(String? content) {
  final normalized = content?.replaceAll('\r\n', '\n').trim();
  if (normalized == null || normalized.isEmpty) return null;
  final lines = normalized.split('\n');
  final title = _planTitle(lines);
  final yamlStages = _parseYamlLikePlanStages(lines);
  if (yamlStages.isNotEmpty) {
    return _StructuredPlan(title: title, stages: yamlStages);
  }
  final numberedStages = _parseNumberedPlanStages(lines);
  if (numberedStages.isNotEmpty) {
    return _StructuredPlan(title: title, stages: numberedStages);
  }
  final headingStages = _parseHeadingPlanStages(lines);
  if (headingStages.isNotEmpty) {
    return _StructuredPlan(title: title, stages: headingStages);
  }
  return null;
}

String _planTitle(List<String> lines) {
  for (final line in lines) {
    final trimmed = line.trim();
    if (!trimmed.startsWith('#')) continue;
    final title = trimmed.replaceFirst(RegExp(r'^#+\s*'), '').trim();
    if (title.isNotEmpty) return title;
  }
  return 'Plan';
}

List<_PlanStage> _parseNumberedPlanStages(List<String> lines) {
  final stages = <_PlanStage>[];
  final numbered = RegExp(r'^\s*(\d+)[\.)]\s+(.+)$');
  int? order;
  final buffer = StringBuffer();

  void flush() {
    final currentOrder = order;
    final text = buffer.toString().trim();
    if (currentOrder == null || text.isEmpty) return;
    final cleaned = _cleanPlanText(text);
    stages.add(
      _PlanStage(
        order: currentOrder,
        title: _planStageTitle(cleaned),
        description: cleaned,
        status: _statusFromPlanText(cleaned),
      ),
    );
    buffer.clear();
  }

  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
    final match = numbered.firstMatch(line);
    if (match != null) {
      flush();
      order = int.tryParse(match.group(1) ?? '') ?? (stages.length + 1);
      buffer.write(match.group(2)!.trim());
      continue;
    }
    if (order != null) {
      buffer.write(' ');
      buffer.write(trimmed.replaceFirst(RegExp(r'^[-*]\s+'), ''));
    }
  }
  flush();
  return stages;
}

List<_PlanStage> _parseHeadingPlanStages(List<String> lines) {
  final stages = <_PlanStage>[];
  String? title;
  final body = <String>[];

  void flush() {
    final currentTitle = title?.trim();
    if (currentTitle == null || currentTitle.isEmpty) return;
    final description = _cleanPlanText(body.join(' '));
    stages.add(
      _PlanStage(
        order: stages.length + 1,
        title: currentTitle,
        description: description,
        status: _statusFromPlanText('$currentTitle $description'),
      ),
    );
    body.clear();
  }

  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.startsWith('## ')) {
      flush();
      title = trimmed.replaceFirst(RegExp(r'^#+\s*'), '').trim();
    } else if (title != null &&
        trimmed.isNotEmpty &&
        !trimmed.startsWith('#')) {
      body.add(trimmed.replaceFirst(RegExp(r'^[-*]\s+'), ''));
    }
  }
  flush();
  return stages;
}

List<_PlanStage> _parseYamlLikePlanStages(List<String> lines) {
  final stages = <_PlanStage>[];
  final hasYamlShape = lines.any((line) {
    final trimmed = line.trimLeft();
    return trimmed.startsWith('- ') &&
        RegExp(
          r'\b(title|name|stage|status|description|task):',
        ).hasMatch(trimmed);
  });
  if (!hasYamlShape) return stages;

  final current = <String, String>{};
  final details = <String>[];

  void flush() {
    final title =
        current['title'] ??
        current['name'] ??
        current['stage'] ??
        current['id'];
    final description = current['description'] ?? current['task'] ?? '';
    if (title == null && description.trim().isEmpty && details.isEmpty) return;
    final fallbackTitle = description.trim().isNotEmpty
        ? _planStageTitle(description)
        : 'Stage ${stages.length + 1}';
    stages.add(
      _PlanStage(
        order: stages.length + 1,
        title: _cleanPlanText(title ?? fallbackTitle),
        description: _cleanPlanText(description),
        status: _cleanPlanText(current['status'] ?? 'planned'),
        details: details
            .map(_cleanPlanText)
            .where((detail) => detail.isNotEmpty)
            .toList(growable: false),
      ),
    );
    current.clear();
    details.clear();
  }

  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
    if (trimmed.startsWith('- ')) {
      final body = trimmed.substring(2).trim();
      final keyValue = _yamlKeyValue(body);
      if (keyValue == null) {
        if (current.isNotEmpty) {
          details.add(body);
        }
        continue;
      }
      if (current.isNotEmpty) flush();
      current[keyValue.$1] = keyValue.$2;
      continue;
    }
    final keyValue = _yamlKeyValue(trimmed);
    if (keyValue != null && current.isNotEmpty) {
      current[keyValue.$1] = keyValue.$2;
    } else if (current.isNotEmpty) {
      details.add(trimmed.replaceFirst(RegExp(r'^[-*]\s+'), ''));
    }
  }
  flush();
  return stages;
}

(String, String)? _yamlKeyValue(String text) {
  final separator = text.indexOf(':');
  if (separator <= 0) return null;
  final key = text.substring(0, separator).trim().toLowerCase();
  if (key.isEmpty || key.contains(' ')) return null;
  final value = text
      .substring(separator + 1)
      .trim()
      .replaceAll(RegExp(r'''^['"]|['"]$'''), '');
  return (key, value);
}

String _cleanPlanText(String text) {
  return text
      .replaceAllMapped(RegExp(r'`([^`]+)`'), (match) => match.group(1) ?? '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

bool _sameDisplayText(String left, String right) {
  String normalize(String value) => _cleanPlanText(
    value,
  ).toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
  final normalizedLeft = normalize(left);
  final normalizedRight = normalize(right);
  return normalizedLeft.isNotEmpty && normalizedLeft == normalizedRight;
}

String _planStageTitle(String text) {
  final cleaned = _cleanPlanText(text);
  if (cleaned.isEmpty) return 'Plan stage';
  final sentenceEnd = cleaned.indexOf(RegExp(r'[.:;]'));
  final end = sentenceEnd > 10 ? sentenceEnd : cleaned.length;
  final title = cleaned.substring(0, end).trim();
  if (title.length <= 72) return title;
  return '${title.substring(0, 69).trimRight()}...';
}

String _statusFromPlanText(String text) {
  final lower = text.toLowerCase();
  if (lower.contains('[x]') ||
      lower.contains('done') ||
      lower.contains('complete') ||
      lower.contains('validated')) {
    return 'complete';
  }
  if (lower.contains('blocked') || lower.contains('missing')) return 'blocked';
  if (lower.contains('validate') || lower.contains('test')) return 'validation';
  if (lower.contains('maintain') || lower.contains('preserve')) {
    return 'ongoing';
  }
  return 'planned';
}

bool _planStatusIsWarning(String status) {
  final normalized = status.toLowerCase();
  return normalized.contains('blocked') ||
      normalized.contains('missing') ||
      normalized.contains('failed');
}

class _PlanFileSection extends StatelessWidget {
  const _PlanFileSection({
    required this.file,
    this.title = 'plan.md',
    this.taskSections = const <_PlanTaskSectionData>[],
    this.feedbackTarget,
    this.onFeedback,
    this.actions = const <SddCodexActionKind>[],
    this.onCodexAction,
  });

  final String title;
  final SddFile? file;
  final List<_PlanTaskSectionData> taskSections;
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
    final plan = _parseStructuredPlan(value.content);
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
          if (plan != null) ...[
            const SizedBox(height: 10),
            _StructuredPlanView(plan: plan),
          ] else if (value.hasContent) ...[
            const SizedBox(height: 10),
            _ReadableMarkdownView(text: value.content!),
            const SizedBox(height: 8),
            _SourceExcerptDisclosure(text: value.content!),
          ],
          if (taskSections.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Divider(height: 1, color: _WorkbenchColors.border),
            const SizedBox(height: 12),
            Row(
              children: <Widget>[
                const Icon(
                  Icons.checklist_rounded,
                  size: 16,
                  color: _WorkbenchColors.primary,
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Tasks in this plan',
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                ),
                _TinyMetaChip(
                  icon: Icons.account_tree_outlined,
                  label: '${taskSections.length} task(s)',
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final task in taskSections) ...[
              _TaskFileSection(
                title: _artifactLabel(task.file, 'tasks.md'),
                file: task.file,
                planAssociation: task.planAssociation,
                feedbackTarget: task.feedbackTarget,
                onFeedback: onFeedback,
                actions: const <SddCodexActionKind>[
                  SddCodexActionKind.updateTasks,
                ],
                onCodexAction: onCodexAction,
                embedded: true,
              ),
              if (task.index != taskSections.last.index)
                const SizedBox(height: 8),
            ],
          ],
        ],
      ),
    );
  }
}

class _StructuredPlanView extends StatefulWidget {
  const _StructuredPlanView({required this.plan});

  final _StructuredPlan plan;

  @override
  State<_StructuredPlanView> createState() => _StructuredPlanViewState();
}

class _StructuredPlanViewState extends State<_StructuredPlanView> {
  final Set<int> _expanded = <int>{};

  @override
  void didUpdateWidget(_StructuredPlanView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.plan != widget.plan) {
      _expanded.clear();
    } else {
      _expanded.removeWhere((index) => index >= widget.plan.stages.length);
    }
  }

  @override
  Widget build(BuildContext context) {
    final stages = widget.plan.stages;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            const Icon(
              Icons.route_outlined,
              size: 16,
              color: _WorkbenchColors.primary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                widget.plan.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
            _TinyMetaChip(
              icon: Icons.view_timeline_outlined,
              label: '${stages.length} stages',
            ),
          ],
        ),
        const SizedBox(height: 10),
        for (final entry in stages.indexed) ...[
          if (entry.$1 > 0)
            const Divider(height: 12, color: _WorkbenchColors.border),
          _PlanStageRow(
            stage: entry.$2,
            expanded: _expanded.contains(entry.$1),
            onToggle: () {
              setState(() {
                if (!_expanded.remove(entry.$1)) {
                  _expanded.add(entry.$1);
                }
              });
            },
          ),
        ],
      ],
    );
  }
}

class _PlanStageRow extends StatelessWidget {
  const _PlanStageRow({
    required this.stage,
    required this.expanded,
    required this.onToggle,
  });

  final _PlanStage stage;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final status = _statusStyle(
      stage.status,
      warning: _planStatusIsWarning(stage.status),
    );
    final showDescription =
        stage.description.isNotEmpty &&
        !_sameDisplayText(stage.title, stage.description);
    final detailItems = stage.details
        .where(
          (detail) =>
              !_sameDisplayText(detail, stage.title) &&
              !_sameDisplayText(detail, stage.description),
        )
        .toList(growable: false);
    return Material(
      color: expanded
          ? status.color.withValues(alpha: 0.08)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onToggle,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  CircleAvatar(
                    radius: 13,
                    backgroundColor: status.color.withValues(alpha: 0.18),
                    child: Text(
                      '${stage.order}',
                      style: TextStyle(
                        color: status.color,
                        fontSize: 11,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          stage.title,
                          maxLines: expanded ? null : 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: expanded
                                ? _WorkbenchColors.onBackground
                                : _WorkbenchColors.secondaryText,
                            fontWeight: FontWeight.w900,
                            fontSize: 13,
                          ),
                        ),
                        if (showDescription) ...[
                          const SizedBox(height: 3),
                          Text(
                            stage.description,
                            maxLines: expanded ? null : 2,
                            overflow: expanded
                                ? TextOverflow.visible
                                : TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _WorkbenchColors.secondaryText,
                              fontSize: 12,
                              height: 1.25,
                            ),
                          ),
                        ],
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: <Widget>[
                            _TinyStatusPill(
                              label: stage.status,
                              warning: _planStatusIsWarning(stage.status),
                            ),
                            TextButton.icon(
                              onPressed: onToggle,
                              icon: Icon(
                                expanded
                                    ? Icons.keyboard_arrow_up_rounded
                                    : Icons.keyboard_arrow_down_rounded,
                                size: 17,
                              ),
                              label: Text(
                                expanded ? 'Hide details' : 'Show details',
                              ),
                              style: TextButton.styleFrom(
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                ),
                                minimumSize: const Size(0, 30),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (expanded && detailItems.isNotEmpty) ...[
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.only(left: 36),
                  child: _PlanStageDetail(details: detailItems),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanStageDetail extends StatelessWidget {
  const _PlanStageDetail({required this.details});

  final List<String> details;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _WorkbenchColors.sourceBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            ...details.map(
              (detail) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(
                      Icons.chevron_right_rounded,
                      size: 16,
                      color: _WorkbenchColors.primary,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        detail,
                        style: const TextStyle(
                          color: _WorkbenchColors.secondaryText,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TaskFileSection extends StatelessWidget {
  const _TaskFileSection({
    required this.file,
    this.title = 'tasks.md',
    this.planAssociation,
    this.feedbackTarget,
    this.onFeedback,
    this.actions = const <SddCodexActionKind>[],
    this.onCodexAction,
    this.embedded = false,
  });

  final String title;
  final SddFile? file;
  final String? planAssociation;
  final SddFeedbackTarget? feedbackTarget;
  final ValueChanged<SddFeedbackTarget>? onFeedback;
  final List<SddCodexActionKind> actions;
  final ValueChanged<SddCodexActionRequest>? onCodexAction;
  final bool embedded;

  @override
  Widget build(BuildContext context) {
    final tasks = _parseStructuredTasks(file?.content);
    final progress = tasks?.progress ?? _taskProgress(file?.content);
    final body = Column(
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
          if (planAssociation != null) ...[
            const SizedBox(height: 8),
            _TinyMetaChip(icon: Icons.route_outlined, label: planAssociation!),
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
            if (tasks != null)
              _StructuredTaskListView(tasks: tasks)
            else
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _ReadableMarkdownView(text: file!.content!),
                  const SizedBox(height: 8),
                  _SourceExcerptDisclosure(text: file!.content!),
                ],
              ),
          ],
        ],
      ],
    );
    if (!embedded) {
      return _PanelCard(child: body);
    }
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _WorkbenchColors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _WorkbenchColors.border),
      ),
      child: Padding(padding: const EdgeInsets.all(10), child: body),
    );
  }
}

class _StructuredTaskList {
  const _StructuredTaskList({required this.title, required this.tasks});

  final String title;
  final List<_StructuredTask> tasks;

  _TaskProgress get progress {
    final completed = tasks
        .where((task) => _taskStatusIsComplete(task.status))
        .length;
    return _TaskProgress(completed: completed, total: tasks.length);
  }
}

class _StructuredTask {
  const _StructuredTask({
    required this.order,
    required this.title,
    required this.status,
    this.details = const <String>[],
  });

  final int order;
  final String title;
  final String status;
  final List<String> details;
}

class _StructuredTaskListView extends StatefulWidget {
  const _StructuredTaskListView({required this.tasks});

  final _StructuredTaskList tasks;

  @override
  State<_StructuredTaskListView> createState() =>
      _StructuredTaskListViewState();
}

class _StructuredTaskListViewState extends State<_StructuredTaskListView> {
  final Set<int> _expanded = <int>{};

  @override
  void didUpdateWidget(_StructuredTaskListView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.tasks != widget.tasks) {
      _expanded.clear();
    } else {
      _expanded.removeWhere((index) => index >= widget.tasks.tasks.length);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tasks = widget.tasks;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            const Icon(
              Icons.task_alt_rounded,
              size: 16,
              color: _WorkbenchColors.primary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                tasks.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
            _TinyMetaChip(
              icon: Icons.checklist_rounded,
              label: '${tasks.tasks.length} tasks',
            ),
          ],
        ),
        const SizedBox(height: 8),
        for (final entry in tasks.tasks.indexed) ...[
          if (entry.$1 > 0)
            const Divider(height: 12, color: _WorkbenchColors.border),
          _StructuredTaskRow(
            task: entry.$2,
            expanded: _expanded.contains(entry.$1),
            onToggle: () {
              setState(() {
                if (!_expanded.remove(entry.$1)) {
                  _expanded.add(entry.$1);
                }
              });
            },
          ),
        ],
      ],
    );
  }
}

class _StructuredTaskRow extends StatelessWidget {
  const _StructuredTaskRow({
    required this.task,
    required this.expanded,
    required this.onToggle,
  });

  final _StructuredTask task;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final status = _statusStyle(task.status);
    return Material(
      color: expanded
          ? status.color.withValues(alpha: 0.08)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onToggle,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 5),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: 24,
                height: 24,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: status.color.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: status.color.withValues(alpha: 0.5),
                  ),
                ),
                child: Icon(status.icon, size: 14, color: status.color),
              ),
              const SizedBox(width: 9),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      task.title,
                      maxLines: expanded ? null : 2,
                      overflow: expanded
                          ? TextOverflow.visible
                          : TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _WorkbenchColors.onBackground,
                        fontSize: 12,
                        height: 1.25,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    if (task.details.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        task.details.join(' '),
                        maxLines: expanded ? null : 3,
                        overflow: expanded
                            ? TextOverflow.visible
                            : TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _WorkbenchColors.secondaryText,
                          fontSize: 11.5,
                          height: 1.25,
                        ),
                      ),
                    ],
                    const SizedBox(height: 5),
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: <Widget>[
                        _TinyStatusPill(label: task.status),
                        TextButton.icon(
                          onPressed: onToggle,
                          icon: Icon(
                            expanded
                                ? Icons.keyboard_arrow_up_rounded
                                : Icons.keyboard_arrow_down_rounded,
                            size: 17,
                          ),
                          label: Text(
                            expanded ? 'Hide details' : 'Show details',
                          ),
                          style: TextButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            minimumSize: const Size(0, 30),
                          ),
                        ),
                      ],
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

_TaskProgress? _specTaskProgress(SddSpec spec) {
  if (spec.taskTotal > 0) {
    return _TaskProgress(completed: spec.taskCompleted, total: spec.taskTotal);
  }
  var completed = 0;
  var total = 0;
  for (final file in spec.allTaskFiles) {
    final progress = _taskProgress(file.content);
    if (progress == null) continue;
    completed += progress.completed;
    total += progress.total;
  }
  if (total == 0) return null;
  return _TaskProgress(completed: completed, total: total);
}

int _specPlanCount(SddSpec spec) {
  return spec.tree?.plans.length ?? spec.allPlanFiles.length;
}

int _specTaskCount(SddSpec spec) {
  final tree = spec.tree;
  if (tree != null) {
    return tree.plans.fold<int>(0, (total, plan) => total + plan.tasks.length);
  }
  return spec.allTaskFiles.length;
}

bool _specNeedsDetail(SddSpec spec) {
  final tree = spec.tree;
  if (tree != null && _treeNeedsDetail(tree)) {
    return true;
  }
  return <SddFile>[
    ...spec.allPlanFiles,
    ...spec.allTaskFiles,
    ...spec.sliceDocs,
  ].any(_fileNeedsDetail);
}

bool _treeNeedsDetail(SddSpecTree tree) {
  if (_fileNeedsDetail(tree.file)) return true;
  for (final plan in tree.plans) {
    if (_fileNeedsDetail(plan.file)) return true;
    for (final task in plan.tasks) {
      if (_fileNeedsDetail(task.file)) return true;
    }
  }
  return false;
}

bool _fileNeedsDetail(SddFile? file) {
  if (file == null) return false;
  return file.content == null && file.error == null;
}

_TaskProgress? _taskProgress(String? content) {
  return _parseStructuredTasks(content)?.progress;
}

_StructuredTaskList? _parseStructuredTasks(String? content) {
  final normalized = content?.replaceAll('\r\n', '\n').trim();
  if (normalized == null || normalized.isEmpty) return null;
  final lines = normalized.split('\n');
  final tasks = <_StructuredTask>[];
  final details = <String>[];
  var title = 'Tasks';
  String? taskTitle;
  String? status;
  final taskStart = RegExp(
    r'^\s*[-*]\s+(?:\[([ xX])\]|\[status:\s*([^\]]+)\])\s*(.*)$',
  );

  void flush() {
    final currentTitle = taskTitle?.trim();
    final currentStatus = status?.trim();
    if (currentTitle == null ||
        currentTitle.isEmpty ||
        currentStatus == null ||
        currentStatus.isEmpty) {
      return;
    }
    tasks.add(
      _StructuredTask(
        order: tasks.length + 1,
        title: _cleanTaskText(currentTitle),
        status: currentStatus,
        details: details
            .map(_cleanTaskText)
            .where((detail) => detail.isNotEmpty)
            .toList(growable: false),
      ),
    );
    taskTitle = null;
    status = null;
    details.clear();
  }

  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) continue;
    if (trimmed.startsWith('#')) {
      if (title == 'Tasks') {
        final heading = trimmed.replaceFirst(RegExp(r'^#+\s*'), '').trim();
        if (heading.isNotEmpty) title = heading;
      }
      continue;
    }
    final match = taskStart.firstMatch(line);
    if (match != null) {
      flush();
      final checkbox = match.group(1);
      status = checkbox == null
          ? match.group(2)!.trim()
          : checkbox.toLowerCase() == 'x'
          ? 'done'
          : 'planned';
      taskTitle = match.group(3)!.trim();
      continue;
    }
    if (taskTitle != null) {
      details.add(trimmed.replaceFirst(RegExp(r'^[-*]\s+'), ''));
    }
  }
  flush();
  if (tasks.isEmpty) return null;
  return _StructuredTaskList(title: title, tasks: tasks);
}

String _cleanTaskText(String text) {
  return text
      .replaceAllMapped(RegExp(r'`([^`]+)`'), (match) => match.group(1) ?? '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

bool _taskStatusIsComplete(String status) {
  return _normalizeStatus(status) == 'done';
}

String _specDescription(SddSpec spec) {
  final explicit = spec.description.trim();
  if (explicit.isNotEmpty) return explicit;
  final content = spec.spec?.content?.trim();
  if (content == null || content.isEmpty) return 'No description yet.';
  final lines = content
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty && !line.startsWith('#'))
      .toList(growable: false);
  if (lines.isEmpty) return 'No description yet.';
  return lines.first.length > 180
      ? '${lines.first.substring(0, 177)}...'
      : lines.first;
}

String? _formatShortDate(String? value) {
  final trimmed = value?.trim();
  if (trimmed == null || trimmed.isEmpty) return null;
  final parsed = DateTime.tryParse(trimmed);
  if (parsed == null) return trimmed;
  final local = parsed.toLocal();
  String twoDigits(int number) => number.toString().padLeft(2, '0');
  return '${local.year}-${twoDigits(local.month)}-${twoDigits(local.day)}';
}

String _specLifecycleStatus(SddSpec spec) {
  final explicit = spec.lifecycleStatus.trim();
  if (explicit.isNotEmpty && explicit.toLowerCase() != 'unknown') {
    return explicit;
  }
  return _frontMatterValue(spec.spec?.content, 'status') ?? 'draft';
}

String _specTraceabilityStatus(SddSpec spec) {
  if (spec.traceabilityStatus.trim().isNotEmpty &&
      spec.traceabilityStatus != 'unknown') {
    return spec.traceabilityStatus;
  }
  if (spec.metadataStatus.trim().isEmpty ||
      spec.metadataStatus.toLowerCase() == 'unknown') {
    return 'needs metadata';
  }
  if (spec.missing.isNotEmpty) return 'incomplete';
  final tree = spec.tree;
  if (tree != null) {
    return tree.isComplete ? 'linked' : 'incomplete';
  }
  if (spec.allSpecFiles.isEmpty ||
      spec.allPlanFiles.isEmpty ||
      spec.allTaskFiles.isEmpty) {
    return 'not linked';
  }
  return 'linked';
}

List<_GovernanceItem> _baselineArtifacts(SddProject project) {
  return <_GovernanceItem>[
    ...project.architectureDiagrams.map(
      (diagram) => _GovernanceItem(
        kind: 'Architecture',
        label: '${diagram.path} · ${_diagramTypeLabel(diagram.diagramType)}',
        warning: false,
      ),
    ),
    const _GovernanceItem(
      kind: 'Domain',
      label: 'Domain baseline files are not loaded by this snapshot',
      warning: true,
    ),
    const _GovernanceItem(
      kind: 'Data',
      label: 'Data baseline files are not loaded by this snapshot',
      warning: true,
    ),
  ];
}

List<_GovernanceItem> _impactQueueItems(SddProject project) {
  final items = <_GovernanceItem>[
    ...project.architectureDiagrams.map(
      (diagram) => _GovernanceItem(
        kind: 'Architecture',
        label: '${diagram.path} requires baseline impact review before edits',
        warning: true,
      ),
    ),
  ];
  for (final spec in project.specs) {
    for (final diagram in spec.diagrams) {
      if (diagram.diagramType == 'component-impact' ||
          diagram.diagramType == 'domain-impact' ||
          diagram.diagramType == 'data-impact') {
        items.add(
          _GovernanceItem(
            kind: spec.id,
            label:
                '${diagram.path} · ${_diagramTypeLabel(diagram.diagramType)}',
            warning: true,
          ),
        );
      }
    }
  }
  return items;
}

String? _frontMatterValue(String? content, String key) {
  if (content == null || !content.startsWith('---')) return null;
  final lines = content.split('\n');
  for (final line in lines.skip(1)) {
    if (line.trim() == '---') return null;
    final separator = line.indexOf(':');
    if (separator <= 0) continue;
    final rawKey = line.substring(0, separator).trim();
    if (rawKey != key) continue;
    final value = line.substring(separator + 1).trim();
    return value.isEmpty ? null : value;
  }
  return null;
}

class _GovernanceItem {
  const _GovernanceItem({
    required this.kind,
    required this.label,
    required this.warning,
  });

  final String kind;
  final String label;
  final bool warning;
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
    targetWorkspaceName: _projectDisplayName(project),
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
    targetWorkspaceName: _projectDisplayName(project),
    artifactType: 'diagram',
    artifactPath: _safeMetadataPath(diagram.path),
    artifactTitle: _diagramDisplayLabel(diagram),
    sourceExcerpt: _sourceExcerpt(diagram.content),
    specId: spec?.id,
    specTitle: spec?.title,
    diagramType: diagram.diagramType,
    diagramScope: diagram.scope,
  );
}

T? _fileAt<T>(List<T> files, int index) {
  if (index < 0 || index >= files.length) return null;
  return files[index];
}

String _artifactLabel(SddFile? file, String fallback) {
  final title = file?.title?.trim();
  if (title != null && title.isNotEmpty) return title;
  return _artifactPathLabel(file, fallback);
}

String _artifactPathLabel(SddFile? file, String fallback) {
  final path = file?.path.trim();
  if (path == null || path.isEmpty) return fallback;
  return path.split('/').last;
}

String _diagramDisplayLabel(SddDiagram diagram) {
  final title = diagram.title?.trim();
  if (title != null && title.isNotEmpty) return title;
  return '${_diagramTypeLabel(diagram.diagramType, path: diagram.path, content: diagram.content)} diagram';
}

String _diagramTypeLabel(String rawType, {String? path, String? content}) {
  final type = rawType.trim();
  final normalized = type.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
  final source = (content ?? '').trimLeft().toLowerCase();
  final lowerPath = (path ?? '').toLowerCase();
  if (source.startsWith('classdiagram') || normalized == 'classdiagram') {
    return 'UML class';
  }
  if (source.startsWith('sequencediagram') || normalized == 'sequencediagram') {
    return 'UML sequence';
  }
  if (source.startsWith('statediagram') || normalized == 'statediagram') {
    return 'UML state';
  }
  if (source.startsWith('erdiagram') || normalized == 'erdiagram') {
    return 'ER';
  }
  if (source.startsWith('c4component') || normalized == 'c4component') {
    return 'C4 component';
  }
  if (normalized.contains('component') ||
      lowerPath.contains('component') ||
      lowerPath.contains('/components')) {
    return 'UML component';
  }
  return switch (normalized) {
    'flowchart' || 'graph' => 'Flowchart',
    'architecture' => 'Architecture',
    'journey' => 'User journey',
    'gantt' => 'Gantt',
    'mindmap' => 'Mind map',
    'timeline' => 'Timeline',
    '' || 'unknown' => 'Diagram',
    _ => type,
  };
}

IconData _diagramIcon(SddDiagram diagram) {
  final label = _diagramTypeLabel(
    diagram.diagramType,
    path: diagram.path,
    content: diagram.content,
  ).toLowerCase();
  if (label.contains('sequence')) return Icons.swap_horiz_rounded;
  if (label.contains('class')) return Icons.schema_outlined;
  if (label.contains('state')) return Icons.sync_alt_rounded;
  if (label.contains('component') || label.contains('architecture')) {
    return Icons.account_tree_outlined;
  }
  return Icons.hub_outlined;
}

String _diagramHeaderSubtitle(SddDiagram diagram) {
  final type = _diagramTypeLabel(
    diagram.diagramType,
    path: diagram.path,
    content: diagram.content,
  );
  final scope = diagram.scope.trim();
  if (scope.isEmpty) return type;
  return '$scope · $type';
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
    this.specBodyMode = false,
    this.feedbackTarget,
    this.onFeedback,
    this.actions = const <SddCodexActionKind>[],
    this.onCodexAction,
  });

  final String title;
  final SddFile? file;
  final bool specBodyMode;
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
            if (specBodyMode)
              _SpecBodySectionSelector(text: value.content!)
            else
              _ReadableMarkdownView(text: value.content!),
            const SizedBox(height: 8),
            _SourceExcerptDisclosure(text: value.content!),
          ],
        ],
      ),
    );
  }
}

class _SpecBodySectionSelector extends StatefulWidget {
  const _SpecBodySectionSelector({required this.text});

  final String text;

  @override
  State<_SpecBodySectionSelector> createState() =>
      _SpecBodySectionSelectorState();
}

class _SpecBodySectionSelectorState extends State<_SpecBodySectionSelector> {
  int _selectedIndex = 0;

  @override
  void didUpdateWidget(_SpecBodySectionSelector oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.text != widget.text) {
      _selectedIndex = 0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final sections = _specBodySections(widget.text);
    if (sections.isEmpty) {
      return _ReadableMarkdownView(text: widget.text, skipFirstHeading: true);
    }
    final selectedIndex = _selectedIndex.clamp(0, sections.length - 1).toInt();
    final selected = sections[selectedIndex];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: <Widget>[
            for (final entry in sections.indexed)
              ChoiceChip(
                label: Text(entry.$2.title),
                selected: entry.$1 == selectedIndex,
                visualDensity: VisualDensity.compact,
                onSelected: (_) {
                  setState(() {
                    _selectedIndex = entry.$1;
                  });
                },
              ),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: _WorkbenchColors.sourceBackground.withValues(alpha: 0.42),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: _WorkbenchColors.border),
          ),
          child: _MarkdownBlocksView(blocks: selected.blocks),
        ),
      ],
    );
  }
}

class _SpecBodySection {
  const _SpecBodySection({required this.title, required this.blocks});

  final String title;
  final List<_MarkdownBlock> blocks;
}

List<_SpecBodySection> _specBodySections(String source) {
  final sections = <_SpecBodySection>[];
  final blocks = _markdownBlocks(source);
  String? activeTitle;
  final activeBlocks = <_MarkdownBlock>[];

  void flush() {
    if (activeTitle == null) return;
    sections.add(
      _SpecBodySection(
        title: activeTitle,
        blocks: List<_MarkdownBlock>.unmodifiable(activeBlocks),
      ),
    );
    activeBlocks.clear();
  }

  for (final entry in blocks.indexed) {
    final block = entry.$2;
    if (block.kind == _MarkdownBlockKind.heading) {
      if (entry.$1 == 0 && block.level <= 1) {
        continue;
      }
      flush();
      activeTitle = _commonSpecSectionTitle(block.text) ?? block.text;
      continue;
    }
    if (activeTitle != null) {
      activeBlocks.add(block);
    }
  }
  flush();
  return sections
      .where((section) => section.blocks.isNotEmpty)
      .toList(growable: false);
}

String? _commonSpecSectionTitle(String raw) {
  final normalized = raw
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
      .trim();
  return switch (normalized) {
    'intent' => 'Intent',
    'scope' => 'Scope',
    'functional requirements' ||
    'functional requirement' ||
    'requirements' => 'Functional Requirements',
    'domain rules' || 'domain rule' || 'rules' => 'Domain Rules',
    'acceptance criteria' || 'acceptance' => 'Acceptance Criteria',
    _ => null,
  };
}

class _ReadableMarkdownView extends StatelessWidget {
  const _ReadableMarkdownView({
    required this.text,
    this.skipFirstHeading = false,
  });

  final String text;
  final bool skipFirstHeading;

  @override
  Widget build(BuildContext context) {
    final blocks = _markdownBlocks(text).toList(growable: false);
    final visibleBlocks =
        skipFirstHeading &&
            blocks.isNotEmpty &&
            blocks.first.kind == _MarkdownBlockKind.heading
        ? blocks.skip(1).toList(growable: false)
        : blocks;
    if (visibleBlocks.isEmpty) {
      return const Text(
        'No readable content yet.',
        style: TextStyle(color: _WorkbenchColors.secondaryText),
      );
    }
    return _MarkdownBlocksView(blocks: visibleBlocks);
  }
}

class _MarkdownBlocksView extends StatelessWidget {
  const _MarkdownBlocksView({required this.blocks});

  final List<_MarkdownBlock> blocks;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final block in blocks) _MarkdownBlockView(block: block),
      ],
    );
  }
}

class _MarkdownBlockView extends StatelessWidget {
  const _MarkdownBlockView({required this.block});

  final _MarkdownBlock block;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: block.kind == _MarkdownBlockKind.heading ? 8 : 6,
      ),
      child: switch (block.kind) {
        _MarkdownBlockKind.heading => Text(
          block.text,
          style: TextStyle(
            color: _WorkbenchColors.onBackground,
            fontSize: block.level <= 1 ? 16 : 14,
            fontWeight: FontWeight.w900,
          ),
        ),
        _MarkdownBlockKind.bullet => _MarkdownBullet(text: block.text),
        _MarkdownBlockKind.numbered => _MarkdownBullet(
          text: block.text,
          marker: '${block.level}.',
        ),
        _MarkdownBlockKind.check => _MarkdownBullet(
          text: block.text,
          icon: block.checked == true
              ? Icons.check_circle_rounded
              : Icons.radio_button_unchecked_rounded,
          iconColor: block.checked == true
              ? const Color(0xFF76E4A6)
              : _WorkbenchColors.secondaryText,
        ),
        _MarkdownBlockKind.paragraph => Text(
          block.text,
          style: const TextStyle(
            color: _WorkbenchColors.secondaryText,
            fontSize: 12.5,
            height: 1.35,
          ),
        ),
      },
    );
  }
}

class _MarkdownBullet extends StatelessWidget {
  const _MarkdownBullet({
    required this.text,
    this.marker,
    this.icon,
    this.iconColor,
  });

  final String text;
  final String? marker;
  final IconData? icon;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SizedBox(
          width: 22,
          child: icon == null
              ? Text(
                  marker ?? '•',
                  style: const TextStyle(
                    color: _WorkbenchColors.primary,
                    fontWeight: FontWeight.w900,
                  ),
                )
              : Icon(icon, size: 15, color: iconColor),
        ),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              color: _WorkbenchColors.secondaryText,
              fontSize: 12.5,
              height: 1.3,
            ),
          ),
        ),
      ],
    );
  }
}

class _SourceExcerptDisclosure extends StatelessWidget {
  const _SourceExcerptDisclosure({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      visualDensity: VisualDensity.compact,
      title: const Text(
        'Source excerpt',
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w900),
      ),
      children: <Widget>[_SourceBlock(text: _sourceExcerpt(text))],
    );
  }
}

enum _MarkdownBlockKind { heading, paragraph, bullet, numbered, check }

class _MarkdownBlock {
  const _MarkdownBlock({
    required this.kind,
    required this.text,
    this.level = 1,
    this.checked,
  });

  final _MarkdownBlockKind kind;
  final String text;
  final int level;
  final bool? checked;
}

List<_MarkdownBlock> _markdownBlocks(String source) {
  final normalized = source.replaceAll('\r\n', '\n');
  final blocks = <_MarkdownBlock>[];
  final paragraph = StringBuffer();
  var inFrontMatter = normalized.trimLeft().startsWith('---');
  var frontMatterStarted = false;

  void flushParagraph() {
    final text = _cleanMarkdownText(paragraph.toString());
    if (text.isNotEmpty) {
      blocks.add(
        _MarkdownBlock(kind: _MarkdownBlockKind.paragraph, text: text),
      );
    }
    paragraph.clear();
  }

  for (final line in normalized.split('\n')) {
    final trimmed = line.trim();
    if (inFrontMatter) {
      if (trimmed == '---' && frontMatterStarted) {
        inFrontMatter = false;
      } else if (trimmed == '---') {
        frontMatterStarted = true;
      }
      continue;
    }
    if (trimmed.isEmpty) {
      flushParagraph();
      continue;
    }
    final heading = RegExp(r'^(#{1,6})\s+(.+)$').firstMatch(trimmed);
    if (heading != null) {
      flushParagraph();
      blocks.add(
        _MarkdownBlock(
          kind: _MarkdownBlockKind.heading,
          level: heading.group(1)!.length,
          text: _cleanMarkdownText(heading.group(2)!),
        ),
      );
      continue;
    }
    final check = RegExp(r'^[-*]\s+\[([ xX])\]\s+(.+)$').firstMatch(trimmed);
    if (check != null) {
      flushParagraph();
      blocks.add(
        _MarkdownBlock(
          kind: _MarkdownBlockKind.check,
          checked: check.group(1)!.toLowerCase() == 'x',
          text: _cleanMarkdownText(check.group(2)!),
        ),
      );
      continue;
    }
    final bullet = RegExp(r'^[-*]\s+(.+)$').firstMatch(trimmed);
    if (bullet != null) {
      flushParagraph();
      blocks.add(
        _MarkdownBlock(
          kind: _MarkdownBlockKind.bullet,
          text: _cleanMarkdownText(bullet.group(1)!),
        ),
      );
      continue;
    }
    final numbered = RegExp(r'^(\d+)[\.)]\s+(.+)$').firstMatch(trimmed);
    if (numbered != null) {
      flushParagraph();
      blocks.add(
        _MarkdownBlock(
          kind: _MarkdownBlockKind.numbered,
          level: int.tryParse(numbered.group(1)!) ?? 1,
          text: _cleanMarkdownText(numbered.group(2)!),
        ),
      );
      continue;
    }
    if (paragraph.isNotEmpty) paragraph.write(' ');
    paragraph.write(trimmed);
  }
  flushParagraph();
  return blocks;
}

String _cleanMarkdownText(String text) {
  return text
      .replaceAllMapped(RegExp(r'`([^`]+)`'), (match) => match.group(1) ?? '')
      .replaceAll(RegExp(r'\*\*([^*]+)\*\*'), r'$1')
      .replaceAll(RegExp(r'\*([^*]+)\*'), r'$1')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

class _SpecDiagramListCard extends StatelessWidget {
  const _SpecDiagramListCard({
    required this.project,
    required this.spec,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final SddProject project;
  final SddSpec spec;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    if (spec.diagrams.isEmpty) {
      return const _InfoCard(
        title: 'Spec diagrams',
        detail: 'No diagrams found',
      );
    }
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.account_tree_outlined,
                size: 16,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Diagrams in this spec',
                  style: TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              _TinyMetaChip(
                icon: Icons.open_in_full_rounded,
                label: 'tap to open',
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final diagram in spec.diagrams)
            _DiagramListTile(
              item: _DiagramListItem(diagram: diagram, spec: spec),
              project: project,
              diagramRenderer: diagramRenderer,
              onFeedback: onFeedback,
              onCodexAction: onCodexAction,
            ),
        ],
      ),
    );
  }
}

class _ScopedDiagramListCard extends StatelessWidget {
  const _ScopedDiagramListCard({
    required this.title,
    required this.diagrams,
    required this.project,
    required this.spec,
    required this.diagramRenderer,
    required this.onFeedback,
    required this.onCodexAction,
  });

  final String title;
  final List<SddDiagram> diagrams;
  final SddProject project;
  final SddSpec spec;
  final MermaidDiagramRenderer diagramRenderer;
  final ValueChanged<SddFeedbackTarget> onFeedback;
  final ValueChanged<SddCodexActionRequest> onCodexAction;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.account_tree_outlined,
                size: 16,
                color: _WorkbenchColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              _TinyMetaChip(
                icon: Icons.open_in_full_rounded,
                label: '${diagrams.length} diagram(s)',
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final diagram in diagrams)
            _DiagramListTile(
              item: _DiagramListItem(diagram: diagram, spec: spec),
              project: project,
              diagramRenderer: diagramRenderer,
              onFeedback: onFeedback,
              onCodexAction: onCodexAction,
            ),
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
            title: _diagramDisplayLabel(diagram),
            file: diagram,
            subtitle: _diagramHeaderSubtitle(diagram),
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
                renderFuture: _renderFuture,
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
    required this.renderFuture,
    required this.onRetry,
  });

  final SddDiagram diagram;
  final Future<MermaidRenderResult> renderFuture;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<MermaidRenderResult>(
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
            sourceText: diagram.content ?? '',
            onRetry: onRetry,
          );
        }
        final result = snapshot.data;
        if (result == null || !result.isSuccess) {
          return _DiagramRenderError(
            message: result?.error ?? 'Could not render diagram preview.',
            sourceText: diagram.content ?? '',
            onRetry: onRetry,
          );
        }
        return _PreviewFrame(child: result.preview!);
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

void _openFullscreenDiagram(
  BuildContext context,
  SddDiagram diagram,
  MermaidDiagramRenderer diagramRenderer,
) {
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
                _diagramDisplayLabel(widget.diagram),
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
              child: Text(
                kind.label,
                style: const TextStyle(color: _WorkbenchColors.onBackground),
              ),
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
    required this.metaWorkspaceLabel,
    required this.submitter,
    required this.onActionSubmitted,
    this.metaWorkspacePath,
  });

  final String bridgeUrl;
  final SddCodexActionRequest request;
  final String? metaWorkspacePath;
  final String metaWorkspaceLabel;
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
  bool _runInMetaWorkspace = false;
  SddCodexActionSubmissionResult? _accepted;
  String? _errorText;

  String? get _configuredMetaWorkspacePath {
    final value = widget.metaWorkspacePath?.trim();
    if (value == null || value.isEmpty) {
      return null;
    }
    return value;
  }

  String get _executionWorkspacePath {
    final metaWorkspacePath = _configuredMetaWorkspacePath;
    if (_runInMetaWorkspace && metaWorkspacePath != null) {
      return metaWorkspacePath;
    }
    return widget.request.target.workspacePath;
  }

  String get _executionWorkspaceLabel {
    final metaWorkspacePath = _configuredMetaWorkspacePath;
    if (_runInMetaWorkspace && metaWorkspacePath != null) {
      return widget.metaWorkspaceLabel;
    }
    return 'Current project';
  }

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
        SddCodexActionDraft(
          request: widget.request,
          prompt: prompt,
          executionWorkspacePath: _executionWorkspacePath,
          executionWorkspaceLabel: _executionWorkspaceLabel,
        ),
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
              _ExecutionWorkspaceSelector(
                currentWorkspacePath: request.target.workspacePath,
                metaWorkspacePath: _configuredMetaWorkspacePath,
                metaWorkspaceLabel: widget.metaWorkspaceLabel,
                runInMetaWorkspace: _runInMetaWorkspace,
                enabled: !_submitting && accepted == null,
                onChanged: (value) {
                  setState(() {
                    _runInMetaWorkspace = value;
                  });
                },
              ),
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

class _ExecutionWorkspaceSelector extends StatelessWidget {
  const _ExecutionWorkspaceSelector({
    required this.currentWorkspacePath,
    required this.metaWorkspacePath,
    required this.metaWorkspaceLabel,
    required this.runInMetaWorkspace,
    required this.enabled,
    required this.onChanged,
  });

  final String currentWorkspacePath;
  final String? metaWorkspacePath;
  final String metaWorkspaceLabel;
  final bool runInMetaWorkspace;
  final bool enabled;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final hasMetaTarget =
        metaWorkspacePath != null && metaWorkspacePath!.isNotEmpty;
    final effectiveLabel = runInMetaWorkspace && hasMetaTarget
        ? metaWorkspaceLabel
        : 'Current project';
    final effectivePath = runInMetaWorkspace && hasMetaTarget
        ? metaWorkspacePath!
        : currentWorkspacePath;
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
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            dense: true,
            value: hasMetaTarget && runInMetaWorkspace,
            onChanged: enabled && hasMetaTarget ? onChanged : null,
            title: const Text(
              'Run against Workbench platform repo',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            subtitle: Text(
              hasMetaTarget
                  ? 'Off: change this project. On: change shared Workbench/Bridge behavior.'
                  : 'No platform workspace was configured by this app.',
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Execution target: $effectiveLabel',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
          ),
          const SizedBox(height: 2),
          Text(
            effectivePath,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _WorkbenchColors.secondaryText,
              fontSize: 12,
            ),
          ),
        ],
      ),
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
        Text(
          title,
          style: const TextStyle(
            color: _WorkbenchColors.onBackground,
            fontWeight: FontWeight.w800,
          ),
        ),
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

class _SpecDetailErrorCard extends StatelessWidget {
  const _SpecDetailErrorCard({required this.errorText, required this.onRetry});

  final String errorText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Could not load spec detail',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Text(
            errorText,
            style: const TextStyle(color: _WorkbenchColors.secondaryText),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Retry spec'),
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
