import 'dart:async';

import 'package:flutter/material.dart';

import '../models/project_documents.dart';
import '../services/api_client.dart';

class ProjectDocumentsPanel extends StatefulWidget {
  const ProjectDocumentsPanel({
    super.key,
    required this.apiClient,
    required this.workspacePath,
    required this.onRequestCharterChange,
  });

  final ApiClient apiClient;
  final String workspacePath;
  final ValueChanged<String> onRequestCharterChange;

  @override
  State<ProjectDocumentsPanel> createState() => _ProjectDocumentsPanelState();
}

class _ProjectDocumentsPanelState extends State<ProjectDocumentsPanel> {
  final TextEditingController _releaseVersionController =
      TextEditingController();
  ProjectDocuments? _documents;
  ProjectDocumentCharterDetail? _charter;
  ProjectDocumentValidationResult? _exportValidation;
  List<ProjectDocumentRelease> _releases = const <ProjectDocumentRelease>[];
  ProjectDocumentRelease? _selectedRelease;
  String? _errorText;
  bool _isLoading = true;
  bool _isRefreshingRender = false;
  bool _isReleasing = false;
  bool _isLoadingRelease = false;
  bool _isSharing = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(covariant ProjectDocumentsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspacePath != widget.workspacePath ||
        oldWidget.apiClient != widget.apiClient) {
      _selectedRelease = null;
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _releaseVersionController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (widget.workspacePath.trim().isEmpty) {
      setState(() {
        _isLoading = false;
        _errorText = 'No workspace selected for project documents.';
      });
      return;
    }
    setState(() {
      _isLoading = true;
      _errorText = null;
    });
    try {
      final results = await Future.wait<Object>(<Future<Object>>[
        widget.apiClient.listProjectDocuments(
          workspacePath: widget.workspacePath,
        ),
        widget.apiClient.getProjectDocumentCharter(
          workspacePath: widget.workspacePath,
        ),
        widget.apiClient.validateProjectDocumentCharter(
          workspacePath: widget.workspacePath,
          clientExport: true,
        ),
        widget.apiClient.listProjectDocumentCharterReleases(
          workspacePath: widget.workspacePath,
        ),
      ]);
      if (!mounted) {
        return;
      }
      final documents = results[0] as ProjectDocuments;
      final charter = results[1] as ProjectDocumentCharterDetail;
      final validation = results[2] as ProjectDocumentCharterValidationResponse;
      final releases = results[3] as ProjectDocumentCharterReleasesResponse;
      setState(() {
        _documents = documents;
        _charter = charter;
        _exportValidation = validation.validation;
        _releases = releases.releases;
        _releaseVersionController.text = _nextReleaseVersion(charter);
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorText = '$error';
        _isLoading = false;
      });
    }
  }

  Future<void> _refreshRender() async {
    if (_isRefreshingRender) {
      return;
    }
    setState(() {
      _isRefreshingRender = true;
      _errorText = null;
    });
    try {
      await widget.apiClient.renderProjectDocumentCharter(
        workspacePath: widget.workspacePath,
      );
      await _load();
    } catch (error) {
      if (mounted) {
        setState(() {
          _errorText = '$error';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isRefreshingRender = false;
        });
      }
    }
  }

  Future<void> _releaseCharter() async {
    if (!_canRelease || _isReleasing) {
      return;
    }
    final version = _releaseVersionController.text.trim();
    if (version.isEmpty) {
      setState(() {
        _errorText = 'Release version is required.';
      });
      return;
    }
    setState(() {
      _isReleasing = true;
      _errorText = null;
    });
    try {
      await widget.apiClient.releaseProjectDocumentCharter(
        workspacePath: widget.workspacePath,
        version: version,
        changedFields: const <String>[],
        clientExport: true,
      );
      await _load();
    } catch (error) {
      if (mounted) {
        setState(() {
          _errorText = '$error';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isReleasing = false;
        });
      }
    }
  }

