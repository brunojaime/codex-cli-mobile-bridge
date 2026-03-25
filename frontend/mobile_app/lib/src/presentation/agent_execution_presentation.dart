import 'package:flutter/material.dart';

import '../models/agent_configuration.dart';
import '../models/current_run_execution.dart';
import '../models/reviewer_lifecycle_state.dart';
import '../models/session_detail.dart';

class ReviewerLifecyclePresentation {
  const ReviewerLifecyclePresentation({
    required this.title,
    required this.statusLine,
    required this.subtitle,
    required this.icon,
    required this.bannerBackgroundColor,
    required this.bannerForegroundColor,
    required this.accentColor,
  });

  final String title;
  final String statusLine;
  final String subtitle;
  final IconData icon;
  final Color bannerBackgroundColor;
  final Color bannerForegroundColor;
  final Color accentColor;
}

class RunStagePresentation {
  const RunStagePresentation({
    required this.statusLabel,
    required this.subtitle,
    required this.icon,
    required this.color,
  });

  final String statusLabel;
  final String subtitle;
  final IconData icon;
  final Color color;
}

String resolveAgentLabel(SessionDetail session, AgentId agentId) {
  final configuredLabel =
      session.agentConfiguration.byId(agentId)?.label.trim();
  if (configuredLabel != null && configuredLabel.isNotEmpty) {
    return configuredLabel;
  }
  return switch (agentId) {
    AgentId.generator => 'Generator',
    AgentId.reviewer => 'Reviewer',
    AgentId.summary => 'Summary',
    AgentId.supervisor => 'Supervisor',
    AgentId.qa => 'QA',
    AgentId.ux => 'UX',
    AgentId.seniorEngineer => 'Senior Engineer',
    AgentId.user => 'User',
  };
}

ReviewerLifecyclePresentation buildReviewerLifecyclePresentation(
  SessionDetail session,
) {
  final reviewerLabel = resolveAgentLabel(session, AgentId.reviewer);
  switch (session.reviewerState) {
    case ReviewerLifecycleState.off:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel inactive',
        statusLine: '$reviewerLabel off',
        subtitle: 'Auto mode is off for this chat.',
        icon: Icons.pause_circle_outline,
        bannerBackgroundColor: const Color(0xFF1E2944),
        bannerForegroundColor: const Color(0xFFB8C8EA),
        accentColor: const Color(0xFF8B97B5),
      );
    case ReviewerLifecycleState.disabled:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel disabled',
        statusLine: '$reviewerLabel disabled',
        subtitle: 'Auto mode is on, but reviewer turns are disabled.',
        icon: Icons.visibility_off_outlined,
        bannerBackgroundColor: const Color(0xFF362411),
        bannerForegroundColor: const Color(0xFFFFD08A),
        accentColor: const Color(0xFFFFC857),
      );
    case ReviewerLifecycleState.idle:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel ready',
        statusLine: '$reviewerLabel ready',
        subtitle: 'Waiting for the next auto-mode run.',
        icon: Icons.schedule_outlined,
        bannerBackgroundColor: const Color(0xFF1E2944),
        bannerForegroundColor: const Color(0xFFB8C8EA),
        accentColor: const Color(0xFF9FD3FF),
      );
    case ReviewerLifecycleState.waitingOnGenerator:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel waiting on generator',
        statusLine: '$reviewerLabel waiting on generator',
        subtitle: 'The generator has not finished the current run yet.',
        icon: Icons.hourglass_bottom_rounded,
        bannerBackgroundColor: const Color(0xFF1E2944),
        bannerForegroundColor: const Color(0xFF9FD3FF),
        accentColor: const Color(0xFF9FD3FF),
      );
    case ReviewerLifecycleState.queued:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel queued',
        statusLine: '$reviewerLabel queued',
        subtitle: 'The reviewer turn is reserved and will start next.',
        icon: Icons.queue_rounded,
        bannerBackgroundColor: const Color(0xFF17323E),
        bannerForegroundColor: const Color(0xFF8FEAFF),
        accentColor: const Color(0xFF8FEAFF),
      );
    case ReviewerLifecycleState.running:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel running',
        statusLine: '$reviewerLabel running',
        subtitle: 'The reviewer is actively working on this run.',
        icon: Icons.sync_rounded,
        bannerBackgroundColor: const Color(0xFF17323E),
        bannerForegroundColor: const Color(0xFF55D6BE),
        accentColor: const Color(0xFF55D6BE),
      );
    case ReviewerLifecycleState.completed:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel completed',
        statusLine: '$reviewerLabel completed',
        subtitle: 'The reviewer has already acted on this run.',
        icon: Icons.verified_rounded,
        bannerBackgroundColor: const Color(0xFF1F4D45),
        bannerForegroundColor: const Color(0xFFB6F4E4),
        accentColor: const Color(0xFF55D6BE),
      );
    case ReviewerLifecycleState.failed:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel failed',
        statusLine: '$reviewerLabel failed',
        subtitle: 'The reviewer turn failed and needs attention.',
        icon: Icons.error_outline_rounded,
        bannerBackgroundColor: const Color(0xFF3B1521),
        bannerForegroundColor: const Color(0xFFFFB3B3),
        accentColor: const Color(0xFFFFB3B3),
      );
    case ReviewerLifecycleState.skipped:
      return ReviewerLifecyclePresentation(
        title: '$reviewerLabel skipped',
        statusLine: '$reviewerLabel skipped',
        subtitle: 'This run finished without a reviewer turn.',
        icon: Icons.skip_next_rounded,
        bannerBackgroundColor: const Color(0xFF362411),
        bannerForegroundColor: const Color(0xFFFFD08A),
        accentColor: const Color(0xFFFFC857),
      );
  }
}

