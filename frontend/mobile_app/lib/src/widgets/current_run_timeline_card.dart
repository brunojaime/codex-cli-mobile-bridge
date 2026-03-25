import 'package:flutter/material.dart';

import '../models/agent_configuration.dart';
import '../models/current_run_execution.dart';
import '../models/session_detail.dart';
import '../presentation/agent_execution_presentation.dart';

class CurrentRunTimelineCard extends StatelessWidget {
  const CurrentRunTimelineCard({
    super.key,
    required this.session,
  });

  final SessionDetail session;

  @override
  Widget build(BuildContext context) {
    final runs = _runsForDisplay(session);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Run history',
            style: TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _headerText(session, runs),
            style: const TextStyle(
              color: Color(0xFF8B97B5),
              fontSize: 12,
              height: 1.3,
            ),
          ),
          if (runs.isNotEmpty) ...<Widget>[
            const SizedBox(height: 12),
            for (final run in runs) ...<Widget>[
              _RunHistoryEntry(
                session: session,
                run: run,
              ),
              if (run != runs.last) const SizedBox(height: 12),
            ],
          ],
        ],
      ),
    );
  }
}

class _RunHistoryEntry extends StatelessWidget {
  const _RunHistoryEntry({
    required this.session,
    required this.run,
  });

  final SessionDetail session;
  final CurrentRunExecution run;

  @override
  Widget build(BuildContext context) {
    final runPresentation = _runPresentation(run.state);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0F1730),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color:
              run.isActive ? const Color(0xFF2F5C7E) : const Color(0xFF22304E),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          LayoutBuilder(
            builder: (context, constraints) {
              final useStackedHeader = constraints.maxWidth < 300;
              final titleBlock = Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    run.isActive
                        ? 'Active run ${_shortId(run.runId)}'
                        : 'Run ${_shortId(run.runId)}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _runTimestampLine(run),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFF8B97B5),
                      fontSize: 12,
                    ),
                  ),
                ],
              );

              if (useStackedHeader) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    titleBlock,
                    const SizedBox(height: 8),
                    _StateChip(
                      label: runPresentation.statusLabel,
                      color: runPresentation.color,
                    ),
                  ],
                );
              }

              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(child: titleBlock),
                  const SizedBox(width: 8),
                  _StateChip(
                    label: runPresentation.statusLabel,
                    color: runPresentation.color,
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 10),
          for (final stage in run.stages) ...<Widget>[
            _CurrentRunStageRow(
              label: resolveAgentLabel(session, _agentIdForStage(stage.stage)),
              stage: stage,
            ),
            if (stage != run.stages.last) const SizedBox(height: 8),
          ],
        ],
      ),
    );
  }
}

class _CurrentRunStageRow extends StatelessWidget {
  const _CurrentRunStageRow({
    required this.label,
    required this.stage,
  });

  final String label;
  final CurrentRunStageExecution stage;

  @override
  Widget build(BuildContext context) {
    final presentation = buildRunStagePresentation(stage);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            presentation.icon,
            color: presentation.color,
            size: 18,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                LayoutBuilder(
                  builder: (context, constraints) {
                    final useStackedHeader = constraints.maxWidth < 250;
                    final title = Text(
                      '$label ${_progressText(stage)}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    );

                    if (useStackedHeader) {
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          title,
                          const SizedBox(height: 8),
                          _StateChip(
                            label: presentation.statusLabel,
                            color: presentation.color,
                          ),
                        ],
                      );
                    }

                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Expanded(child: title),
                        const SizedBox(width: 8),
                        _StateChip(
                          label: presentation.statusLabel,
                          color: presentation.color,
                        ),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 4),
                Text(
                  presentation.subtitle,
                  style: const TextStyle(
                    color: Color(0xFFB8C8EA),
                    fontSize: 12,
                    height: 1.3,
                  ),
                ),
                if (_stageTimestampLine(stage) case final timestampText?)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      timestampText,
                      style: const TextStyle(
                        color: Color(0xFF8B97B5),
                        fontSize: 11,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StateChip extends StatelessWidget {
  const _StateChip({
    required this.label,
    required this.color,
  });

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

List<CurrentRunExecution> _runsForDisplay(SessionDetail session) {
  final currentRun = session.currentRun;
  if (currentRun == null) {
    return session.recentRuns;
  }

  final runs = <CurrentRunExecution>[currentRun];
  for (final run in session.recentRuns) {
    if (run.runId == currentRun.runId) {
      continue;
    }
    runs.add(run);
  }
  return runs;
}

String _headerText(SessionDetail session, List<CurrentRunExecution> runs) {
  if (runs.isEmpty) {
    return 'No active or recent runs yet. Start an agent request to populate this panel.';
  }
  if (session.activeAgentRunId != null) {
    return 'The active pipeline updates live here, and completed runs remain below it.';
  }
  return 'Recent completed runs stay visible here after the active pipeline closes.';
}

String _progressText(CurrentRunStageExecution stage) {
  return '${stage.attemptCount}/${stage.maxTurns}';
}

String? _stageTimestampLine(CurrentRunStageExecution stage) {
  final completedAt = stage.completedAt?.toLocal();
  if (completedAt != null) {
    return 'Finished ${_formatTimestamp(completedAt)}';
  }
  final updatedAt = stage.updatedAt?.toLocal();
  if (updatedAt != null) {
    return 'Updated ${_formatTimestamp(updatedAt)}';
  }
  final startedAt = stage.startedAt?.toLocal();
  if (startedAt != null) {
    return 'Started ${_formatTimestamp(startedAt)}';
  }
  return null;
}

String _runTimestampLine(CurrentRunExecution run) {
  final completedAt = run.completedAt?.toLocal();
  if (completedAt != null && !run.isActive) {
    return 'Finished ${_formatTimestamp(completedAt)}';
  }
  final updatedAt = run.updatedAt?.toLocal();
  if (updatedAt != null) {
    return 'Updated ${_formatTimestamp(updatedAt)}';
  }
  final startedAt = run.startedAt?.toLocal();
  if (startedAt != null) {
    return 'Started ${_formatTimestamp(startedAt)}';
  }
  return run.isActive
      ? 'Waiting for the first stage to start.'
      : 'Timestamp unavailable.';
}

RunStagePresentation _runPresentation(CurrentRunStageState state) {
  return buildRunStagePresentation(
    CurrentRunStageExecution(
      stage: CurrentRunStageId.generator,
      state: state,
      configured: true,
    ),
  );
}

String _formatTimestamp(DateTime timestamp) {
  final month = timestamp.month.toString().padLeft(2, '0');
  final day = timestamp.day.toString().padLeft(2, '0');
  final hour = timestamp.hour.toString().padLeft(2, '0');
  final minute = timestamp.minute.toString().padLeft(2, '0');
  return '$month/$day $hour:$minute';
}

AgentId _agentIdForStage(CurrentRunStageId stage) {
  switch (stage) {
    case CurrentRunStageId.generator:
      return AgentId.generator;
    case CurrentRunStageId.reviewer:
      return AgentId.reviewer;
    case CurrentRunStageId.summary:
      return AgentId.summary;
    case CurrentRunStageId.supervisor:
      return AgentId.supervisor;
    case CurrentRunStageId.qa:
      return AgentId.qa;
    case CurrentRunStageId.ux:
      return AgentId.ux;
    case CurrentRunStageId.seniorEngineer:
      return AgentId.seniorEngineer;
  }
}

String _shortId(String value) {
  final trimmed = value.trim();
  if (trimmed.length <= 8) {
    return trimmed;
  }
  return trimmed.substring(0, 8);
}
