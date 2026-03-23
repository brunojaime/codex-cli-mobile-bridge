import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class RichMessageContent extends StatelessWidget {
  const RichMessageContent({
    super.key,
    required this.text,
    required this.textColor,
    this.onOptionSelected,
    this.onLinkTap,
  });

  final String text;
  final Color textColor;
  final ValueChanged<String>? onOptionSelected;
  final Future<void> Function(String target)? onLinkTap;

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
            onLinkTap: onLinkTap,
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
      _SectionBlock() => _SectionCard(
          title: block.title,
          textColor: textColor,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var index = 0; index < block.blocks.length; index++) ...[
                _buildBlock(context, block.blocks[index]),
                if (index != block.blocks.length - 1)
                  const SizedBox(height: 10),
              ],
            ],
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
                          _inlineSpans(
                            item,
                            textColor: textColor,
                            onLinkTap: onLinkTap,
                          ),
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
      _ValidationBlock() => _ValidationCard(
          title: block.title,
          items: block.items,
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
    final title =
        (language?.trim().isNotEmpty ?? false) ? language!.trim() : 'code';
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
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

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.child,
    required this.textColor,
  });

  final String title;
  final Widget child;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0x141C273D),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2A3654)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: textColor,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}

class _ValidationCard extends StatelessWidget {
  const _ValidationCard({
    required this.title,
    required this.items,
  });

  final String title;
  final List<_ValidationItem> items;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF111A2E),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2C3B60)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.verified_outlined, color: Color(0xFF7CF2D4), size: 16),
              SizedBox(width: 8),
              Text(
                'Validation',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          if (title.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              title,
              style: const TextStyle(
                color: Color(0xFF9EB3D8),
                fontSize: 12,
              ),
            ),
          ],
          const SizedBox(height: 10),
          for (final item in items) ...[
            _ValidationRow(item: item),
            if (item != items.last) const SizedBox(height: 8),
          ],
        ],
      ),
    );
  }
}

class _ValidationRow extends StatelessWidget {
  const _ValidationRow({required this.item});