  Future<void> _openRelease(ProjectDocumentRelease release) async {
    if (_isLoadingRelease) {
      return;
    }
    setState(() {
      _isLoadingRelease = true;
      _errorText = null;
    });
    try {
      final detail = await widget.apiClient.getProjectDocumentCharterRelease(
        workspacePath: widget.workspacePath,
        version: release.version,
        includeRenderContent: false,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedRelease = detail.release ?? release;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _errorText = '$error';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingRelease = false;
        });
      }
    }
  }

  Future<void> _shareCharter() async {
    if (_isSharing) {
      return;
    }
    final request = await showDialog<_ShareCharterRequest>(
      context: context,
      builder: (context) => const _ShareCharterDialog(),
    );
    if (request == null || !mounted) {
      return;
    }
    setState(() {
      _isSharing = true;
      _errorText = null;
    });
    try {
      await widget.apiClient.shareProjectDocumentCharter(
        workspacePath: widget.workspacePath,
        recipients: request.recipients,
        includeFullDocument: request.includeFullDocument,
        message: request.message,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Acta enviada por correo.')),
        );
      }
    } catch (error) {
      if (mounted) {
        setState(() => _errorText = '$error');
      }
    } finally {
      if (mounted) {
        setState(() => _isSharing = false);
      }
    }
  }

  bool get _canRelease {
    final charter = _charter;
    final validation = _exportValidation;
    if (charter == null || validation == null) {
      return false;
    }
    return validation.ok && charter.hasFreshRender;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_isLoading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: CircularProgressIndicator(),
        ),
      );
    }

    final charter = _charter;
    if (charter == null) {
      return _ErrorPanel(
        message: _errorText ?? 'Project documents are not available.',
        onRetry: _load,
      );
    }

    final validation = _exportValidation ?? charter.validation;
    final modules = _documents?.modules ?? const <ProjectDocumentModule>[];
    final releaseDisabledReason = _releaseDisabledReason(charter, validation);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (_errorText != null)
          _StatusBanner(
            color: const Color(0xFF3B1521),
            foregroundColor: Colors.white,
            text: _errorText!,
          ),
        _HeaderSection(
          workspaceName: charter.workspaceName,
          status: charter.status,
          draftVersion: charter.draftVersion,
          deliveredVersion: charter.deliveredVersion,
          updatedAt: charter.updatedAt,
          latestRelease: charter.latestRelease,
          validation: validation,
          renderFresh: charter.hasFreshRender,
          renderPath: charter.render.path,
        ),
        const SizedBox(height: 12),
        _PreviewSection(charter: charter, onRefreshRender: _refreshRender),
        const SizedBox(height: 12),
        _ValidationSection(validation: validation),
        const SizedBox(height: 12),
        _ModuleContextSection(modules: modules),
        const SizedBox(height: 12),
        _ActionsSection(
          releaseVersionController: _releaseVersionController,
          canRelease: _canRelease,
          releaseDisabledReason: releaseDisabledReason,
          isRefreshingRender: _isRefreshingRender,
          isReleasing: _isReleasing,
          isSharing: _isSharing,
          onRefreshRender: _refreshRender,
          onRelease: _releaseCharter,
          onShare: _shareCharter,
          onRequestChange: () {
            widget.onRequestCharterChange(
              'Trabajemos sobre el acta de proyecto. '
              'Quiero ajustar una parte del documento manteniendo el marco '
              'documental y sin preparar una version entregable al cliente '
              'hasta que lo pida explicitamente.',
            );
          },
        ),
        const SizedBox(height: 12),
        _ReleasesSection(
          releases: _releases,
          selectedRelease: _selectedRelease,
          isLoadingRelease: _isLoadingRelease,
          onOpenRelease: _openRelease,
        ),
        SizedBox(height: theme.visualDensity.baseSizeAdjustment.dy.abs() + 12),
      ],
    );
  }

  String? _releaseDisabledReason(
    ProjectDocumentCharterDetail charter,
    ProjectDocumentValidationResult validation,
  ) {
    if (!validation.ok) {
      return 'Resolve blocking validation issues before client delivery.';
    }
    if (!charter.hasFreshRender) {
      return 'Refresh render before creating a client-delivered version.';
    }
    return null;
  }
}

