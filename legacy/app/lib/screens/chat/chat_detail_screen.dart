import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/message.dart';
import '../../state/providers.dart';
import '../../utils/date_formatters.dart';
import '../../widgets/message_bubble.dart';
import '../../widgets/request_card_message.dart';

class ChatDetailScreen extends ConsumerStatefulWidget {
  const ChatDetailScreen({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ChatDetailScreen> createState() => _ChatDetailScreenState();
}

class _ChatDetailScreenState extends ConsumerState<ChatDetailScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(appStateProvider);
    final conversation = state.conversations
        .firstWhere((item) => item.id == widget.conversationId);
    final messages =
        state.messagesByConversation[widget.conversationId] ?? [];
    final items = _buildChatItems(messages);

    return Scaffold(
      appBar: AppBar(
        title: Text(conversation.name),
        actions: [
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'create') {
                context.push('/chat/${conversation.id}/request/create');
              }
              if (value == 'members') {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Members list is mocked.')),
                );
              }
            },
            itemBuilder: (context) => const [
              PopupMenuItem(value: 'create', child: Text('Create request')),
              PopupMenuItem(value: 'members', child: Text('Members')),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.separated(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              itemCount: items.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final item = items[index];
                return TweenAnimationBuilder<double>(
                  duration: const Duration(milliseconds: 250),
                  tween: Tween(begin: 0, end: 1),
                  curve: Curves.easeOut,
                  builder: (context, value, child) {
                    return Transform.translate(
                      offset: Offset(0, 10 * (1 - value)),
                      child: Opacity(opacity: value, child: child),
                    );
                  },
                  child: item.when(
                    separator: (label) => Center(
                      child: Text(
                        label,
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withOpacity(0.5),
                            ),
                      ),
                    ),
                    message: (message) {
                      if (message.type == MessageType.requestCard) {
                        final requestId = message.requestId;
                        final request =
                            requestId == null ? null : state.requestsById[requestId];
                        if (request == null) {
                          return const SizedBox.shrink();
                        }
                        return Align(
                          alignment: message.isMe
                              ? Alignment.centerRight
                              : Alignment.centerLeft,
                          child: SizedBox(
                            width: MediaQuery.of(context).size.width * 0.75,
                            child: RequestCardMessage(
                              request: request,
                              onViewDetails: () {
                                context.push('/request/${request.id}');
                              },
                              onProposeTimes: () {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Propose times is mocked.'),
                                  ),
                                );
                              },
                              onShare: () async {
                                await Clipboard.setData(const ClipboardData(
                                    text: 'https://sync.app/r/1234'));
                                if (!mounted) return;
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Share link copied.'),
                                  ),
                                );
                              },
                              onConfirm: () {
                                context.push('/request/${request.id}');
                              },
                            ),
                          ),
                        );
                      }
                      return Align(
                        alignment: message.isMe
                            ? Alignment.centerRight
                            : Alignment.centerLeft,
                        child: MessageBubble(
                          isMe: message.isMe,
                          text: message.text ?? '',
                          timeLabel: formatTime(context, message.timestamp),
                        ),
                      );
                    },
                  ),
                );
              },
            ),
          ),
          _InputBar(
            controller: _controller,
            onSend: () {
              final text = _controller.text.trim();
              if (text.isEmpty) {
                return;
              }
              ref
                  .read(appStateProvider.notifier)
                  .addTextMessage(widget.conversationId, text);
              _controller.clear();
              _scrollController.animateTo(
                _scrollController.position.maxScrollExtent + 120,
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeOut,
              );
            },
            onSchedule: () {
              context.push('/chat/${widget.conversationId}/request/create');
            },
          ),
        ],
      ),
    );
  }

  List<_ChatItem> _buildChatItems(List<Message> messages) {
    final items = <_ChatItem>[];
    DateTime? lastTime;
    for (final message in messages) {
      if (lastTime == null ||
          message.timestamp.difference(lastTime).inHours >= 6) {
        items.add(_ChatItem.separator(formatMonthDayYear(message.timestamp)));
      }
      items.add(_ChatItem.message(message));
      lastTime = message.timestamp;
    }
    return items;
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.onSend,
    required this.onSchedule,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final VoidCallback onSchedule;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
        child: Row(
          children: [
            IconButton(
              onPressed: onSchedule,
              icon: const Icon(Icons.add_circle_outline),
            ),
            Expanded(
              child: TextField(
                controller: controller,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: const InputDecoration(
                  hintText: 'Message',
                ),
              ),
            ),
            IconButton(
              onPressed: onSend,
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatItem {
  const _ChatItem._({
    this.message,
    this.separatorLabel,
  });

  final Message? message;
  final String? separatorLabel;

  factory _ChatItem.message(Message message) =>
      _ChatItem._(message: message);
  factory _ChatItem.separator(String label) =>
      _ChatItem._(separatorLabel: label);

  T when<T>({
    required T Function(Message message) message,
    required T Function(String label) separator,
  }) {
    if (this.message != null) {
      return message(this.message!);
    }
    return separator(separatorLabel!);
  }
}
