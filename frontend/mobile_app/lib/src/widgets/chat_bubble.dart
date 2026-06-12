import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/agent_configuration.dart';
import '../models/chat_message.dart';
import '../utils/chat_timestamp_formatter.dart';
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
    this.attachmentBaseUrl,
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
  final String? attachmentBaseUrl;

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final isReviewerCodex = message.isReviewerCodex;
    final isSummaryAgent = message.agentId == AgentId.summary;
    final isGeneratorAgent = message.agentId == AgentId.generator && !isUser;
    final displayContent = _displayContentForMessage(message);
    final screenWidth = MediaQuery.sizeOf(context).width;
    final useWideWebLayout = kIsWeb && screenWidth >= 900;
    final shouldPreferWideBubble =
        displayContent.text.length >= 120 || displayContent.text.contains('\n');
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
    final timestampLabel = formatChatMessageTime(context, message.createdAt);
    final activityPresentation = isUser ? null : _activityPresentation(message);
    final imageAttachments = message.imageAttachments;
    final canOpenImageAttachments =
        attachmentBaseUrl != null && imageAttachments.isNotEmpty;

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
              if (_summaryTurnRangeText(message) case final turnRangeText?) ...[
                Text(
                  turnRangeText,
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.76),
                    fontSize: 12,
                    height: 1.35,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 10),
              ],
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
              if (activityPresentation != null) ...[
                _ActivityStatusStrip(
                  presentation: activityPresentation,
                  textColor: textColor,
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
                if (displayContent.text.isNotEmpty)
                  RichMessageContent(
                    text: displayContent.text,
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
                if (displayContent.attachmentSummary != null) ...[
                  if (displayContent.text.isNotEmpty)
                    const SizedBox(height: 12),
                  _UserAttachmentSummaryCard(
                    summary: displayContent.attachmentSummary!,
                    textColor: textColor,
                    onTap: canOpenImageAttachments
                        ? () => _openImageAttachmentViewer(
                              context,
                              baseUrl: attachmentBaseUrl!,
                              attachments: imageAttachments,
                            )
                        : null,
                  ),
                ],
                if (displayContent.sentViaAudio) ...[
                  if (displayContent.text.isNotEmpty ||
                      displayContent.attachmentSummary != null)
                    const SizedBox(height: 8),
                  _SentViaAudioMarker(textColor: textColor),
                ],
                if ((displayContent.copyText.isNotEmpty ||
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
                      if (displayContent.copyText.isNotEmpty) ...[
                        _MessageAction(
                          icon: Icons.copy_rounded,
                          label: 'Copy',
                          onTap: () async {
                            await Clipboard.setData(
                              ClipboardData(text: displayContent.copyText),
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
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  timestampLabel,
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.62),
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
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

class _UserAttachmentSummaryCard extends StatelessWidget {
  const _UserAttachmentSummaryCard({
    required this.summary,
    required this.textColor,
    this.onTap,
  });

  final _AttachmentDisplaySummary summary;
  final Color textColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final card = Container(
      constraints: const BoxConstraints(maxWidth: 320),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: textColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: textColor.withValues(alpha: 0.16)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(
              color: textColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            alignment: Alignment.center,
            child: Icon(summary.icon, size: 18, color: textColor),
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  summary.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: textColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (summary.detail != null) ...[
                  const SizedBox(height: 1),
                  Text(
                    summary.detail!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: textColor.withValues(alpha: 0.72),
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (onTap != null) ...<Widget>[
            const SizedBox(width: 8),
            Icon(
              Icons.open_in_full_rounded,
              size: 16,
              color: textColor.withValues(alpha: 0.78),
            ),
          ],
        ],
      ),
    );
    if (onTap == null) {
      return card;
    }
    return Semantics(
      button: true,
      label: 'Open image attachment',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: card,
      ),
    );
  }
}

class _SentViaAudioMarker extends StatelessWidget {
  const _SentViaAudioMarker({required this.textColor});

  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: textColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: textColor.withValues(alpha: 0.16)),
      ),
      child: Text(
        'Sent via audio',
        style: TextStyle(
          color: textColor.withValues(alpha: 0.78),
          fontSize: 11,
          fontWeight: FontWeight.w700,
          height: 1.1,
        ),
      ),
    );
  }
}

void _openImageAttachmentViewer(
  BuildContext context, {
  required String baseUrl,
  required List<ChatMessageAttachment> attachments,
}) {
  final urls = attachments
      .map((attachment) =>
          _resolveAttachmentUrl(baseUrl, attachment.downloadUrl))
      .toList(growable: false);
  if (urls.isEmpty) {
    return;
  }
  showDialog<void>(
    context: context,
    builder: (context) => _ImageAttachmentViewer(urls: urls),
  );
}

Uri _resolveAttachmentUrl(String baseUrl, String downloadUrl) {
  final attachmentUri = Uri.parse(downloadUrl);
  if (attachmentUri.hasScheme) {
    return attachmentUri;
  }
  return Uri.parse(baseUrl.trim().replaceAll(RegExp(r'/$'), ''))
      .resolve(downloadUrl);
}

class _ImageAttachmentViewer extends StatefulWidget {
  const _ImageAttachmentViewer({
    required this.urls,
  });

  final List<Uri> urls;

  @override
  State<_ImageAttachmentViewer> createState() => _ImageAttachmentViewerState();
}

class _ImageAttachmentViewerState extends State<_ImageAttachmentViewer> {
  late final PageController _pageController;
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _showImage(int index) {
    if (index < 0 || index >= widget.urls.length) {
      return;
    }
    _pageController.animateToPage(
      index,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    final multiple = widget.urls.length > 1;
    return Dialog.fullscreen(
      backgroundColor: const Color(0xFF070B16),
      child: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Row(
                children: <Widget>[
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded),
                  ),
                  const Spacer(),
                  Text(
                    '${_currentIndex + 1} / ${widget.urls.length}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const Spacer(),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                itemCount: widget.urls.length,
                onPageChanged: (index) {
                  setState(() {
                    _currentIndex = index;
                  });
                },
                itemBuilder: (context, index) {
                  return InteractiveViewer(
                    minScale: 0.8,
                    maxScale: 4,
                    child: Center(
                      child: Image.network(
                        widget.urls[index].toString(),
                        fit: BoxFit.contain,
                        loadingBuilder: (context, child, loadingProgress) {
                          if (loadingProgress == null) {
                            return child;
                          }
                          return const CircularProgressIndicator();
                        },
                        errorBuilder: (context, error, stackTrace) {
                          return const Icon(
                            Icons.broken_image_outlined,
                            color: Color(0xFFB8C8EA),
                            size: 56,
                          );
                        },
                      ),
                    ),
                  );
                },
              ),
            ),
            if (multiple)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 18),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    IconButton.filledTonal(
                      tooltip: 'Previous image',
                      onPressed: _currentIndex == 0
                          ? null
                          : () => _showImage(_currentIndex - 1),
                      icon: const Icon(Icons.chevron_left_rounded),
                    ),
                    const SizedBox(width: 24),
                    IconButton.filledTonal(
                      tooltip: 'Next image',
                      onPressed: _currentIndex == widget.urls.length - 1
                          ? null
                          : () => _showImage(_currentIndex + 1),
                      icon: const Icon(Icons.chevron_right_rounded),
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

class _ActivityStatusPresentation {
  const _ActivityStatusPresentation({
    required this.label,
    required this.detail,
    required this.icon,
    required this.color,
  });

  final String label;
  final String detail;
  final IconData icon;
  final Color color;
}

class _ActivityStatusStrip extends StatelessWidget {
  const _ActivityStatusStrip({
    required this.presentation,
    required this.textColor,
  });

  final _ActivityStatusPresentation presentation;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0F1730).withValues(alpha: 0.64),
        borderRadius: BorderRadius.circular(10),
        border: Border(
          left: BorderSide(color: presentation.color, width: 3),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            presentation.icon,
            color: presentation.color,
            size: 17,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  presentation.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: presentation.color,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  presentation.detail,
                  style: TextStyle(
                    color: textColor.withValues(alpha: 0.82),
                    fontSize: 12,
                    height: 1.35,
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

_ActivityStatusPresentation? _activityPresentation(ChatMessage message) {
  final rawDetail = message.jobLatestActivity?.trim();
  if (rawDetail == null || rawDetail.isEmpty) {
    return null;
  }
  final detail = _cleanActivityDetail(rawDetail);
  final phase = (message.jobPhase ?? '').toLowerCase();
  final combined = '$phase ${rawDetail.toLowerCase()}';

  if (combined.contains('reason')) {
    return _ActivityStatusPresentation(
      label: 'Reasoning',
      detail: detail,
      icon: Icons.psychology_alt_outlined,
      color: const Color(0xFFFFC857),
    );
  }
  if (combined.contains('tool') || combined.contains('mcp')) {
    return _ActivityStatusPresentation(
      label: 'Tools',
      detail: detail,
      icon: Icons.extension_rounded,
      color: const Color(0xFF8FEAFF),
    );
  }
  if (combined.contains('draft') || combined.contains('compos')) {
    return _ActivityStatusPresentation(
      label: 'Drafting',
      detail: detail,
      icon: Icons.edit_note_rounded,
      color: const Color(0xFF55D6BE),
    );
  }
  if (combined.contains('final')) {
    return _ActivityStatusPresentation(
      label: 'Finalizing',
      detail: detail,
      icon: Icons.task_alt_rounded,
      color: const Color(0xFFB8C8EA),
    );
  }
  return _ActivityStatusPresentation(
    label: 'Activity',
    detail: detail,
    icon: Icons.sync_rounded,
    color: const Color(0xFF9FD3FF),
  );
}

String _cleanActivityDetail(String value) {
  final trimmed = value.trim();
  if (trimmed == 'call-mcp-tool') {
    return 'Calling MCP tool.';
  }
  if (trimmed == 'mcpToolCall') {
    return 'Running MCP tool.';
  }
  return trimmed
      .replaceAll('call-mcp-tool', 'MCP tool call')
      .replaceAll('mcpToolCall', 'MCP tool call');
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

class _DisplayMessageContent {
  const _DisplayMessageContent({
    required this.text,
    required this.copyText,
    this.attachmentSummary,
    this.sentViaAudio = false,
  });

  final String text;
  final String copyText;
  final _AttachmentDisplaySummary? attachmentSummary;
  final bool sentViaAudio;
}

class _AttachmentDisplaySummary {
  const _AttachmentDisplaySummary({
    required this.imageCount,
    required this.textCount,
    required this.audioCount,
    required this.fileCount,
  });

  final int imageCount;
  final int textCount;
  final int audioCount;
  final int fileCount;

  int get totalCount => imageCount + textCount + audioCount + fileCount;

  IconData get icon {
    if (totalCount == imageCount) {
      return Icons.image_rounded;
    }
    if (totalCount == audioCount) {
      return Icons.graphic_eq_rounded;
    }
    return Icons.attach_file_rounded;
  }

  String get title {
    if (totalCount == 1) {
      if (imageCount == 1) {
        return 'Image attached';
      }
      if (audioCount == 1) {
        return 'Audio attached';
      }
      if (textCount == 1) {
        return 'Document attached';
      }
      return 'File attached';
    }
    return '$totalCount attachments';
  }

  String? get detail {
    if (totalCount <= 1) {
      return null;
    }
    final parts = <String>[];
    if (imageCount > 0) {
      parts.add('$imageCount image${imageCount == 1 ? '' : 's'}');
    }
    if (textCount > 0) {
      parts.add('$textCount document${textCount == 1 ? '' : 's'}');
    }
    if (audioCount > 0) {
      parts.add('$audioCount audio file${audioCount == 1 ? '' : 's'}');
    }
    if (fileCount > 0) {
      parts.add('$fileCount file${fileCount == 1 ? '' : 's'}');
    }
    return parts.join(' · ');
  }
}

_DisplayMessageContent _displayContentForMessage(ChatMessage message) {
  if (!message.isUser) {
    return _DisplayMessageContent(
      text: message.text,
      copyText: message.text,
    );
  }

  final audioContent = _extractSentViaAudioMarker(message.text);
  if (audioContent != null) {
    return audioContent;
  }

  final legacyContent = _extractUserAttachmentMetadata(message.text);
  if (legacyContent.attachmentSummary != null) {
    return legacyContent;
  }
  final imageAttachmentCount = message.imageAttachments.length;
  if (imageAttachmentCount > 0) {
    return _DisplayMessageContent(
      text: message.text,
      copyText: message.text.isNotEmpty ? message.text : 'Image attached',
      attachmentSummary: _AttachmentDisplaySummary(
        imageCount: imageAttachmentCount,
        textCount: 0,
        audioCount: 0,
        fileCount: 0,
      ),
    );
  }
  return legacyContent;
}

_DisplayMessageContent? _extractSentViaAudioMarker(String text) {
  final normalizedText = text.replaceAll('\r\n', '\n');
  final lines = normalizedText.split('\n');
  final markerIndex =
      lines.indexWhere((line) => line.trim() == '[Sent via audio]');
  if (markerIndex == -1) {
    return null;
  }

  final before = lines.take(markerIndex).join('\n').trimRight();
  final after = lines.skip(markerIndex + 1).join('\n').trim();
  final visibleParts = <String>[
    if (before.isNotEmpty) before,
    if (after.isNotEmpty) after,
  ];
  final visibleText = visibleParts.join('\n\n');
  return _DisplayMessageContent(
    text: visibleText,
    copyText: visibleText,
    sentViaAudio: true,
  );
}

_DisplayMessageContent _extractUserAttachmentMetadata(String text) {
  final normalizedText = text.replaceAll('\r\n', '\n');
  final multiAttachmentContent = _extractAttachedFilesBlock(normalizedText) ??
      _extractSingleDocumentAttachmentBlock(normalizedText);
  if (multiAttachmentContent != null) {
    final visibleText = multiAttachmentContent.text.trimRight();
    final attachmentSummary = multiAttachmentContent.attachmentSummary!;
    final copyText =
        visibleText.isNotEmpty ? visibleText : attachmentSummary.title;
    return _DisplayMessageContent(
      text: visibleText,
      copyText: copyText,
      attachmentSummary: attachmentSummary,
    );
  }

  return _DisplayMessageContent(text: text, copyText: text);
}

_DisplayMessageContent? _extractAttachedFilesBlock(String text) {
  final lines = text.split('\n');
  final headerIndex =
      lines.lastIndexWhere((line) => line.trim() == '[Attached files]');
  if (headerIndex == -1) {
    return null;
  }

  final metadataLines = lines
      .skip(headerIndex + 1)
      .where((line) => line.trim().isNotEmpty)
      .toList(growable: false);
  if (metadataLines.isEmpty) {
    return null;
  }

  final kinds = <String>[];
  final metadataPattern = RegExp(r'^-\s*([A-Za-z0-9 _-]+):\s+.+$');
  for (final line in metadataLines) {
    final match = metadataPattern.firstMatch(line.trim());
    if (match == null) {
      return null;
    }
    kinds.add(match.group(1)!.trim());
  }

  return _DisplayMessageContent(
    text: lines.take(headerIndex).join('\n'),
    copyText: '',
    attachmentSummary: _attachmentSummaryFromKinds(kinds),
  );
}

_DisplayMessageContent? _extractSingleDocumentAttachmentBlock(String text) {
  final lines = text.split('\n');
  final lastContentIndex =
      lines.lastIndexWhere((line) => line.trim().isNotEmpty);
  if (lastContentIndex == -1) {
    return null;
  }

  final documentPattern =
      RegExp(r'^\[Attached\s+([A-Za-z0-9 _-]+)\s+document:\s+.+\]$');
  final match = documentPattern.firstMatch(lines[lastContentIndex].trim());
  if (match == null) {
    return null;
  }

  return _DisplayMessageContent(
    text: lines.take(lastContentIndex).join('\n'),
    copyText: '',
    attachmentSummary: _attachmentSummaryFromKinds([match.group(1)!.trim()]),
  );
}

_AttachmentDisplaySummary _attachmentSummaryFromKinds(List<String> kinds) {
  var imageCount = 0;
  var textCount = 0;
  var audioCount = 0;
  var fileCount = 0;

  for (final kind in kinds) {
    final normalizedKind = kind.toLowerCase();
    if (normalizedKind.contains('image')) {
      imageCount += 1;
    } else if (normalizedKind.contains('audio')) {
      audioCount += 1;
    } else if (normalizedKind.contains('text') ||
        normalizedKind.contains('document') ||
        normalizedKind.contains('doc') ||
        normalizedKind.contains('pdf')) {
      textCount += 1;
    } else {
      fileCount += 1;
    }
  }

  return _AttachmentDisplaySummary(
    imageCount: imageCount,
    textCount: textCount,
    audioCount: audioCount,
    fileCount: fileCount,
  );
}

String _collapsedPreviewText(ChatMessage message) {
  final displayContent = _displayContentForMessage(message);
  final trimmedText = displayContent.text.trim();
  if (trimmedText.isNotEmpty) {
    return trimmedText.replaceAll(RegExp(r'\s+'), ' ');
  }
  if (displayContent.attachmentSummary != null) {
    return displayContent.attachmentSummary!.title;
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

String? _summaryTurnRangeText(ChatMessage message) {
  if (message.agentId != AgentId.summary) {
    return null;
  }
  final start = message.summaryTurnStart;
  final end = message.summaryTurnEnd;
  if (start == null || end == null) {
    return null;
  }
  if (start == end) {
    return 'Covers turn $start';
  }
  return 'Covers turns $start to $end';
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
