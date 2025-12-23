import 'package:flutter/material.dart';

import '../models/meeting_request.dart';
import '../utils/date_formatters.dart';

class RequestCardMessage extends StatelessWidget {
  const RequestCardMessage({
    super.key,
    required this.request,
    required this.onViewDetails,
    required this.onProposeTimes,
    required this.onShare,
    required this.onConfirm,
  });

  final MeetingRequest request;
  final VoidCallback onViewDetails;
  final VoidCallback onProposeTimes;
  final VoidCallback onShare;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: theme.dividerColor),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            request.title,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            '${request.durationMinutes} min · ${request.timezone}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 6),
          Text(
            '${formatMonthDay(request.dateRangeStart)} - ${formatMonthDay(request.dateRangeEnd)}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 6),
          _StatusPill(status: request.status),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton(
                onPressed: onViewDetails,
                child: const Text('View details'),
              ),
              OutlinedButton(
                onPressed: onProposeTimes,
                child: const Text('Propose times'),
              ),
              OutlinedButton(
                onPressed: onShare,
                child: const Text('Share link'),
              ),
              FilledButton(
                onPressed: onConfirm,
                child: const Text('Confirm time'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});

  final MeetingRequestStatus status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String label;
    switch (status) {
      case MeetingRequestStatus.draft:
        label = 'Draft';
      case MeetingRequestStatus.pending:
        label = 'Pending';
      case MeetingRequestStatus.optionsGenerated:
        label = 'Options ready';
      case MeetingRequestStatus.confirmed:
        label = 'Confirmed';
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.primary.withOpacity(0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }
}
