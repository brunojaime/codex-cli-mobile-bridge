import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class RichMessageContent extends StatelessWidget {
  const RichMessageContent({
    super.key,
    required this.text,
    required this.textColor,
    this.onOptionSelected,
  });

  final String text;
  final Color textColor;
  final ValueChanged<String>? onOptionSelected;

  @override
  Widget build(BuildContext context) {
    final blocks = _parseBlocks(text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var index = 0; index < blocks.length; index++) ...[
          _buildBlock(context, blocks[index]),
          if (index != blocks.length - 1) const SizedBox(height: 12),
        ],
      ],
    );
  }

  Widget _buildBlock(BuildContext context, _MessageBlock block) {
    return switch (block) {
      _ParagraphBlock() => SelectableText.rich(
          _inlineSpans(
            block.text,
            textColor: textColor,
          ),
          style: TextStyle(
            color: textColor,
            height: 1.5,
            fontSize: 15,
          ),
        ),
      _HeadingBlock() => Text(
          block.text,
          style: TextStyle(
            color: textColor,
            height: 1.3,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
      _BulletListBlock() => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: block.items
              .map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: textColor.withValues(alpha: 0.8),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: SelectableText.rich(
                          _inlineSpans(item, textColor: textColor),
                          style: TextStyle(
                            color: textColor,
                            height: 1.5,
                            fontSize: 15,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              )
              .toList(),
        ),
      _OptionListBlock() => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Quick options',
              style: TextStyle(
                color: textColor.withValues(alpha: 0.78),
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: block.options
                  .map(
                    (option) => ActionChip(
                      backgroundColor: const Color(0xFF223153),
                      side: const BorderSide(color: Color(0xFF314569)),
                      label: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 240),
                        child: Text(option.text),
                      ),
                      onPressed: onOptionSelected == null
                          ? null
                          : () => onOptionSelected!(option.text),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      _CodeBlock() => _CodeCard(code: block.code, language: block.language),
    };
  }
}

class _CodeCard extends StatelessWidget {
  const _CodeCard({
    required this.code,
    this.language,
  });

  final String code;
  final String? language;

  @override
  Widget build(BuildContext context) {
    final title = (language?.trim().isNotEmpty ?? false) ? language!.trim() : 'code';
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFF0E162A),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF273453)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 8, 8),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1B2742),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    title,
                    style: const TextStyle(
                      color: Color(0xFFB7C5E5),
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const Spacer(),
                IconButton(
                  tooltip: 'Copy code',
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: code));
                  },
                  icon: const Icon(Icons.copy_rounded, size: 18),
                ),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: SelectableText(
              code.trimRight(),
              style: const TextStyle(
                color: Color(0xFFE6EEF8),
                fontFamily: 'monospace',
                fontSize: 13,
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

sealed class _MessageBlock {}

class _ParagraphBlock extends _MessageBlock {
  _ParagraphBlock(this.text);
  final String text;
}

class _HeadingBlock extends _MessageBlock {
  _HeadingBlock(this.text);
  final String text;
}

class _BulletListBlock extends _MessageBlock {
  _BulletListBlock(this.items);
  final List<String> items;
}

class _OptionListBlock extends _MessageBlock {
  _OptionListBlock(this.options);
  final List<_MessageOption> options;
}

class _CodeBlock extends _MessageBlock {
  _CodeBlock({
    required this.code,
    this.language,
  });

  final String code;
  final String? language;
}

class _MessageOption {
  _MessageOption(this.text);
  final String text;
}

List<_MessageBlock> _parseBlocks(String rawText) {
  final text = rawText.replaceAll('\r\n', '\n');
  final blocks = <_MessageBlock>[];
  final lines = text.split('\n');
  final paragraphBuffer = <String>[];
  var index = 0;

  void flushParagraphs() {
    if (paragraphBuffer.isEmpty) {
      return;
    }
    blocks.addAll(_parseTextChunk(paragraphBuffer.join('\n')));
    paragraphBuffer.clear();
  }

  while (index < lines.length) {
    final line = lines[index];
    final trimmed = line.trimLeft();
    if (trimmed.startsWith('```')) {
      flushParagraphs();
      final language = trimmed.substring(3).trim();
      index += 1;
      final codeLines = <String>[];
      while (index < lines.length && !lines[index].trimLeft().startsWith('```')) {
        codeLines.add(lines[index]);
        index += 1;
      }
      blocks.add(
        _CodeBlock(
          code: codeLines.join('\n'),
          language: language.isEmpty ? null : language,
        ),
      );
      if (index < lines.length) {
        index += 1;
      }
      continue;
    }

    paragraphBuffer.add(line);
    index += 1;
  }

  flushParagraphs();

  return blocks.isEmpty ? <_MessageBlock>[_ParagraphBlock(text)] : blocks;
}

List<_MessageBlock> _parseTextChunk(String chunk) {
  final groups = chunk
      .split(RegExp(r'\n\s*\n'))
      .map((value) => value.trim())
      .where((value) => value.isNotEmpty);

  final blocks = <_MessageBlock>[];
  for (final group in groups) {
    final lines = group
        .split('\n')
        .map((line) => line.trimRight())
        .where((line) => line.trim().isNotEmpty)
        .toList();
    if (lines.isEmpty) {
      continue;
    }

    final headingMatch = RegExp(r'^#{1,3}\s+(.+)$').firstMatch(lines.first.trim());
    if (lines.length == 1 && headingMatch != null) {
      blocks.add(_HeadingBlock(headingMatch.group(1)!.trim()));
      continue;
    }

    final optionMatches = lines
        .map((line) => RegExp(r'^\d+[.)]\s+(.+)$').firstMatch(line.trim()))
        .toList();
    if (optionMatches.every((match) => match != null)) {
      blocks.add(
        _OptionListBlock(
          optionMatches
              .map((match) => _MessageOption(match!.group(1)!.trim()))
              .toList(),
        ),
      );
      continue;
    }

    final bulletMatches = lines
        .map((line) => RegExp(r'^[-*]\s+(.+)$').firstMatch(line.trim()))
        .toList();
    if (bulletMatches.every((match) => match != null)) {
      blocks.add(
        _BulletListBlock(
          bulletMatches.map((match) => match!.group(1)!.trim()).toList(),
        ),
      );
      continue;
    }

    blocks.add(_ParagraphBlock(lines.join('\n')));
  }

  return blocks;
}

TextSpan _inlineSpans(
  String text, {
  required Color textColor,
}) {
  final matches = RegExp(r'`([^`]+)`').allMatches(text).toList();
  if (matches.isEmpty) {
    return TextSpan(text: text, style: TextStyle(color: textColor));
  }

  final children = <InlineSpan>[];
  var cursor = 0;
  for (final match in matches) {
    if (match.start > cursor) {
      children.add(TextSpan(text: text.substring(cursor, match.start)));
    }
    children.add(
      WidgetSpan(
        alignment: PlaceholderAlignment.middle,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 1),
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: const Color(0x2218203A),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: const Color(0x33455C87)),
          ),
          child: Text(
            match.group(1)!,
            style: const TextStyle(
              color: Color(0xFFE7EEF9),
              fontFamily: 'monospace',
              fontSize: 12.5,
            ),
          ),
        ),
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    children.add(TextSpan(text: text.substring(cursor)));
  }

  return TextSpan(
    style: TextStyle(color: textColor),
    children: children,
  );
}
