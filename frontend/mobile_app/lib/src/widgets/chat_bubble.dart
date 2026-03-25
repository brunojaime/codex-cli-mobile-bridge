import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/agent_configuration.dart';
import '../models/chat_message.dart';
import 'rich_message_content.dart';

class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.message,
    this.isCollapsed = false,
    this.onToggleCollapsed,
    this.generatorColor,
    this.onOptionSelected,
    this.onLinkTap,
    this.onCancelJob,
    this.onRetryJob,
    this.onRecoverUnknownSubmission,
    this.onCancelUnknownSubmission,
  });

  final ChatMessage message;
  final bool isCollapsed;
  final VoidCallback? onToggleCollapsed;
  final Color? generatorColor;
  final ValueChanged<String>? onOptionSelected;
  final Future<void> Function(String target)? onLinkTap;
  final Future<void> Function()? onCancelJob;
  final Future<void> Function()? onRetryJob;
  final Future<void> Function()? onRecoverUnknownSubmission;
  final Future<void> Function()? onCancelUnknownSubmission;

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final isReviewerCodex = message.isReviewerCodex;
    final isSummaryAgent = message.agentId == AgentId.summary;
    final isGeneratorAgent = message.agentId == AgentId.generator && !isUser;
    final screenWidth = MediaQuery.sizeOf(context).width;
    final useWideWebLayout = kIsWeb && screenWidth >= 900;
    final shouldPreferWideBubble =
        message.text.length >= 120 || message.text.contains('\n');
    final maxBubbleWidth = switch ((screenWidth, isUser)) {
      (>= 1600, true) => 980.0,
      (>= 1600, false) => 1280.0,
      (>= 1280, true) => screenWidth * 0.62,
      (>= 1280, false) => screenWidth * 0.8,
      (>= 900, true) => screenWidth * 0.72,
      (>= 900, false) => screenWidth * 0.86,
      _ => screenWidth * 0.88,
    };
    final preferredBubbleWidth = useWideWebLayout && shouldPreferWideBubble
        ? (isUser ? screenWidth * 0.52 : screenWidth * 0.78)
        : null;
    final resolvedGeneratorBubbleColor = generatorColor == null
        ? const Color(0xFF1A2440)
        : Color.alphaBlend(
            generatorColor!.withValues(alpha: 0.24),
            const Color(0xFF1A2440),
          );
    final bubbleColor = switch ((isUser, isReviewerCodex)) {
      (true, true) => const Color(0xFFFFD79A),
      (true, false) => const Color(0xFF55D6BE),
      (false, _) when isSummaryAgent => const Color(0xFF24385C),
      (false, _) when isGeneratorAgent => resolvedGeneratorBubbleColor,
      _ => const Color(0xFF1A2440),
    };
    final textColor = isUser ? const Color(0xFF09111F) : Colors.white;
    final alignment =
        isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start;
    final collapsedPreview = _collapsedPreviewText(message);
    final radius = BorderRadius.only(
      topLeft: const Radius.circular(18),
      topRight: const Radius.circular(18),
      bottomLeft: Radius.circular(isUser ? 18 : 6),
      bottomRight: Radius.circular(isUser ? 6 : 18),
    );

    return Column(
      crossAxisAlignment: alignment,
      children: <Widget>[
        Container(
          width: preferredBubbleWidth?.clamp(320.0, isUser ? 980.0 : 1280.0),
          constraints: BoxConstraints(
            maxWidth: maxBubbleWidth.clamp(280.0, isUser ? 980.0 : 1280.0),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: bubbleColor,
            borderRadius: radius,
            border: isReviewerCodex
                ? Border.all(color: const Color(0xFFD98B1D), width: 1.2)
                : null,
            boxShadow: const <BoxShadow>[
              BoxShadow(
                color: Color(0x22000000),
                blurRadius: 16,
                offset: Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: alignment,
            children: <Widget>[
              if (onToggleCollapsed != null)
                Align(
                  alignment: Alignment.centerRight,
                  child: _BubbleCollapseToggle(
                    isCollapsed: isCollapsed,
                    textColor: textColor,
                    onTap: onToggleCollapsed!,
                  ),
                ),
              if (onToggleCollapsed != null) const SizedBox(height: 8),
              if (isReviewerCodex)
                _ReviewerHeader(
                  message: message,
                  textColor: textColor,
                ),
              if (!isUser)
                _AssistantHeader(message: message, textColor: textColor),
              if (isReviewerCodex || !isUser) const SizedBox(height: 10),
              if (_recoveryLineageText(message) case final lineageText?) ...[
                Text(
                  lineageText,
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.74),
                    fontSize: 12,
                    height: 1.35,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 10),
              ],
              if (message.jobLatestActivity != null &&
                  message.jobLatestActivity!.isNotEmpty) ...[
                Text(
                  message.jobLatestActivity!,
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.72),
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 10),
              ],
              if (isCollapsed)
                _CollapsedMessagePreview(
                  text: collapsedPreview,
                  textColor: textColor,
                  alignment: alignment,
                  textAlign: isUser ? TextAlign.right : TextAlign.left,
                )
              else ...<Widget>[
                if (message.text.isNotEmpty)
                  RichMessageContent(
                    text: message.text,
                    textColor: textColor,
                    onOptionSelected:
                        isUser || isReviewerCodex ? null : onOptionSelected,
                    onLinkTap: isUser || isReviewerCodex ? null : onLinkTap,
                  )
                else if (isReviewerCodex && message.isPendingLike)
                  Text(
                    'Reviewer Codex is drafting the next prompt...',
                    style: TextStyle(
                      color: textColor.withValues(alpha: 0.78),
                      fontSize: 14,
                    ),
                  )
                else if (!isUser && message.isPendingLike)
                  Text(
                    isSummaryAgent
                        ? 'Summary agent is preparing a user-facing update...'
                        : isGeneratorAgent
                            ? 'Waiting for generator output...'
                            : 'Waiting for Codex output...',
                    style: TextStyle(
                      color: textColor.withValues(alpha: 0.78),
                      fontSize: 14,
                    ),
                  ),
                if ((message.text.isNotEmpty ||
                        (!isUser &&
                            onCancelJob != null &&
                            _canCancel(message)) ||
                        (!isUser && onRetryJob != null && _canRetry(message)) ||
                        (onRecoverUnknownSubmission != null &&
                            _canRecoverUnknownSubmission(message)) ||
                        (onCancelUnknownSubmission != null &&
                            _canCancelUnknownSubmission(message))) &&
                    (!isUser ||
                        _canRecoverUnknownSubmission(message) ||
                        _canCancelUnknownSubmission(message))) ...[
                  const SizedBox(height: 12),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (message.text.isNotEmpty) ...[
                        _MessageAction(
                          icon: Icons.copy_rounded,
                          label: 'Copy',
                          onTap: () async {
                            await Clipboard.setData(
                              ClipboardData(text: message.text),
                            );
                          },
                        ),
                        if (message.providerSessionId != null &&
                            message.providerSessionId!.isNotEmpty) ...[
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              'Session ${_shortId(message.providerSessionId!)}',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: textColor.withValues(alpha: 0.64),
                                fontSize: 11,
                              ),
                            ),
                          ),
                        ],
                      ],
                      if (onCancelJob != null && _canCancel(message)) ...[
                        const SizedBox(width: 8),
                        _MessageAction(
                          icon: Icons.stop_circle_outlined,
                          label: 'Cancel',
                          onTap: () async {
                            await onCancelJob!();
                          },
                        ),
                      ],
                      if (onRetryJob != null && _canRetry(message)) ...[
                        const SizedBox(width: 8),
                        _MessageAction(
                          icon: Icons.refresh_rounded,
                          label: 'Retry',
                          onTap: () async {
                            await onRetryJob!();
                          },
                        ),
                      ],
                      if (onRecoverUnknownSubmission != null &&
                          _canRecoverUnknownSubmission(message)) ...[
                        const SizedBox(width: 8),
                        _MessageAction(
                          icon: Icons.replay_circle_filled_rounded,
                          label: 'Retry follow-up',
                          onTap: () async {
                            await onRecoverUnknownSubmission!();
                          },
                        ),
                      ],
                      if (onCancelUnknownSubmission != null &&
                          _canCancelUnknownSubmission(message)) ...[
                        const SizedBox(width: 8),
                        _MessageAction(
                          icon: Icons.cancel_outlined,
                          label: 'Dismiss',
                          onTap: () async {
                            await onCancelUnknownSubmission!();
                          },
                        ),
                      ],
                    ],
                  ),
                ],
              ],
            ],
          ),
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

