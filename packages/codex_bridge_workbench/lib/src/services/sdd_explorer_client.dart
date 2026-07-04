import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/sdd_project.dart';

class SddExplorerClient {
  SddExplorerClient({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<SddProjectsIndex> listProjects() async {
    final response = await _client.get(Uri.parse('$baseUrl/sdd/projects'));
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD projects: ${response.body}');
    }
    return SddProjectsIndex.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddProject> getProject(String workspacePath) async {
    final uri = Uri.parse('$baseUrl/sdd/project').replace(
      queryParameters: <String, String>{'workspace_path': workspacePath},
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD project: ${response.body}');
    }
    return SddProject.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<SddDiagram>> getProjectDiagrams(String workspacePath) async {
    final uri = Uri.parse('$baseUrl/sdd/project/diagrams').replace(
      queryParameters: <String, String>{'workspace_path': workspacePath},
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD diagrams: ${response.body}');
    }
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final rawDiagrams = payload['diagrams'];
    if (rawDiagrams is! List) {
      return const <SddDiagram>[];
    }
    return rawDiagrams
        .whereType<Map<String, dynamic>>()
        .map(SddDiagram.fromJson)
        .toList(growable: false);
  }

  Future<SddProject?> loadDefaultProject() async {
    final index = await listProjects();
    if (index.projects.isEmpty) {
      return null;
    }
    final defaultPath = index.defaultWorkspacePath;
    final selected = defaultPath == null
        ? index.projects.first
        : index.projects.firstWhere(
            (project) => project.workspacePath == defaultPath,
            orElse: () => index.projects.first,
          );
    final project = await getProject(selected.workspacePath);
    await getProjectDiagrams(selected.workspacePath);
    return project;
  }
}
