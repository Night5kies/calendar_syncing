import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/providers.dart';
import '../../utils/date_formatters.dart';
import '../../widgets/conversation_row.dart';
import '../../widgets/section_header.dart';

class ChatsTab extends ConsumerWidget {
  const ChatsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appStateProvider);
    final favorites =
        state.conversations.where((item) => item.isFavorite).toList();
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Messages',
            style: theme.textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          TextField(
            decoration: InputDecoration(
              hintText: 'Search',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: const Icon(Icons.tune),
            ),
            onChanged: (value) {},
          ),
          const SizedBox(height: 20),
          if (favorites.isNotEmpty) ...[
            const SectionHeader(title: 'Favorites'),
            const SizedBox(height: 12),
            SizedBox(
              height: 76,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: favorites.length,
                separatorBuilder: (_, __) => const SizedBox(width: 12),
                itemBuilder: (context, index) {
                  final convo = favorites[index];
                  return Column(
                    children: [
                      CircleAvatar(
                        radius: 24,
                        backgroundColor:
                            theme.colorScheme.primary.withOpacity(0.12),
                        child: Text(
                          convo.avatarInitials,
                          style: TextStyle(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        convo.name.split(' ').first,
                        style: theme.textTheme.labelSmall,
                      ),
                    ],
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
          ],
          Row(
            children: [
              Text(
                'Inbox',
                style: theme.textTheme.titleMedium,
              ),
              const Spacer(),
              Text(
                '${state.conversations.length} chats',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Expanded(
            child: ListView.separated(
              itemCount: state.conversations.length,
              separatorBuilder: (_, __) => Divider(
                height: 24,
                color: theme.dividerColor,
              ),
              itemBuilder: (context, index) {
                final conversation = state.conversations[index];
                return TweenAnimationBuilder<double>(
                  duration: const Duration(milliseconds: 300),
                  tween: Tween(begin: 0, end: 1),
                  curve: Curves.easeOut,
                  builder: (context, value, child) {
                    return Transform.translate(
                      offset: Offset(0, 12 * (1 - value)),
                      child: Opacity(opacity: value, child: child),
                    );
                  },
                  child: ConversationRow(
                    conversation: conversation,
                    onTap: () {
                      ref
                          .read(appStateProvider.notifier)
                          .markConversationRead(conversation.id);
                      context.push('/chat/${conversation.id}');
                    },
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Last updated ${formatChatTimestamp(DateTime.now())} ago',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurface.withOpacity(0.4),
            ),
          ),
        ],
      ),
    );
  }
}
