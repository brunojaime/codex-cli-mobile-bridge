import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../models/job_status_response.dart';
import '../models/agent_configuration.dart';
import '../models/agent_profile.dart';
import '../models/chat_message.dart';
import '../models/codex_tooling.dart';
import '../models/feedback_queue_item.dart';
import '../models/server_capabilities.dart';
import '../models/session_detail.dart';
import '../models/chat_session_summary.dart';
import '../models/server_health.dart';
import '../models/workspace.dart';

class SynthesizedSpeechClip {
  const SynthesizedSpeechClip({
    required this.audioBytes,
    required this.contentType,
    required this.responseFormat,
  });

  final List<int> audioBytes;
  final String contentType;
  final String responseFormat;
}

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

  Future<SynthesizedSpeechClip> synthesizeSpeech(String text) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/audio/speech'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'text': text,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to synthesize speech: ${response.body}');
    }

    return SynthesizedSpeechClip(
      audioBytes: response.bodyBytes,
      contentType: response.headers['content-type'] ?? 'audio/mpeg',
      responseFormat: response.headers['x-response-format'] ?? 'mp3',
    );
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

  Future<CodexToolingSnapshot> getCodexTooling({
    String? workspacePath,
  }) async {
    final uri = Uri.parse('$baseUrl/codex/tooling').replace(
      queryParameters: <String, String>{
        if (workspacePath != null && workspacePath.trim().isNotEmpty)
          'workspace_path': workspacePath,
      },
    );
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch Codex tooling: ${response.body}');
    }

    return CodexToolingSnapshot.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<CodexMcpAppInstallResult> installCodexMcpApp(String appId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/codex/mcp-apps/$appId/install'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to install MCP app: ${response.body}');
    }

    return CodexMcpAppInstallResult.fromJson(
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
    bool turnSummariesEnabled = false,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        if (workspacePath != null) 'workspace_path': workspacePath,
        if (agentProfileId != null) 'agent_profile_id': agentProfileId,
        'turn_summaries_enabled': turnSummariesEnabled,
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

  Future<SessionDetail> updateTurnSummaries(
    String sessionId, {
    required bool enabled,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/turn-summaries'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'enabled': enabled,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to update turn summaries: ${_turnSummaryErrorDetail(response)}',
      );
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  String _turnSummaryErrorDetail(http.Response response) {
    final detail = _responseErrorDetail(response);
    if (response.statusCode == 404 && detail.toLowerCase() == 'not found') {
      return 'Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.';
    }
    return detail;
  }

  String _responseErrorDetail(http.Response response) {
    final body = response.body.trim();
    if (body.isEmpty) {
      return 'HTTP ${response.statusCode}';
    }
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          return detail.trim();
        }
      }
    } catch (_) {
      // Fall back to the raw body for non-JSON responses.
    }
    return body;
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
    CodexRunOptions? codexRunOptions,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/message'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'message': message,
        if (sessionId != null) 'session_id': sessionId,
        if (workspacePath != null) 'workspace_path': workspacePath,
        if (codexRunOptions != null && !codexRunOptions.isEmpty)
          'codex_options': codexRunOptions.toJson(),
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
    CodexRunOptions? codexRunOptions,
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
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] =
          jsonEncode(codexRunOptions.toJson());
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
    CodexRunOptions? codexRunOptions,
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
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] =
          jsonEncode(codexRunOptions.toJson());
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

  Future<List<FeedbackQueueItem>> listFeedbackQueue({
    bool includeImages = false,
  }) async {
    final uri = Uri.parse('$baseUrl/feedback-queue').replace(
      queryParameters: <String, String>{
        if (includeImages) 'include_images': 'true',
      },
    );
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to list feedback queue: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => FeedbackQueueItem.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteFeedbackQueueItem(String id) async {
    final response =
        await _client.delete(Uri.parse('$baseUrl/feedback-queue/$id'));
    if (response.statusCode != 204) {
      throw Exception('Failed to delete feedback item: ${response.body}');
    }
  }

  Future<void> clearFeedbackQueue() async {
    final response = await _client.delete(Uri.parse('$baseUrl/feedback-queue'));
    if (response.statusCode != 204) {
      throw Exception('Failed to clear feedback queue: ${response.body}');
    }
  }

  Future<JobStatusResponse> startFeedbackQueueSession(
    String id, {
    String? message,
    String? sessionId,
    String? workspacePath,
    FeedbackQueueTargetMode targetMode = FeedbackQueueTargetMode.generatorOnly,
    CodexRunOptions? codexRunOptions,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/feedback-queue/$id/start-session'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (message != null && message.trim().isNotEmpty)
          'message': message.trim(),
        if (sessionId != null) 'session_id': sessionId,
        if (workspacePath != null) 'workspace_path': workspacePath,
        'target_mode': targetMode.apiValue,
        if (codexRunOptions != null && !codexRunOptions.isEmpty)
          'codex_options': codexRunOptions.toJson(),
      }),
    );

    if (response.statusCode != 202) {
      throw Exception('Failed to start feedback session: ${response.body}');
    }

    return JobStatusResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<JobStatusResponse> sendDocumentMessage(
    XFile documentFile, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
    CodexRunOptions? codexRunOptions,
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
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] =
          jsonEncode(codexRunOptions.toJson());
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
    CodexRunOptions? codexRunOptions,
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
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] =
          jsonEncode(codexRunOptions.toJson());
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
    final mimeType = file.mimeType?.trim();
    final filename = _filenameFromXFile(file);
    return http.MultipartFile.fromBytes(
      field,
      await file.readAsBytes(),
      filename: filename,
      contentType: mimeType == null || mimeType.isEmpty
          ? null
          : MediaType.parse(mimeType),
    );
  }

  String? _filenameFromXFile(XFile file) {
    final name = file.name.trim();
    if (name.isNotEmpty) {
      return name;
    }
    final path = file.path.trim();
    if (path.isEmpty) {
      return null;
    }
    final normalized = path.replaceAll('\\', '/');
    final segments = normalized
        .split('/')
        .where((segment) => segment.trim().isNotEmpty)
        .toList();
    return segments.isEmpty ? null : segments.last;
  }
}
