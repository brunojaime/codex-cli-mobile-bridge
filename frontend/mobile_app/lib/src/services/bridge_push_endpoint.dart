/// Public host routing for the non-disruptive push companion. Other bridge
/// installations can serve /notifications directly on their existing backend.
String bridgePushServiceUrl(String server) {
  final uri = Uri.parse(server);
  if (uri.host == 'batata-default-string.tail0302c4.ts.net') {
    if (uri.port == 8118) return uri.replace(scheme: 'http', port: 8126).toString().replaceAll(RegExp(r'/$'), '');
    if (uri.port == 80 || uri.port == 443) return uri.replace(scheme: 'http', port: 8125).toString().replaceAll(RegExp(r'/$'), '');
  }
  return server;
}
