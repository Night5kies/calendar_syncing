import 'package:flutter/material.dart';

import '../models/time_slot.dart';
import '../utils/date_formatters.dart';

class SlotCard extends StatelessWidget {
  const SlotCard({
    super.key,
    required this.slot,
    required this.onConfirm,
  });

  final TimeSlot slot;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: slot.isConfirmed
            ? theme.colorScheme.primary.withOpacity(0.12)
            : Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${formatMonthDay(slot.start)} · ${formatTime(context, slot.start)} - ${formatTime(context, slot.end)}',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              if (slot.score > 0)
                Text(
                  '${slot.score}%',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.primary,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            slot.explanation,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerRight,
            child: slot.isConfirmed
                ? Text(
                    'Confirmed',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.primary,
                    ),
                  )
                : OutlinedButton(
                    onPressed: onConfirm,
                    child: const Text('Confirm time'),
                  ),
          ),
        ],
      ),
    );
  }
}