  final _ValidationItem item;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: const Color(0xFF18233C),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              item.label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                height: 1.35,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: item.statusColor.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              item.result,
              style: TextStyle(
                color: item.statusColor,
                fontSize: 11,
                fontWeight: FontWeight.w700,
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

class _SectionBlock extends _MessageBlock {
  _SectionBlock({
    required this.title,
    required this.blocks,
  });

  final String title;
  final List<_MessageBlock> blocks;
}

class _BulletListBlock extends _MessageBlock {
  _BulletListBlock(this.items);
  final List<String> items;
}

class _ValidationBlock extends _MessageBlock {
  _ValidationBlock({
    required this.title,
    required this.items,
  });

  final String title;
  final List<_ValidationItem> items;
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

class _ValidationItem {
  _ValidationItem({
    required this.label,
    required this.result,
    required this.statusColor,
  });

  final String label;
  final String result;
  final Color statusColor;
}

class _FileReference {
  _FileReference({
    required this.label,
    required this.path,
  });

  final String label;
  final String path;
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
      while (
          index < lines.length && !lines[index].trimLeft().startsWith('```')) {
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

    final headingMatch =
        RegExp(r'^#{1,3}\s+(.+)$').firstMatch(lines.first.trim());
    if (lines.length == 1 && headingMatch != null) {
      blocks.add(_HeadingBlock(headingMatch.group(1)!.trim()));
      continue;
    }

    final sectionMatch =
        RegExp(r'^([A-Z][A-Za-z0-9 /-]{2,}):$').firstMatch(lines.first.trim());
    if (sectionMatch != null && lines.length > 1) {
      final body = lines.sublist(1).join('\n');
      final sectionBlocks = _parseTextChunk(body);
      final validationBlock =
          _maybeValidationBlock(lines.first.trim(), lines.sublist(1));
      if (validationBlock != null) {
        blocks.add(validationBlock);
      } else {
        blocks.add(
          _SectionBlock(
            title: sectionMatch.group(1)!.trim(),
            blocks: sectionBlocks,
          ),
        );
      }
      continue;
    }

    final validationBlock = _maybeValidationBlock('', lines);
    if (validationBlock != null) {
      blocks.add(validationBlock);
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

_ValidationBlock? _maybeValidationBlock(String titleLine, List<String> lines) {
  if (lines.isEmpty) {
    return null;
  }

  final items = <_ValidationItem>[];
  for (final line in lines) {
    final cleaned = line.trim().replaceFirst(RegExp(r'^[-*]\s+'), '');
    final arrowIndex = cleaned.indexOf('->');
    if (arrowIndex < 0) {
      return null;
    }
    final left = cleaned.substring(0, arrowIndex).trim();
    final right = cleaned.substring(arrowIndex + 2).trim();
    if (left.isEmpty || right.isEmpty) {
      return null;
    }
    items.add(
      _ValidationItem(
        label: left,
        result: right,
        statusColor: _statusColorForResult(right),
      ),
    );
  }

  if (items.isEmpty) {
    return null;
  }

  final normalizedTitle = titleLine.endsWith(':')
      ? titleLine.substring(0, titleLine.length - 1).trim()
      : titleLine.trim();

  return _ValidationBlock(
    title: normalizedTitle == 'Validation' ? '' : normalizedTitle,
    items: items,
  );
}

Color _statusColorForResult(String value) {
  final normalized = value.toLowerCase();
  if (normalized.contains('pass') ||
      normalized.contains('ok') ||
      normalized.contains('success')) {
    return const Color(0xFF7CF2D4);
  }
  if (normalized.contains('fail') || normalized.contains('error')) {
    return const Color(0xFFFFA8A8);
  }
  return const Color(0xFFB9D8FF);
}

TextSpan _inlineSpans(
  String text, {
  required Color textColor,
  Future<void> Function(String target)? onLinkTap,
}) {
  final tokens = <_InlineToken>[];
  final pattern = RegExp(r'`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)');
  var cursor = 0;
  for (final match in pattern.allMatches(text)) {
    if (match.start > cursor) {
      tokens.add(_InlineText(text.substring(cursor, match.start)));
    }

    if (match.group(1) != null) {
      tokens.add(_InlineCode(match.group(1)!));
    } else if (match.group(2) != null && match.group(3) != null) {
      tokens.add(
        _InlineFileReference(
          _FileReference(
            label: match.group(2)!.trim(),
            path: match.group(3)!.trim(),
          ),
        ),
      );
    }
    cursor = match.end;
  }

  if (cursor < text.length) {
    tokens.add(_InlineText(text.substring(cursor)));
  }

  if (tokens.isEmpty) {
    return TextSpan(text: text, style: TextStyle(color: textColor));
  }

  return TextSpan(
    style: TextStyle(color: textColor),
    children: [
      for (final token in tokens)
        switch (token) {
          _InlineText() => TextSpan(text: token.text),
          _InlineCode() => WidgetSpan(
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
                  token.code,
                  style: const TextStyle(
                    color: Color(0xFFE7EEF9),
                    fontFamily: 'monospace',
                    fontSize: 12.5,
                  ),
                ),
              ),
            ),
          _InlineFileReference() => WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
                child: InkWell(
                  borderRadius: BorderRadius.circular(999),
                  onTap: () async {
                    if (onLinkTap != null) {
                      await onLinkTap(token.reference.path);
                      return;
                    }
                    await Clipboard.setData(
                      ClipboardData(text: token.reference.path),
                    );
                  },
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFF203150),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: const Color(0xFF35517A)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.description_outlined,
                          size: 13,
                          color: Color(0xFFB9D8FF),
                        ),
                        const SizedBox(width: 5),
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 170),
                          child: Text(
                            token.reference.label,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Color(0xFFE7EEF9),
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        },
    ],
  );
}

sealed class _InlineToken {}

class _InlineText extends _InlineToken {
  _InlineText(this.text);
  final String text;
}

class _InlineCode extends _InlineToken {
  _InlineCode(this.code);
  final String code;
}

class _InlineFileReference extends _InlineToken {
  _InlineFileReference(this.reference);
  final _FileReference reference;
}
