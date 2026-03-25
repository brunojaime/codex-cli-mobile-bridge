import 'package:flutter/material.dart';

import '../models/agent_configuration.dart';
import '../models/session_detail.dart';
import '../presentation/agent_execution_presentation.dart';

class AgentStudioStatusPresentation {
  const AgentStudioStatusPresentation({
    required this.icon,
    required this.iconColor,
    required this.tooltip,
    this.badgeLabel,
    this.badgeBackgroundColor,
    this.badgeForegroundColor,
  });

  final IconData icon;
  final Color? iconColor;
  final String tooltip;
  final String? badgeLabel;
  final Color? badgeBackgroundColor;
  final Color? badgeForegroundColor;
}

AgentStudioStatusPresentation buildAgentStudioStatusPresentation(
  SessionDetail? session,
) {
  if (session == null) {
    return const AgentStudioStatusPresentation(
      icon: Icons.hub_outlined,
      iconColor: null,
      tooltip: 'Agents',
    );
  }

  final preset = session.agentConfiguration.preset;
  final modeLabel = switch (preset) {
    AgentPreset.solo => 'Solo generator',
    AgentPreset.review => 'Generator + Reviewer',
    AgentPreset.triad => 'Generator + Reviewer + Summary',
    AgentPreset.supervisor => 'Supervisor + Specialists',
  };
  final reviewerPresentation = buildReviewerLifecyclePresentation(session);

  return switch (preset) {
    AgentPreset.solo => AgentStudioStatusPresentation(
        icon: Icons.smart_toy_outlined,
        iconColor: const Color(0xFF8B97B5),
        tooltip: 'Agents: $modeLabel',
      ),
    AgentPreset.review => AgentStudioStatusPresentation(
        icon: Icons.rate_review_outlined,
        iconColor: reviewerPresentation.accentColor,
        tooltip: 'Agents: $modeLabel\n${reviewerPresentation.statusLine}',
        badgeLabel: 'R',
        badgeBackgroundColor: reviewerPresentation.accentColor,
        badgeForegroundColor: const Color(0xFF07131D),
      ),
    AgentPreset.triad => AgentStudioStatusPresentation(
        icon: Icons.hub_outlined,
        iconColor: reviewerPresentation.accentColor,
        tooltip: 'Agents: $modeLabel\n${reviewerPresentation.statusLine}',
        badgeLabel: '3',
        badgeBackgroundColor: reviewerPresentation.accentColor,
        badgeForegroundColor: const Color(0xFF07131D),
      ),
    AgentPreset.supervisor => const AgentStudioStatusPresentation(
        icon: Icons.account_tree_outlined,
        iconColor: Color(0xFF8FEAFF),
        tooltip: 'Agents: Supervisor + Specialists',
        badgeLabel: 'S',
        badgeBackgroundColor: Color(0xFF8FEAFF),
        badgeForegroundColor: Color(0xFF07131D),
      ),
  };
}

class AgentStudioStatusButton extends StatelessWidget {
  const AgentStudioStatusButton({
    super.key,
    required this.session,
    required this.onPressed,
  });

  final SessionDetail? session;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final presentation = buildAgentStudioStatusPresentation(session);
    return IconButton(
      onPressed: onPressed,
      tooltip: presentation.tooltip,
      icon: Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          Icon(
            presentation.icon,
            color: presentation.iconColor,
          ),
          if (presentation.badgeLabel != null &&
              presentation.badgeBackgroundColor != null &&
              presentation.badgeForegroundColor != null)
            Positioned(
              right: -10,
              top: -6,
              child: _AgentStatusBadge(
                label: presentation.badgeLabel!,
                backgroundColor: presentation.badgeBackgroundColor!,
                foregroundColor: presentation.badgeForegroundColor!,
              ),
            ),
        ],
      ),
    );
  }
}

class _AgentStatusBadge extends StatelessWidget {
  const _AgentStatusBadge({
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String label;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foregroundColor,
          fontSize: 10,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