class _HeaderSection extends StatelessWidget {
  const _HeaderSection({
    required this.workspaceName,
    required this.status,
    required this.draftVersion,
    required this.deliveredVersion,
    required this.updatedAt,
    required this.latestRelease,
    required this.validation,
    required this.renderFresh,
    required this.renderPath,
  });

  final String workspaceName;
  final String status;
  final String? draftVersion;
  final String? deliveredVersion;
  final String? updatedAt;
  final String? latestRelease;
  final ProjectDocumentValidationResult validation;
  final bool renderFresh;
  final String renderPath;

  @override
  Widget build(BuildContext context) {
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(Icons.description_outlined, color: Color(0xFF55D6BE)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Acta de Proyecto',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      workspaceName,
                      style: const TextStyle(color: Color(0xFF9CA8C7)),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              _Pill(label: 'Status', value: status),
              _Pill(label: 'Draft', value: draftVersion ?? 'not set'),
              _Pill(label: 'Delivered', value: deliveredVersion ?? 'none'),
              _Pill(label: 'Latest release', value: latestRelease ?? 'none'),
              _Pill(
                label: 'Validation',
                value: validation.ok
                    ? 'passing'
                    : '${validation.blockingCount} blocking',
                accent: validation.ok
                    ? const Color(0xFF55D6BE)
                    : const Color(0xFFFFC857),
              ),
              _Pill(
                label: 'Render',
                value: renderFresh ? 'fresh' : 'refresh needed',
                accent: renderFresh
                    ? const Color(0xFF55D6BE)
                    : const Color(0xFFFFC857),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _KeyValue(label: 'Updated', value: updatedAt ?? 'not available'),
          _KeyValue(label: 'Render path', value: renderPath),
        ],
      ),
    );
  }
}

class _PreviewSection extends StatelessWidget {
  const _PreviewSection({
    required this.charter,
    required this.onRefreshRender,
  });

  final ProjectDocumentCharterDetail charter;
  final VoidCallback onRefreshRender;

  @override
  Widget build(BuildContext context) {
    final render = charter.render;
    final previewText = _renderPreviewText(render.content, charter);
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _SectionTitle(
            icon: Icons.article_outlined,
            title: 'Latest Preview',
            trailing: IconButton(
              tooltip: 'Refresh render',
              icon: const Icon(Icons.refresh),
              color: const Color(0xFF55D6BE),
              onPressed: onRefreshRender,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            render.exists
                ? 'HTML render fallback · ${render.path}'
                : 'No rendered preview yet',
            style: const TextStyle(color: Color(0xFF9CA8C7)),
          ),
          const SizedBox(height: 10),
          Container(
            constraints: BoxConstraints(
              minHeight: 240,
              maxHeight: MediaQuery.sizeOf(context).height * 0.62,
            ),
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE1E7F0)),
            ),
            child: SingleChildScrollView(
              child: SelectableText(
                previewText,
                style: const TextStyle(
                  color: Color(0xFF172033),
                  fontSize: 16,
                  height: 1.55,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ValidationSection extends StatelessWidget {
  const _ValidationSection({required this.validation});

  final ProjectDocumentValidationResult validation;

  @override
  Widget build(BuildContext context) {
    final issues = validation.issues;
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _SectionTitle(
            icon: validation.ok
                ? Icons.verified_outlined
                : Icons.report_problem_outlined,
            title: 'Validation',
          ),
          const SizedBox(height: 8),
          if (issues.isEmpty)
            const Text(
              'No validation issues.',
              style: TextStyle(color: Color(0xFFDCE5FF)),
            )
          else
            ...issues.map((issue) => _ValidationIssueTile(issue: issue)),
        ],
      ),
    );
  }
}

class _ModuleContextSection extends StatelessWidget {
  const _ModuleContextSection({required this.modules});

