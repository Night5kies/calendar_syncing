import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/meeting_request.dart';
import '../../state/providers.dart';
import '../../utils/date_formatters.dart';
import '../../widgets/app_scaffold.dart';
import '../../widgets/primary_button.dart';
import '../../widgets/section_header.dart';
import '../../widgets/slot_card.dart';

class RequestDetailScreen extends ConsumerWidget {
  const RequestDetailScreen({super.key, required this.requestId});

  final String requestId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appStateProvider);
    final request = state.requestsById[requestId];
    if (request == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Request not found')),
      );
    }
    final isGenerating = state.generatingRequests.contains(requestId);

    return AppScaffold(
      title: 'Request details',
      actions: [
        IconButton(
          icon: const Icon(Icons.ios_share),
          onPressed: () async {
            await Clipboard.setData(
              const ClipboardData(text: 'https://sync.app/r/1234'),
            );
            if (!context.mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Share link copied.')),
            );
          },
        ),
      ],
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        children: [
          Text(request.title, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 6),
          Text(
            '${request.durationMinutes} min · ${request.timezone}',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 6),
          Text(
            '${formatMonthDay(request.dateRangeStart)} - ${formatMonthDay(request.dateRangeEnd)}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 8),
          _StatusLine(status: request.status),
          const SizedBox(height: 20),
          const SectionHeader(title: 'Participants'),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: request.participants
                .map((participant) => Chip(label: Text(participant.email)))
                .toList(),
          ),
          if (request.notes != null) ...[
            const SizedBox(height: 20),
            const SectionHeader(title: 'Notes'),
            const SizedBox(height: 8),
            Text(request.notes!),
          ],
          const SizedBox(height: 20),
          PrimaryButton(
            label: 'Generate time options',
            isLoading: isGenerating,
            onPressed: () async {
              await ref
                  .read(appStateProvider.notifier)
                  .generateTimeSlots(requestId);
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Time options ready.')),
              );
            },
          ),
          const SizedBox(height: 24),
          const SectionHeader(title: 'Ranked options'),
          const SizedBox(height: 12),
          if (request.slots.isEmpty)
            Text(
              'Generate options to see recommended times.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withOpacity(0.6),
                  ),
            )
          else
            Column(
              children: request.slots
                  .map(
                    (slot) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: SlotCard(
                        slot: slot,
                        onConfirm: () {
                          ref
                              .read(appStateProvider.notifier)
                              .confirmSlot(requestId, slot);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Time confirmed (mock).'),
                            ),
                          );
                        },
                      ),
                    ),
                  )
                  .toList(),
            ),
          const SizedBox(height: 24),
          const SectionHeader(title: 'Share link'),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Theme.of(context).dividerColor),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'https://sync.app/r/1234',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                TextButton(
                  onPressed: () async {
                    await Clipboard.setData(
                      const ClipboardData(text: 'https://sync.app/r/1234'),
                    );
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Link copied.')),
                    );
                  },
                  child: const Text('Copy'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          PrimaryButton(
            label: 'Back to chat',
            onPressed: () {
              context.pop();
            },
          ),
        ],
      ),
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.status});

  final MeetingRequestStatus status;

  @override
  Widget build(BuildContext context) {
    String label;
    switch (status) {
      case MeetingRequestStatus.draft:
        label = 'Draft';
      case MeetingRequestStatus.pending:
        label = 'Pending responses';
      case MeetingRequestStatus.optionsGenerated:
        label = 'Options ready';
      case MeetingRequestStatus.confirmed:
        label = 'Confirmed';
    }
    return Row(
      children: [
        const Icon(Icons.circle, size: 10),
        const SizedBox(width: 8),
        Text(label),
      ],
    );
  }
}
