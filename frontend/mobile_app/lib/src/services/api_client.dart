import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;

import '../models/job_status_response.dart';
import '../models/session_detail.dart';
import '../models/chat_session_summary.dart';
import '../models/server_health.dart';
import '../models/workspace.dart';

class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Uri jobStreamUri(String jobId) {
    final httpUri = Uri.parse(baseUrl);
    final scheme = httpUri.scheme == 'https' ? 'wss' : 'ws';
    return httpUri.replace(
      scheme: scheme,
      path: '${httpUri.path.replaceAll(RegExp(r'/$'), '')}/ws/jobs/$jobId',
    );
  }

  Future<List<ChatSessionSummary>> listSessions() async {
    final response = await _client.get(Uri.parse('$baseUrl/sessions'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list sessions: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map(
            (item) => ChatSessionSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<ServerHealth> getHealth() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch health: ${response.body}');
    }

    return ServerHealth.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<Workspace>> listWorkspaces() async {
    final response = await _client.get(Uri.parse('$baseUrl/workspaces'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list workspaces: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => Workspace.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        if (workspacePath != null) 'workspace_path': workspacePath,
      }),
    );

    if (response.statusCode != 201) {
      throw Exception('Failed to create session: ${response.body}');
    }

    return SessionDetail.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<SessionDetail> getSession(String sessionId) async {
    final response =
        await _client.get(Uri.parse('$baseUrl/sessions/$sessionId'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch session: ${response.body}');
    }

    return SessionDetail.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<JobStatusResponse> sendMessage(
    String message, {
    String? sessionId,
    String? workspacePath,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/message'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'message': message,
        if (sessionId != null) 'session_id': sessionId,
        if (workspacePath != null) 'workspace_path': workspacePath,
      }),
    );

    if (response.statusCode != 202) {
      throw Exception('Failed to create job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendAudioMessage(
    XFile audioFile, {
    String? sessionId,
    String? workspacePath,
    String? language,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/audio'),
    );
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (language != null) {
      request.fields['language'] = language;
    }

    request.files.add(
      await _multipartFileFromXFile('audio', audioFile),
    );

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload audio message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendImageMessage(
    XFile imageFile, {
    String? message,
    String? sessionId,
    String? workspacePath,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/image'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }

    request.files.add(
      await _multipartFileFromXFile('image', imageFile),
    );

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload image message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendDocumentMessage(
    XFile documentFile, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/document'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (language != null) {
      request.fields['language'] = language;
    }

    request.files.add(
      await _multipartFileFromXFile('document', documentFile),
    );

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload document message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendAttachmentsMessage(
    List<XFile> attachments, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
  }) async {
    if (attachments.isEmpty) {
      throw Exception('No attachments were provided.');
    }

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/attachments'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (language != null) {
      request.fields['language'] = language;
    }

    for (final attachment in attachments) {
      request.files.add(
        await _multipartFileFromXFile('attachments', attachment),
      );
    }

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload attachments: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> getJob(String jobId) async {
    final response = await _client.get(Uri.parse('$baseUrl/response/$jobId'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<http.MultipartFile> _multipartFileFromXFile(
    String field,
    XFile file,
  ) async {
    return http.MultipartFile.fromBytes(
      field,
      await file.readAsBytes(),
      filename: file.name,
    );
  }
}
