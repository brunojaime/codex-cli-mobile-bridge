import 'dart:async';

import 'package:flutter/material.dart';

import '../models/project_secrets.dart';
import '../services/api_client.dart';

class ProjectSecretsSheet extends StatefulWidget {
  const ProjectSecretsSheet({
    super.key,
    required this.apiClient,
    required this.workspacePath,
    required this.workspaceName,
  });

  final ApiClient apiClient;
  final String workspacePath;
  final String workspaceName;

  @override
  State<ProjectSecretsSheet> createState() => _ProjectSecretsSheetState();
}

class _ProjectSecretsSheetState extends State<ProjectSecretsSheet> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _valueController = TextEditingController();
  ProjectSecrets? _secrets;
  bool _isLoading = true;
  bool _isSaving = false;
  bool _showForm = false;
  String? _errorText;
  String? _statusText;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _nameController.dispose();
    _valueController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorText = null;
    });
    try {
      final secrets = await widget.apiClient.listProjectSecrets(
        workspacePath: widget.workspacePath,
      );
      if (!mounted) return;
      setState(() {
        _secrets = secrets;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorText = 'Could not load project secrets.\n$error';
      });
    }
  }

  Future<void> _save() async {
    if (_isSaving || !(_formKey.currentState?.validate() ?? false)) return;
    final name = _nameController.text.trim();
    setState(() {
      _isSaving = true;
      _errorText = null;
      _statusText = null;
    });
    try {
      final secrets = await widget.apiClient.setProjectSecret(
        workspacePath: widget.workspacePath,
        name: name,
        value: _valueController.text,
      );
      _valueController.clear();
      _nameController.clear();
      if (!mounted) return;
      setState(() {
        _secrets = secrets;
        _isSaving = false;
        _showForm = false;
        _statusText = '$name saved in .env. Its value cannot be viewed here.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isSaving = false;
        _errorText = 'Could not save the secret.\n$error';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    final names = _secrets?.names ?? const <String>[];
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(16, 12, 16, 20 + bottomInset),
        child: Align(
          alignment: Alignment.topCenter,
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      const Icon(Icons.lock_outline_rounded),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            const Text(
                              'Project secrets',
                              style: TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            Text(
                              widget.workspaceName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: 'Refresh',
                        onPressed: _isLoading ? null : _load,
                        icon: const Icon(Icons.refresh_rounded),
                      ),
                      IconButton(
                        tooltip: 'Close',
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.close_rounded),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Stored in .env. Values are write-only and never returned by the server.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_isLoading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 28),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (_errorText != null && _secrets == null)
                    _ProjectSecretMessage(
                      icon: Icons.error_outline_rounded,
                      text: _errorText!,
                      isError: true,
                    )
                  else if (names.isEmpty)
                    const _ProjectSecretMessage(
                      icon: Icons.key_off_outlined,
                      text: 'No secrets configured for this project.',
                    )
                  else
                    DecoratedBox(
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest
                            .withValues(alpha: 0.38),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: ListView.separated(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: names.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) => ListTile(
                          minTileHeight: 48,
                          leading: const Icon(Icons.key_rounded, size: 20),
                          title: Text(
                            names[index],
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          trailing: const Text('••••••••'),
                        ),
                      ),
                    ),
                  if (_errorText != null && _secrets != null) ...<Widget>[
                    const SizedBox(height: 12),
                    _ProjectSecretMessage(
                      icon: Icons.error_outline_rounded,
                      text: _errorText!,
                      isError: true,
                    ),
                  ],
                  if (_statusText != null) ...<Widget>[
                    const SizedBox(height: 12),
                    _ProjectSecretMessage(
                      icon: Icons.check_circle_outline_rounded,
                      text: _statusText!,
                    ),
                  ],
                  const SizedBox(height: 16),
                  if (!_showForm)
                    FilledButton.icon(
                      key: const ValueKey<String>('add-project-secret'),
                      onPressed: _isLoading
                          ? null
                          : () {
                              setState(() {
                                _showForm = true;
                                _errorText = null;
                                _statusText = null;
                              });
                            },
                      icon: const Icon(Icons.add_rounded),
                      label: const Text('Add secret'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(48),
                      ),
                    )
                  else
                    Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          TextFormField(
                            key: const ValueKey<String>('project-secret-name'),
                            controller: _nameController,
                            enabled: !_isSaving,
                            textCapitalization: TextCapitalization.characters,
                            textInputAction: TextInputAction.next,
                            autocorrect: false,
                            enableSuggestions: false,
                            decoration: const InputDecoration(
                              labelText: 'Name',
                              hintText: 'WORDPRESS_PASSWORD',
                              border: OutlineInputBorder(),
                            ),
                            validator: (value) {
                              final normalized = value?.trim() ?? '';
                              if (normalized.isEmpty) {
                                return 'Enter a secret name.';
                              }
                              if (!RegExp(r'^[A-Za-z_][A-Za-z0-9_]*$')
                                  .hasMatch(normalized)) {
                                return 'Use letters, numbers, and underscores; do not start with a number.';
                              }
                              return null;
                            },
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            key: const ValueKey<String>('project-secret-value'),
                            controller: _valueController,
                            enabled: !_isSaving,
                            obscureText: true,
                            enableSuggestions: false,
                            autocorrect: false,
                            keyboardType: TextInputType.visiblePassword,
                            textInputAction: TextInputAction.done,
                            onFieldSubmitted: (_) => unawaited(_save()),
                            decoration: const InputDecoration(
                              labelText: 'Secret value',
                              border: OutlineInputBorder(),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Enter the secret value.'
                                : null,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Using an existing name replaces its current value.',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 14),
                          FilledButton.icon(
                            key: const ValueKey<String>('save-project-secret'),
                            onPressed: _isSaving ? null : _save,
                            icon: _isSaving
                                ? const SizedBox.square(
                                    dimension: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.lock_rounded),
                            label: const Text('Add secret'),
                            style: FilledButton.styleFrom(
                              minimumSize: const Size.fromHeight(48),
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ProjectSecretMessage extends StatelessWidget {
  const _ProjectSecretMessage({
    required this.icon,
    required this.text,
    this.isError = false,
  });

  final IconData icon;
  final String text;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final foreground = isError ? colors.onErrorContainer : colors.onSurface;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isError
            ? colors.errorContainer
            : colors.surfaceContainerHighest.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(icon, size: 20, color: foreground),
            const SizedBox(width: 10),
            Expanded(child: Text(text, style: TextStyle(color: foreground))),
          ],
        ),
      ),
    );
  }
}