  final List<ProjectDocumentModule> modules;

  @override
  Widget build(BuildContext context) {
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const _SectionTitle(
            icon: Icons.account_tree_outlined,
            title: 'Module Context',
          ),
          const SizedBox(height: 8),
          if (modules.isEmpty)
            const Text(
              'No project-management modules found.',
              style: TextStyle(color: Color(0xFF9CA8C7)),
            )
          else
            ...modules.map((module) => _ModuleTile(module: module)),
        ],
      ),
    );
  }
}

class _ActionsSection extends StatelessWidget {
  const _ActionsSection({
    required this.releaseVersionController,
    required this.canRelease,
    required this.releaseDisabledReason,
    required this.isRefreshingRender,
    required this.isReleasing,
    required this.isSharing,
    required this.onRefreshRender,
    required this.onRelease,
    required this.onShare,
    required this.onRequestChange,
  });

  final TextEditingController releaseVersionController;
  final bool canRelease;
  final String? releaseDisabledReason;
  final bool isRefreshingRender;
  final bool isReleasing;
  final bool isSharing;
  final VoidCallback onRefreshRender;
  final VoidCallback onRelease;
  final VoidCallback onShare;
  final VoidCallback onRequestChange;

  @override
  Widget build(BuildContext context) {
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const _SectionTitle(icon: Icons.tune_outlined, title: 'Actions'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: <Widget>[
              OutlinedButton.icon(
                onPressed: onRequestChange,
                icon: const Icon(Icons.edit_note_outlined),
                label: const Text('Request charter change'),
              ),
              OutlinedButton.icon(
                onPressed: isRefreshingRender ? null : onRefreshRender,
                icon: isRefreshingRender
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
                label: const Text('Refresh render'),
              ),
              OutlinedButton.icon(
                onPressed: isSharing ? null : onShare,
                icon: isSharing
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.mail_outline),
                label: const Text('Compartir por correo'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 240),
            child: TextField(
              controller: releaseVersionController,
              decoration: const InputDecoration(
                labelText: 'Client version',
                isDense: true,
                border: OutlineInputBorder(),
              ),
              style: const TextStyle(color: Colors.white),
            ),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: canRelease && !isReleasing ? onRelease : null,
            icon: isReleasing
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.lock_outline),
            label: const Text('Create client version'),
          ),
          if (releaseDisabledReason != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              releaseDisabledReason!,
              style: const TextStyle(color: Color(0xFFFFC857)),
            ),
          ],
        ],
      ),
    );
  }
}

class _ShareCharterRequest {
  const _ShareCharterRequest({
    required this.recipients,
    required this.includeFullDocument,
    this.message,
  });

  final List<String> recipients;
  final bool includeFullDocument;
  final String? message;
}

class _ShareCharterDialog extends StatefulWidget {
  const _ShareCharterDialog();

  @override
  State<_ShareCharterDialog> createState() => _ShareCharterDialogState();
}

class _ShareCharterDialogState extends State<_ShareCharterDialog> {
  final _recipientsController = TextEditingController();
  final _messageController = TextEditingController();
  bool _includeFullDocument = true;
  String? _error;

