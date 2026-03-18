import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../state/providers.dart';
import '../../utils/date_formatters.dart';
import '../../widgets/app_scaffold.dart';
import '../../widgets/primary_button.dart';

class AttendeeShareScreen extends ConsumerStatefulWidget {
  const AttendeeShareScreen({super.key, required this.requestId});

  final String requestId;

  @override
  ConsumerState<AttendeeShareScreen> createState() =>
      _AttendeeShareScreenState();
}

class _AttendeeShareScreenState extends ConsumerState<AttendeeShareScreen> {
  final Map<String, bool> _availability = {};

  @override
  Widget build(BuildContext context) {
    final request = ref.watch(appStateProvider).requestsById[widget.requestId];
    if (request == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Request not found')),
      );
    }

    return AppScaffold(
      title: 'Respond to request',
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        children: [
          Text(
            request.title,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
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
          const SizedBox(height: 20),
          Text(
            'Pick every option that works for you',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          if (request.slots.isEmpty)
            Text(
              'No time options yet. Ask the host to add manual options.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withOpacity(0.6),
                  ),
            )
          else
            Column(
              children: request.slots.map((slot) {
                final value = _availability[slot.id] ?? false;
                return SwitchListTile.adaptive(
                  value: value,
                  onChanged: (next) {
                    setState(() {
                      _availability[slot.id] = next;
                    });
                  },
                  title: Text(
                    '${formatMonthDay(slot.start)} · ${formatTime(context, slot.start)}',
                  ),
                  subtitle: Text(
                    slot.explanation,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                );
              }).toList(),
            ),
          const SizedBox(height: 24),
          PrimaryButton(
            label: 'Submit response',
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Response sent (mock).')),
              );
            },
          ),
        ],
      ),
    );
  }
}