class _BubbleCollapseToggle extends StatelessWidget {
  const _BubbleCollapseToggle({
    required this.isCollapsed,
    required this.textColor,
    required this.onTap,
  });

  final bool isCollapsed;
  final Color textColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              isCollapsed
                  ? Icons.unfold_more_rounded
                  : Icons.unfold_less_rounded,
              size: 15,
              color: textColor.withValues(alpha: 0.72),
            ),
            const SizedBox(width: 4),
            Text(
              isCollapsed ? 'Expand' : 'Collapse',
              style: TextStyle(
                color: textColor.withValues(alpha: 0.72),
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CollapsedMessagePreview extends StatelessWidget {
  const _CollapsedMessagePreview({
    required this.text,
    required this.textColor,
    required this.alignment,
    required this.textAlign,
  });

  final String text;
  final Color textColor;
  final CrossAxisAlignment alignment;
  final TextAlign textAlign;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: alignment,
      children: <Widget>[
        Text(
          'Message collapsed',
          textAlign: textAlign,
          style: TextStyle(
            color: textColor.withValues(alpha: 0.74),
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          text,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          textAlign: textAlign,
          style: TextStyle(
            color: textColor.withValues(alpha: 0.86),
            height: 1.4,
          ),
        ),
      ],
    );
  }
}

class _ReviewerHeader extends StatelessWidget {
  const _ReviewerHeader({
    required this.message,
    required this.textColor,
  });

  final ChatMessage message;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    final phase = message.jobPhase ??
        (message.isPendingLike ? 'Preparing next prompt' : 'Prompt ready');

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFFFFE7BE),
            borderRadius: BorderRadius.circular(999),
          ),
          child: const Text(
            'CODEX REVIEWER',
            style: TextStyle(
              color: Color(0xFF7A3D00),
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            phase,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: textColor.withValues(alpha: 0.84),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}

class _AssistantHeader extends StatelessWidget {
  const _AssistantHeader({
    required this.message,
    required this.textColor,
  });

  final ChatMessage message;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    final phase = message.jobPhase ?? _fallbackPhase(message);
    final elapsedLabel = _formatElapsed(message.jobElapsedSeconds);
    final agentLabel =
        message.agentLabel ?? _defaultAgentLabel(message.agentId);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFF223153),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            agentLabel.toUpperCase(),
            style: TextStyle(
              color: _agentHeaderColor(message.agentId),
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Flexible(
          fit: FlexFit.loose,
          child: Text(
            phase,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: textColor.withValues(alpha: 0.92),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        if (elapsedLabel != null) const SizedBox(width: 8),
        if (elapsedLabel != null)
          Text(
            elapsedLabel,
            style: TextStyle(
              color: textColor.withValues(alpha: 0.64),
              fontSize: 11,
            ),
          ),
      ],
    );
  }
}