  @override
  void dispose() {
    _recipientsController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Compartir Acta de Proyecto'),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                controller: _recipientsController,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                  labelText: 'Destinatarios',
                  hintText: 'nombre@empresa.com',
                  helperText: 'Separar multiples correos con coma.',
                  errorText: _error,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _messageController,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Mensaje opcional',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _includeFullDocument,
                onChanged: (value) {
                  setState(() => _includeFullDocument = value ?? true);
                },
                title: const Text('Incluir documento completo'),
                subtitle: const Text('Adjunta el Acta en Markdown y HTML.'),
              ),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: _submit,
          icon: const Icon(Icons.send_outlined),
          label: const Text('Enviar'),
        ),
      ],
    );
  }

  void _submit() {
    final recipients = _recipientsController.text
        .split(RegExp(r'[,;\s]+'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (recipients.isEmpty || recipients.any((item) => !item.contains('@'))) {
      setState(() => _error = 'Ingresa al menos un correo valido.');
      return;
    }
    Navigator.pop(
      context,
      _ShareCharterRequest(
        recipients: recipients,
        includeFullDocument: _includeFullDocument,
        message: _messageController.text.trim().isEmpty
            ? null
            : _messageController.text.trim(),
      ),
    );
  }
}

class _ReleasesSection extends StatelessWidget {
  const _ReleasesSection({
    required this.releases,
    required this.selectedRelease,
    required this.isLoadingRelease,
    required this.onOpenRelease,
  });

  final List<ProjectDocumentRelease> releases;
  final ProjectDocumentRelease? selectedRelease;
  final bool isLoadingRelease;
  final ValueChanged<ProjectDocumentRelease> onOpenRelease;

  @override
  Widget build(BuildContext context) {
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const _SectionTitle(
            icon: Icons.history_outlined,
            title: 'Previous Versions',
          ),
          const SizedBox(height: 8),
          if (releases.isEmpty)
            const Text(
              'No delivered versions yet.',
              style: TextStyle(color: Color(0xFF9CA8C7)),
            )
          else
            ...releases.map(
              (release) => _ReleaseTile(
                release: release,
                isLoading: isLoadingRelease,
                onOpen: () => onOpenRelease(release),
              ),
            ),
          if (selectedRelease != null) ...<Widget>[
            const Divider(height: 24, color: Color(0xFF23304F)),
            Text(
              'Open release ${selectedRelease!.version}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              selectedRelease!.path,
              style: const TextStyle(color: Color(0xFF9CA8C7)),
            ),
            const SizedBox(height: 8),
            Text(
              selectedRelease!.source?.content?.trim().isNotEmpty == true
                  ? selectedRelease!.source!.content!.trim()
                  : 'Release source loaded. Render content is kept as a safe reference.',
              maxLines: 8,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Color(0xFFDCE5FF), height: 1.35),
            ),
          ],
        ],
      ),
    );
  }
}

class _Surface extends StatelessWidget {
  const _Surface({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF121A30),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF23304F)),
      ),
      child: child,
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({
    required this.icon,
    required this.title,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(icon, color: const Color(0xFF8CA8FF), size: 20),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            title,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                ),
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({
    required this.label,
    required this.value,
    this.accent = const Color(0xFF8CA8FF),
  });

  final String label;
  final String value;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 34),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0xFF16213C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: accent.withValues(alpha: 0.55)),
      ),
      child: Text.rich(
        TextSpan(
          children: <InlineSpan>[
            TextSpan(
              text: '$label: ',
              style: const TextStyle(color: Color(0xFF9CA8C7)),
            ),
            TextSpan(
              text: value,
              style: TextStyle(color: accent, fontWeight: FontWeight.w800),
            ),
          ],
        ),
      ),
    );
  }
}

class _KeyValue extends StatelessWidget {
  const _KeyValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text.rich(
        TextSpan(
          children: <InlineSpan>[
            TextSpan(
              text: '$label: ',
              style: const TextStyle(color: Color(0xFF9CA8C7)),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(color: Color(0xFFDCE5FF)),
            ),
          ],
        ),
      ),
    );
  }
}

class _ValidationIssueTile extends StatelessWidget {
  const _ValidationIssueTile({required this.issue});

  final ProjectDocumentValidationIssue issue;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color:
            issue.blocking ? const Color(0xFF362411) : const Color(0xFF16213C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: issue.blocking
              ? const Color(0xFFFFC857)
              : const Color(0xFF23304F),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: <Widget>[
              _SmallTag(text: issue.severity.toUpperCase()),
              _SmallTag(text: issue.code),
              if (issue.affectedFile.isNotEmpty)
                _SmallTag(text: issue.affectedFile),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            issue.message,
            style: const TextStyle(color: Colors.white),
          ),
          if (issue.nextAction.isNotEmpty) ...<Widget>[
            const SizedBox(height: 4),
            Text(
              issue.nextAction,
              style: const TextStyle(color: Color(0xFFDCE5FF)),
            ),
          ],
        ],
      ),
    );
  }
}

