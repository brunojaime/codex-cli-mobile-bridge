import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat_message.dart';
import 'rich_message_content.dart';

class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.message,
    this.onOptionSelected,
    this.onLinkTap,
  });

  final ChatMessage message;
  final ValueChanged<String>? onOptionSelected;
  final Future<void> Function(String target)? onLinkTap;

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
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
    final bubbleColor =
        isUser ? const Color(0xFF55D6BE) : const Color(0xFF1A2440);
    final textColor = isUser ? const Color(0xFF09111F) : Colors.white;
    final alignment =
        isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start;
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
              if (!isUser)
                _AssistantHeader(message: message, textColor: textColor),
              if (!isUser) const SizedBox(height: 10),
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
              if (message.text.isNotEmpty)
                RichMessageContent(
                  text: message.text,
                  textColor: textColor,
                  onOptionSelected: isUser ? null : onOptionSelected,
                  onLinkTap: isUser ? null : onLinkTap,
                )
              else if (!isUser && message.isPendingLike)
                Text(
                  'Waiting for Codex output...',
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.78),
                    fontSize: 14,
                  ),
                ),
              if (!isUser && message.text.isNotEmpty) ...[
                const SizedBox(height: 12),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _MessageAction(
                      icon: Icons.copy_rounded,
                      label: 'Copy',
                      onTap: () async {
                        await Clipboard.setData(
                            ClipboardData(text: message.text));
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
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 8),
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
            _statusLabel(message),
            style: TextStyle(
              color: _statusColor(message),
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

String _statusLabel(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  if (jobStatus == 'running') {
    return 'RUNNING';
  }
  if (message.status == ChatMessageStatus.failed || jobStatus == 'failed') {
    return 'FAILED';
  }
  if (message.isPendingLike || jobStatus == 'pending') {
    return 'PENDING';
  }
  return 'READY';
}

Color _statusColor(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  if (message.status == ChatMessageStatus.failed || jobStatus == 'failed') {
    return const Color(0xFFFFA8A8);
  }
  if (message.isPendingLike ||
      jobStatus == 'pending' ||
      jobStatus == 'running') {
    return const Color(0xFFB9D8FF);
  }
  return const Color(0xFF7CF2D4);
}

String _fallbackPhase(ChatMessage message) {
  final jobStatus = message.jobStatus ?? '';
  if (jobStatus == 'running') {
    return 'Codex is working';
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