RunStagePresentation buildRunStagePresentation(CurrentRunStageExecution stage) {
  final metadata = <String>[
    if (stage.attemptCount > 1) 'Attempt ${stage.attemptCount}',
    if (stage.jobId != null && stage.jobId!.isNotEmpty)
      'Job ${_shortId(stage.jobId!)}',
  ];
  final metadataText = metadata.join(' • ');
  switch (stage.state) {
    case CurrentRunStageState.disabled:
      return RunStagePresentation(
        statusLabel: 'Disabled',
        subtitle: 'This stage is not configured for the current mode.',
        icon: Icons.visibility_off_outlined,
        color: const Color(0xFFFFC857),
      );
    case CurrentRunStageState.waiting:
      return RunStagePresentation(
        statusLabel: 'Waiting',
        subtitle: metadataText.isNotEmpty
            ? metadataText
            : 'Waiting for the previous stage to finish.',
        icon: Icons.schedule_outlined,
        color: const Color(0xFF9FD3FF),
      );
    case CurrentRunStageState.notScheduled:
      return RunStagePresentation(
        statusLabel: 'Not scheduled yet',
        subtitle: metadataText.isNotEmpty
            ? metadataText
            : 'The stage should start soon, but no job is attached yet.',
        icon: Icons.more_horiz_rounded,
        color: const Color(0xFF8FEAFF),
      );
    case CurrentRunStageState.queued:
      return RunStagePresentation(
        statusLabel: 'Queued',
        subtitle: metadataText.isNotEmpty
            ? metadataText
            : 'Reserved and waiting to start.',
        icon: Icons.queue_rounded,
        color: const Color(0xFF8FEAFF),
      );
    case CurrentRunStageState.running:
      final runningParts = <String>[
        if (stage.latestActivity?.trim().isNotEmpty == true)
          stage.latestActivity!.trim(),
        if (metadataText.isNotEmpty) metadataText,
      ];
      return RunStagePresentation(
        statusLabel: 'Running',
        subtitle: runningParts.isNotEmpty
            ? runningParts.join(' • ')
            : 'Work in progress.',
        icon: Icons.sync_rounded,
        color: const Color(0xFF55D6BE),
      );
    case CurrentRunStageState.completed:
      return RunStagePresentation(
        statusLabel: 'Completed',
        subtitle:
            metadataText.isNotEmpty ? metadataText : 'Finished successfully.',
        icon: Icons.verified_rounded,
        color: const Color(0xFF55D6BE),
      );
    case CurrentRunStageState.failed:
      final failedParts = <String>[
        if (stage.latestActivity?.trim().isNotEmpty == true)
          stage.latestActivity!.trim(),
        if (metadataText.isNotEmpty) metadataText,
      ];
      return RunStagePresentation(
        statusLabel: 'Failed',
        subtitle: failedParts.isNotEmpty
            ? failedParts.join(' • ')
            : 'The stage failed before completion.',
        icon: Icons.error_outline_rounded,
        color: const Color(0xFFFFB3B3),
      );
    case CurrentRunStageState.cancelled:
      return RunStagePresentation(
        statusLabel: 'Cancelled',
        subtitle:
            metadataText.isNotEmpty ? metadataText : 'The stage was cancelled.',
        icon: Icons.cancel_outlined,
        color: const Color(0xFFFFD08A),
      );
    case CurrentRunStageState.stale:
      return RunStagePresentation(
        statusLabel: 'Needs recovery',
        subtitle: metadataText.isNotEmpty
            ? metadataText
            : 'The submission outcome is uncertain.',
        icon: Icons.help_outline_rounded,
        color: const Color(0xFFFFB3B3),
      );
    case CurrentRunStageState.skipped:
      return RunStagePresentation(
        statusLabel: 'Skipped',
        subtitle: metadataText.isNotEmpty
            ? metadataText
            : 'This stage did not run for the active pipeline.',
        icon: Icons.skip_next_rounded,
        color: const Color(0xFFFFC857),
      );
  }
}

String _shortId(String value) {
  final trimmed = value.trim();
  if (trimmed.length <= 8) {
    return trimmed;
  }
  return trimmed.substring(0, 8);
}
