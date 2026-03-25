import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;

import '../models/job_status_response.dart';
import '../models/agent_configuration.dart';
import '../models/agent_profile.dart';
import '../models/chat_message.dart';
import '../models/server_capabilities.dart';
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

  Future<ServerCapabilities> getCapabilities() async {
    final response = await _client.get(Uri.parse('$baseUrl/capabilities'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch capabilities: ${response.body}');
    }

    return ServerCapabilities.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
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

  Future<List<AgentProfile>> listAgentProfiles() async {
    final response = await _client.get(Uri.parse('$baseUrl/agent-profiles'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<AgentProfile>> exportAgentProfiles() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/agent-profiles/export'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to export agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        if (workspacePath != null) 'workspace_path': workspacePath,
        if (agentProfileId != null) 'agent_profile_id': agentProfileId,
      }),
    );

    if (response.statusCode != 201) {
      throw Exception('Failed to create session: ${response.body}');
    }

    return SessionDetail.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<AgentProfile> createAgentProfile({
    required String name,
    required String description,
    required String colorHex,
    required AgentConfiguration configuration,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/agent-profiles'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'name': name,
        'description': description,
        'color_hex': colorHex,
        'configuration': configuration.toJson(),
      }),
    );

    if (response.statusCode != 201) {
      throw Exception('Failed to create agent profile: ${response.body}');
    }

    return AgentProfile.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<AgentProfile>> importAgentProfiles(
    List<AgentProfile> profiles,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/agent-profiles/import'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'profiles': profiles.map((profile) => profile.toJson()).toList(),
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to import agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
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

  Future<SessionDetail> updateAutoMode(
    String sessionId, {
    required bool enabled,
    required int maxTurns,
    String? reviewerPrompt,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/auto-mode'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'enabled': enabled,
        'max_turns': maxTurns,
        'reviewer_prompt': reviewerPrompt,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to update auto mode: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/agents'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(configuration.toJson()),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to update agent configuration: ${response.body}',
      );
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> setSessionArchived(
    String sessionId, {
    required bool archived,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/archive'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'archived': archived,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to update archive state: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> applyAgentProfile(
    String sessionId, {
    required String profileId,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/agent-profile'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'profile_id': profileId,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to apply agent profile: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
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

  Future<JobStatusResponse> cancelJob(String jobId) async {
    final response =
        await _client.post(Uri.parse('$baseUrl/jobs/$jobId/cancel'));

    if (response.statusCode != 200) {
      throw Exception('Failed to cancel job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> retryJob(String jobId) async {
    final response =
        await _client.post(Uri.parse('$baseUrl/jobs/$jobId/retry'));

    if (response.statusCode != 202) {
      throw Exception('Failed to retry job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<SessionDetail> recoverMessage(
    String sessionId,
    String messageId, {
    required MessageRecoveryAction action,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions/$sessionId/messages/$messageId/recovery'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'action': action == MessageRecoveryAction.cancel ? 'cancel' : 'retry',
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to recover message: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
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
