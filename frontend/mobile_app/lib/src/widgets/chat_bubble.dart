import 'package:flutter/material.dart';

import '../models/chat_message.dart';

class ChatBubble extends StatelessWidget {
  const ChatBubble({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final bubbleColor = isUser ? const Color(0xFF55D6BE) : const Color(0xFF1A2440);
    final textColor = isUser ? const Color(0xFF09111F) : Colors.white;
    final alignment = isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start;
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
          constraints: const BoxConstraints(maxWidth: 320),
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
              if (!isUser &&
                  (message.status == ChatMessageStatus.pending ||
                      message.status == ChatMessageStatus.sending)) ...<Widget>[
                const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    SizedBox(
                      height: 14,
                      width: 14,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    SizedBox(width: 10),
                    Text('Processing...'),
                  ],
                ),
                if (message.text.isNotEmpty) const SizedBox(height: 10),
              ],
              if (message.text.isNotEmpty)
                SelectableText(
                  message.text,
                  style: TextStyle(
                    color: textColor,
                    height: 1.45,
                    fontSize: 15,
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