Color _agentHeaderColor(AgentId agentId) {
  return switch (agentId) {
    AgentId.summary => const Color(0xFFAED3FF),
    AgentId.reviewer => const Color(0xFFD98B1D),
    AgentId.supervisor => const Color(0xFF8FEAFF),
    AgentId.qa => const Color(0xFFFFB870),
    AgentId.ux => const Color(0xFFA8F0C8),
    AgentId.seniorEngineer => const Color(0xFFC7B5FF),
    AgentId.scraper => const Color(0xFF7FD5C7),
    _ => const Color(0xFF7CF2D4),
  };
}

String _defaultAgentLabel(AgentId agentId) {
  return switch (agentId) {
    AgentId.generator => 'Generator',
    AgentId.reviewer => 'Reviewer',
    AgentId.summary => 'Summary',
    AgentId.supervisor => 'Supervisor',
    AgentId.qa => 'QA',
    AgentId.ux => 'UX',
    AgentId.seniorEngineer => 'Senior Engineer',
    AgentId.scraper => 'Scraper',
    AgentId.user => 'User',
  };
}

class _MessageAction extends StatelessWidget {
  const _MessageAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 15, color: const Color(0xFF9FB3D6)),
            const SizedBox(width: 4),
            Text(
              label,
              style: const TextStyle(
                color: Color(0xFF9FB3D6),
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _fallbackPhase(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  if (message.status == ChatMessageStatus.cancelled ||
      jobStatus == 'cancelled') {
    return 'Cancelled';
  }
  if (jobStatus == 'running') {
    return 'Codex is working';
  }
  if (message.status == ChatMessageStatus.submissionUnknown) {
    return 'Submission state unknown';
  }
  if (message.status == ChatMessageStatus.failed || jobStatus == 'failed') {
    return 'Execution failed';
  }
  if (message.isPendingLike || jobStatus == 'pending') {
    return 'Queued';
  }
  return 'Completed';
}

String? _formatElapsed(int? seconds) {
  if (seconds == null) {
    return null;
  }
  if (seconds < 60) {
    return '${seconds}s';
  }
  final minutes = seconds ~/ 60;
  final remaining = seconds % 60;
  return '${minutes}m ${remaining}s';
}

String _shortId(String value) {
  if (value.length <= 8) {
    return value;
  }
  return value.substring(0, 8);
}

bool _canCancel(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  return message.jobId != null &&
      (message.isPendingLike ||
          jobStatus == 'pending' ||
          jobStatus == 'running');
}

bool _canRetry(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  return message.jobId != null &&
      (message.status == ChatMessageStatus.failed ||
          message.status == ChatMessageStatus.submissionUnknown ||
          message.status == ChatMessageStatus.cancelled ||
          jobStatus == 'failed' ||
          jobStatus == 'cancelled');
}

bool _canRecoverUnknownSubmission(ChatMessage message) {
  return message.status == ChatMessageStatus.submissionUnknown &&
      message.supersededByMessageId == null &&
      message.recoveryAction == null;
}

bool _canCancelUnknownSubmission(ChatMessage message) {
  return _canRecoverUnknownSubmission(message);
}

String _collapsedPreviewText(ChatMessage message) {
  final trimmedText = message.text.trim();
  if (trimmedText.isNotEmpty) {
    return trimmedText.replaceAll(RegExp(r'\s+'), ' ');
  }
  final latestActivity = message.jobLatestActivity?.trim();
  if (latestActivity != null && latestActivity.isNotEmpty) {
    return latestActivity;
  }
  if (message.isReviewerCodex && message.isPendingLike) {
    return 'Reviewer Codex is drafting the next prompt...';
  }
  if (message.isPendingLike) {
    return _fallbackPhase(message);
  }
  return 'Tap expand to show the full message.';
}

String? _recoveryLineageText(ChatMessage message) {
  final parts = <String>[];
  final diagnosticText = _diagnosticReasonText(message.reasonCode);
  if (diagnosticText != null) {
    parts.add(diagnosticText);
  }
  if (message.status == ChatMessageStatus.submissionUnknown) {
    parts.add(
        'Submission state is unknown. Retry starts a fresh follow-up attempt.');
  }
  if (message.recoveryAction == MessageRecoveryAction.cancel &&
      message.reasonCode != ChatMessageReasonCode.manualCancelRequested) {
    parts.add('This uncertain follow-up was manually dismissed.');
  }
  if (message.recoveryAction == MessageRecoveryAction.retry &&
      message.supersededByMessageId != null) {
    parts.add('This uncertain follow-up was superseded by a manual retry.');
  }
  if (message.recoveryAction == MessageRecoveryAction.retry &&
      message.recoveredFromMessageId != null) {
    parts.add('Manual retry of an earlier uncertain follow-up.');
  }
  if (parts.isEmpty) {
    return null;
  }
  return parts.join(' ');
}

String? _diagnosticReasonText(ChatMessageReasonCode? reasonCode) {
  switch (reasonCode) {
    case ChatMessageReasonCode.supersededByNewerRun:
      return 'Superseded by a newer run before this follow-up could be resumed.';
    case ChatMessageReasonCode.orphanedFollowUpCancelled:
      return 'This placeholder was cancelled because its run was no longer active.';
    case ChatMessageReasonCode.submissionOutcomeUnknown:
      return 'The backend lost the durable job record after submission was attempted.';
    case ChatMessageReasonCode.manualRetryRequested:
      return 'A manual retry was requested for this follow-up.';
    case ChatMessageReasonCode.manualCancelRequested:
      return 'This uncertain follow-up was manually dismissed.';
    case ChatMessageReasonCode.followUpTerminalCompletedRun:
      return 'This follow-up ended the active run.';
    case null:
      return null;
  }
}
