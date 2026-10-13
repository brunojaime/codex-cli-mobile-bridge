import 'dart:convert';
import 'dart:typed_data';

import 'package:html/dom.dart';
import 'package:html/parser.dart' as html;

/// A document-only origin: never the Bridge origin, cookies or API URLs.
const htmlPreviewOrigin = 'https://bridge-document.invalid';
const maxHtmlBytes = 5 * 1024 * 1024;

typedef HtmlAssetLoader = Future<Uint8List> Function(String path);

Uri htmlDocumentUri(String path) => Uri.parse(htmlPreviewOrigin)
    .replace(path: '/${path.replaceFirst(RegExp(r'^/+'), '')}');

class PreparedHtml {
  const PreparedHtml(this.html, this.unavailableAssets);
  final String html;
  final int unavailableAssets;
}

/// Embeds workspace assets so the WebView never receives server credentials.
/// Only passive document resources are read; the server enforces workspace ACLs.
class HtmlDocumentBuilder {
  HtmlDocumentBuilder(this.loadAsset);
  final HtmlAssetLoader loadAsset;
  final _cache = <String, String>{};
  int _bytes = 0;
  int _requests = 0;
  int _missing = 0;

  static const _mime = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'svg': 'image/svg+xml',
    'ico': 'image/x-icon',
    'woff': 'font/woff',
    'woff2': 'font/woff2',
    'ttf': 'font/ttf',
    'otf': 'font/otf',
    'css': 'text/css',
  };

  Future<String> _asset(String value, Uri base, {int depth = 0}) async {
    final raw = value.trim();
    if (raw.startsWith('#')) return raw;
    final uri = base.resolve(raw);
    if (uri.scheme == 'data') return raw;
    if (!const {'http', 'https'}.contains(uri.scheme) ||
        uri.origin != htmlPreviewOrigin) {
      _missing++;
      return '';
    }
    final path = Uri.decodeComponent(uri.path.substring(1));
    final ext = path.split('.').last.toLowerCase();
    final mime = _mime[ext];
    if (mime == null || depth > 4) {
      _missing++;
      return '';
    }
    if (_cache.containsKey(path)) return _cache[path]!;
    if (++_requests > 64 || _bytes >= 15 * 1024 * 1024) {
      _missing++;
      return '';
    }
    _cache[path] = ''; // Break cyclic CSS imports.
    try {
      final bytes = await loadAsset(path).timeout(const Duration(seconds: 15));
      _bytes += bytes.length;
      if (_bytes > 15 * 1024 * 1024) throw StateError('Asset limit');
      final content = ext == 'css'
          ? utf8.encode(await _css(
              utf8.decode(bytes, allowMalformed: true), uri, depth + 1))
          : bytes;
      return _cache[path] = 'data:$mime;base64,${base64Encode(content)}';
    } catch (_) {
      _missing++;
      return '';
    }
  }

  Future<String> _css(String css, Uri base, int depth) async {
    // Normalize quoted @import to url(), preserving media conditions.
    css = css.replaceAllMapped(
        RegExp(r'''@import\s+["']([^"']+)["']''', caseSensitive: false),
        (m) => '@import url("${m[1]}")');
    final urls = RegExp(r'''url\(\s*(?:"([^"]*)"|'([^']*)'|([^\s)]*))\s*\)''',
        caseSensitive: false);
    final out = StringBuffer();
    var end = 0;
    for (final match in urls.allMatches(css)) {
      out.write(css.substring(end, match.start));
      final value = match[1] ?? match[2] ?? match[3]!;
      out.write('url("${await _asset(value, base, depth: depth)}")');
      end = match.end;
    }
    out.write(css.substring(end));
    return out.toString();
  }

  Future<PreparedHtml> build(String source, String path) async {
    if (utf8.encode(source).length > maxHtmlBytes) {
      throw StateError('El HTML supera el límite de vista previa de 5 MB.');
    }
    final document = html.parse(source);
    final base = htmlDocumentUri(path);
    for (final element in document.querySelectorAll(
        'script,iframe,frame,frameset,object,embed,base,meta[http-equiv],link[rel="preload"],link[rel="prefetch"]')) {
      element.remove();
    }
    for (final element in document.querySelectorAll('*')) {
      element.attributes.removeWhere((key, value) =>
          key.toString().toLowerCase().startsWith('on') ||
          const {'srcdoc', 'ping', 'formaction', 'action', 'srcset'}
              .contains(key.toString().toLowerCase()));
      if (element.attributes.containsKey('style')) {
        element.attributes['style'] =
            await _css(element.attributes['style']!, base, 0);
      }
      if (element.localName == 'style') {
        element.text = await _css(element.text, base, 0);
      }
      if (element.localName == 'img' && element.attributes.containsKey('src')) {
        element.attributes['src'] =
            await _asset(element.attributes['src']!, base);
      }
      if (element.localName == 'link') {
        if (element.attributes['rel']?.toLowerCase() == 'stylesheet') {
          element.attributes['href'] =
              await _asset(element.attributes['href'] ?? '', base);
        } else {
          element.remove();
        }
      }
      if (element.localName == 'a') {
        element.attributes.remove('target');
        final href = element.attributes['href'];
        final uri = href == null ? null : Uri.tryParse(href);
        if (uri == null ||
            (uri.hasScheme &&
                !const {'http', 'https', 'mailto', 'tel'}
                    .contains(uri.scheme))) {
          element.attributes.remove('href');
        }
      }
    }
    final head = document.head!;
    if (head.querySelector('meta[name="viewport"]') == null) {
      head.append(Element.tag('meta')
        ..attributes.addAll({
          'name': 'viewport',
          'content': 'width=device-width, initial-scale=1'
        }));
    }
    head.nodes.insert(
        0,
        Element.tag('meta')
          ..attributes.addAll({
            'http-equiv': 'Content-Security-Policy',
            'content':
                "default-src 'none'; img-src data:; style-src 'unsafe-inline' data:; font-src data:; base-uri 'none'; form-action 'none'; connect-src 'none'",
          }));
    return PreparedHtml(
        '<!DOCTYPE html>\n${document.documentElement!.outerHtml}', _missing);
  }
}
