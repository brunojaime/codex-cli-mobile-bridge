import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;

class CodexChecksumVerifier {
  const CodexChecksumVerifier();

  Future<bool> verifySha256(String filePath, String expectedSha256) async {
    final normalizedExpected = expectedSha256.trim().toLowerCase();
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(normalizedExpected)) {
      return false;
    }
    final digest = await crypto.sha256.bind(File(filePath).openRead()).first;
    return const HexEncoder().convert(digest.bytes) == normalizedExpected;
  }
}

class HexEncoder extends Converter<List<int>, String> {
  const HexEncoder();

  @override
  String convert(List<int> input) {
    final buffer = StringBuffer();
    for (final byte in input) {
      buffer.write(byte.toRadixString(16).padLeft(2, '0'));
    }
    return buffer.toString();
  }
}
