import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:markdown/markdown.dart' as md;
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
      _ParagraphBlock() => _SelectableInlineText(
          text: block.text,
          textColor: textColor,
          onLinkTap: onLinkTap,
          style: TextStyle(
            color: textColor,
            height: 1.5,
            fontSize: 15,
          ),
        ),
      _HeadingBlock() => _SelectableInlineText(
          text: block.text,
          textColor: textColor,
          onLinkTap: onLinkTap,
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
                        child: _SelectableInlineText(
                          text: item,
                          textColor: textColor,
                          onLinkTap: onLinkTap,
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
            for (final option in block.options)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      alignment: Alignment.centerLeft,
                      foregroundColor: textColor,
                      backgroundColor: const Color(0xFF223153),
                      side: const BorderSide(color: Color(0xFF314569)),
                      minimumSize: const Size(48, 48),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    onPressed: onOptionSelected == null
                        ? null
                        : () =>
                            onOptionSelected!(_plainInlineText(option.text)),
                    child: Text(
                      _plainInlineText(option.text),
                      softWrap: true,
                      style: const TextStyle(fontSize: 15, height: 1.4),
                    ),
                  ),
                ),
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
  var optionsSection = false;
  for (final group in groups) {
    final lines = group
        .split('\n')
        .map((line) => line.trimRight())
        .where((line) => line.trim().isNotEmpty)
        .toList();
    if (lines.isEmpty) {
      continue;
    }

    // Only explicitly labelled choices become composer actions. Ordinary
    // numbered instructions (especially links) must stay selectable content.
    if (_isOptionsHeading(lines.first)) {
      optionsSection = true;
      lines.removeAt(0);
      if (lines.isEmpty) continue;
    }

    final headingMatch =
        RegExp(r'^#{1,3}\s+(.+)$').firstMatch(lines.first.trim());
    if (lines.length == 1 && headingMatch != null) {
      optionsSection = false;
      blocks.add(_HeadingBlock(headingMatch.group(1)!.trim()));
      continue;
    }

    final sectionMatch =
        RegExp(r'^([A-Z][A-Za-z0-9 /-]{2,}):$').firstMatch(lines.first.trim());
    if (sectionMatch != null && lines.length > 1) {
      optionsSection = false;
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

    final optionItems = <String>[];
    var isList = true;
    for (final line in lines) {
      final match = RegExp(r'^\d+[.)]\s+(.+)$').firstMatch(line.trim());
      if (match != null) {
        optionItems.add(match.group(1)!.trim());
      } else if (optionItems.isNotEmpty && line.startsWith(RegExp(r'\s'))) {
        optionItems[optionItems.length - 1] += '\n${line.trim()}';
      } else {
        isList = false;
        break;
      }
    }
    if (isList && optionItems.isNotEmpty) {
      if (optionsSection && !optionItems.any(_containsLink)) {
        final options = optionItems.map(_MessageOption.new).toList();
        if (blocks.isNotEmpty && blocks.last is _OptionListBlock) {
          (blocks.last as _OptionListBlock).options.addAll(options);
        } else {
          blocks.add(_OptionListBlock(options));
        }
      } else {
        blocks.add(_ParagraphBlock(lines.join('\n')));
      }
      continue;
    }
    optionsSection = false;

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

bool _isOptionsHeading(String line) {
  final label = _plainInlineText(line.replaceFirst(RegExp(r'^#{1,6}\s+'), ''))
      .trim()
      .replaceFirst(RegExp(r':$'), '')
      .toLowerCase();
  return const {
    'quick options',
    'options',
    'opciones',
    'opciones rápidas',
    'opciones rapidas'
  }.contains(label);
}

List<md.Node> _inlineNodes(String text) => md.Document(
      encodeHtml: false,
      extensionSet: md.ExtensionSet.gitHubFlavored,
    ).parseInline(text);

String _plainInlineText(String text) =>
    _inlineNodes(text).map((node) => node.textContent).join();

bool _containsLink(String text) {
  bool visit(md.Node node) =>
      node is md.Element &&
      (node.tag == 'a' || (node.children?.any(visit) ?? false));
  return _inlineNodes(text).any(visit);
}

/// Text spans keep code and links inside the selectable text buffer. WidgetSpan
/// contributes U+FFFC (the OBJ placeholder) to Android's selection clipboard.
class _SelectableInlineText extends StatefulWidget {
  const _SelectableInlineText({
    required this.text,
    required this.textColor,
    required this.style,
    this.onLinkTap,
  });

  final String text;
  final Color textColor;
  final TextStyle style;
  final Future<void> Function(String target)? onLinkTap;

  @override
  State<_SelectableInlineText> createState() => _SelectableInlineTextState();
}

class _SelectableInlineTextState extends State<_SelectableInlineText> {
  final _recognizers = <TapGestureRecognizer>[];
  late TextSpan _span;

  @override
  void initState() {
    super.initState();
    _updateSpans();
  }

  @override
  void didUpdateWidget(_SelectableInlineText oldWidget) {
    super.didUpdateWidget(oldWidget);
    _updateSpans();
  }

  void _disposeRecognizers() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
  }

  void _updateSpans() {
    _disposeRecognizers();
    _span =
        TextSpan(children: _inlineNodes(widget.text).map(_spanFor).toList());
  }

  TextSpan _spanFor(md.Node node, [TapGestureRecognizer? link]) {
    if (node is md.Text) {
      return TextSpan(text: node.text, recognizer: link);
    }
    if (node is! md.Element) return const TextSpan();
    var recognizer = link;
    TextStyle? style;
    switch (node.tag) {
      case 'code':
        style = TextStyle(
          fontFamily: 'monospace',
          backgroundColor: widget.textColor.withValues(alpha: 0.08),
        );
      case 'strong':
        style = const TextStyle(fontWeight: FontWeight.w700);
      case 'em':
        style = const TextStyle(fontStyle: FontStyle.italic);
      case 'del':
        style = const TextStyle(decoration: TextDecoration.lineThrough);
      case 'br':
        return const TextSpan(text: '\n');
      case 'a':
        final target = node.attributes['href'];
        if (target != null) {
          recognizer = TapGestureRecognizer()
            ..onTap = () async {
              if (widget.onLinkTap != null) {
                await widget.onLinkTap!(target);
              } else {
                await Clipboard.setData(ClipboardData(text: target));
              }
            };
          _recognizers.add(recognizer);
          style = TextStyle(
            color: ThemeData.estimateBrightnessForColor(widget.textColor) ==
                    Brightness.light
                ? const Color(0xFFB9D8FF)
                : const Color(0xFF123C69),
            decoration: TextDecoration.underline,
          );
        }
    }
    return TextSpan(
      style: style,
      recognizer: recognizer,
      children:
          node.children?.map((child) => _spanFor(child, recognizer)).toList(),
    );
  }

  @override
  Widget build(BuildContext context) => SelectableText.rich(
        _span,
        style: widget.style,
      );

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }
}
