import 'package:flutter/material.dart';

import '../models/session_detail.dart';
import '../presentation/agent_execution_presentation.dart';

class ReviewerStatusPresentation {
  const ReviewerStatusPresentation({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final Color backgroundColor;
  final Color foregroundColor;
}

ReviewerStatusPresentation reviewerStatusPresentation(SessionDetail session) {
  final shared = buildReviewerLifecyclePresentation(session);
  return ReviewerStatusPresentation(
    title: shared.title,
    subtitle: shared.subtitle,
    icon: shared.icon,
    backgroundColor: shared.bannerBackgroundColor,
    foregroundColor: shared.bannerForegroundColor,
  );
}

class ReviewerStatusBanner extends StatelessWidget {
  const ReviewerStatusBanner({
    super.key,
    required this.session,
  });

  final SessionDetail session;

  @override
  Widget build(BuildContext context) {
    final presentation = reviewerStatusPresentation(session);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: presentation.backgroundColor,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            presentation.icon,
            color: presentation.foregroundColor,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  presentation.title,
                  style: TextStyle(
                    color: presentation.foregroundColor,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  presentation.subtitle,
                  style: TextStyle(
                    color: presentation.foregroundColor.withValues(alpha: 0.9),
                    fontSize: 12,
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