class _ModuleTile extends StatelessWidget {
  const _ModuleTile({required this.module});

  final ProjectDocumentModule module;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF16213C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF23304F)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            module.loadByDefault
                ? Icons.visibility_outlined
                : Icons.visibility_off_outlined,
            color: module.loadByDefault
                ? const Color(0xFF55D6BE)
                : const Color(0xFF9CA8C7),
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: <Widget>[
                    Text(
                      module.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    _SmallTag(text: module.status),
                    _SmallTag(
                      text: module.loadByDefault
                          ? 'loads by default'
                          : 'on request',
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  module.description,
                  style: const TextStyle(color: Color(0xFF9CA8C7)),
                ),
                Text(
                  module.path,
                  style: const TextStyle(color: Color(0xFFDCE5FF)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReleaseTile extends StatelessWidget {
  const _ReleaseTile({
    required this.release,
    required this.isLoading,
    required this.onOpen,
  });

  final ProjectDocumentRelease release;
  final bool isLoading;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF16213C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF23304F)),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  release.version,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  release.releasedAt ?? release.path,
                  style: const TextStyle(color: Color(0xFF9CA8C7)),
                ),
              ],
            ),
          ),
          TextButton.icon(
            onPressed: isLoading ? null : onOpen,
            icon: const Icon(Icons.open_in_new_outlined, size: 18),
            label: const Text('Open'),
          ),
        ],
      ),
    );
  }
}

class _SmallTag extends StatelessWidget {
  const _SmallTag({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF0B1224),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF23304F)),
      ),
      child: Text(
        text,
        style: const TextStyle(color: Color(0xFFDCE5FF), fontSize: 12),
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({
    required this.color,
    required this.foregroundColor,
    required this.text,
  });

  final Color color;
  final Color foregroundColor;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: TextStyle(color: foregroundColor)),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _Surface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const _SectionTitle(
            icon: Icons.error_outline,
            title: 'Project Documents',
          ),
          const SizedBox(height: 8),
          Text(message, style: const TextStyle(color: Color(0xFFFFC857))),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

String _renderPreviewText(
  String? html,
  ProjectDocumentCharterDetail charter,
) {
  final sourceFallback = charter.sourceSummary.excerpt.trim();
  final raw = html?.trim();
  if (raw == null || raw.isEmpty) {
    return sourceFallback.isEmpty
        ? 'Render preview is not available yet.'
        : sourceFallback;
  }
  final withoutScripts = raw
      .replaceAll(
          RegExp(r'<script\b[^>]*>[\s\S]*?</script>', caseSensitive: false), '')
      .replaceAll(
          RegExp(r'<style\b[^>]*>[\s\S]*?</style>', caseSensitive: false), '');
  final text = withoutScripts
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(
          RegExp(r'</(p|h[1-6]|li|tr|section|article)>', caseSensitive: false),
          '\n')
      .replaceAll(RegExp(r'<[^>]+>'), ' ')
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\n\s+'), '\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
  if (text.isEmpty) {
    return sourceFallback.isEmpty ? 'Render preview is empty.' : sourceFallback;
  }
  return text;
}

String _nextReleaseVersion(ProjectDocumentCharterDetail charter) {
  final current = charter.latestRelease ?? charter.deliveredVersion;
  if (current == null || current.trim().isEmpty) {
    return 'v1.0';
  }
  final match = RegExp(r'^v(\d+)\.(\d+)(?:\.(\d+))?$').firstMatch(current);
  if (match == null) {
    return 'v1.0';
  }
  final major = int.tryParse(match.group(1) ?? '') ?? 1;
  final minor = int.tryParse(match.group(2) ?? '') ?? 0;
  return 'v$major.${minor + 1}';
}
