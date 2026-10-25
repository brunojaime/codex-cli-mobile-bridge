bool isInternalChatLink(String target) =>
    target.trim().toLowerCase().startsWith('codex-bridge:');

String? internalChatSessionId(String target) {
  final uri = Uri.tryParse(target.trim());
  if (uri == null ||
      uri.scheme != 'codex-bridge' ||
      uri.host != 'chat' ||
      uri.userInfo.isNotEmpty ||
      uri.hasPort ||
      uri.hasQuery ||
      uri.hasFragment ||
      uri.pathSegments.length != 1) {
    return null;
  }
  final id = uri.pathSegments.single;
  return RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
  ).hasMatch(id)
      ? id.toLowerCase()
      : null;
}
