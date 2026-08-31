import '../models/conversation.dart';
import '../models/meeting_request.dart';
import '../models/message.dart';
import '../models/participant.dart';
import '../models/time_slot.dart';
import '../state/app_state.dart';

class MockRepository {
  AppState buildInitialState() {
    final now = DateTime.now();

    final participants = [
      const Participant(
        id: 'p1',
        name: 'You',
        email: 'you@sync.app',
        isMe: true,
      ),
      const Participant(
        id: 'p2',
        name: 'Alex Parker',
        email: 'alex@studio.co',
      ),
      const Participant(
        id: 'p3',
        name: 'Jules Kim',
        email: 'jules@studio.co',
      ),
    ];

    final request = MeetingRequest(
      id: 'r1',
      title: 'Project Sync',
      durationMinutes: 30,
      timezone: 'Pacific Time',
      dateRangeStart: now.add(const Duration(days: 2)),
      dateRangeEnd: now.add(const Duration(days: 7)),
      daysOfWeek: const [],
      timesOfDay: const [],
      participants: participants,
      status: MeetingRequestStatus.pending,
      slots: buildMockSlots(now.add(const Duration(days: 2))),
      meetingType: 'Video call',
      notes: 'Quick alignment before launch.',
    );

    final conversations = [
      Conversation(
        id: 'c1',
        name: 'Alex Parker',
        avatarInitials: 'AP',
        lastMessagePreview: 'Got it, I can do next week.',
        lastMessageAt: now.subtract(const Duration(minutes: 12)),
        unreadCount: 2,
        isGroup: false,
        isFavorite: true,
        members: const ['Alex Parker'],
      ),
      Conversation(
        id: 'c2',
        name: 'Design Team',
        avatarInitials: 'DT',
        lastMessagePreview: 'Can we do a quick sync?',
        lastMessageAt: now.subtract(const Duration(hours: 3)),
        unreadCount: 0,
        isGroup: true,
        isFavorite: true,
        members: const ['Riya', 'Marco', 'Ava'],
      ),
      Conversation(
        id: 'c3',
        name: 'Jordan Lee',
        avatarInitials: 'JL',
        lastMessagePreview: 'Thanks for the heads up.',
        lastMessageAt: now.subtract(const Duration(days: 1)),
        unreadCount: 1,
        isGroup: false,
        isFavorite: false,
        members: const ['Jordan Lee'],
      ),
    ];

    final messagesByConversation = {
      'c1': [
        Message(
          id: 'm1',
          conversationId: 'c1',
          senderName: 'Alex Parker',
          isMe: false,
          timestamp: now.subtract(const Duration(hours: 20)),
          type: MessageType.text,
          text: 'Could we lock a time for next week?',
        ),
        Message(
          id: 'm2',
          conversationId: 'c1',
          senderName: 'You',
          isMe: true,
          timestamp: now.subtract(const Duration(hours: 18)),
          type: MessageType.text,
          text: 'Sure, I will send a quick request.',
        ),
        Message(
          id: 'm3',
          conversationId: 'c1',
          senderName: 'You',
          isMe: true,
          timestamp: now.subtract(const Duration(hours: 17)),
          type: MessageType.requestCard,
          requestId: request.id,
        ),
        Message(
          id: 'm4',
          conversationId: 'c1',
          senderName: 'Alex Parker',
          isMe: false,
          timestamp: now.subtract(const Duration(minutes: 12)),
          type: MessageType.text,
          text: 'Got it, I can do next week.',
        ),
      ],
      'c2': [
        Message(
          id: 'm5',
          conversationId: 'c2',
          senderName: 'Riya',
          isMe: false,
          timestamp: now.subtract(const Duration(hours: 5)),
          type: MessageType.text,
          text: 'Weekly retro time check?',
        ),
      ],
      'c3': [
        Message(
          id: 'm6',
          conversationId: 'c3',
          senderName: 'Jordan Lee',
          isMe: false,
          timestamp: now.subtract(const Duration(days: 2)),
          type: MessageType.text,
          text: 'Thanks for the heads up.',
        ),
      ],
    };

    final requestsById = {
      request.id: request,
    };

    return AppState(
      conversations: conversations,
      messagesByConversation: messagesByConversation,
      requestsById: requestsById,
      generatingRequests: <String>{},
    );
  }

  List<TimeSlot> buildMockSlots(DateTime baseDate) {
    return [
      TimeSlot(
        id: 's1',
        start: DateTime(baseDate.year, baseDate.month, baseDate.day, 9, 30),
        end: DateTime(baseDate.year, baseDate.month, baseDate.day, 10, 0),
        score: 0,
        explanation: 'Manual option 1',
      ),
      TimeSlot(
        id: 's2',
        start: DateTime(baseDate.year, baseDate.month, baseDate.day, 14, 0),
        end: DateTime(baseDate.year, baseDate.month, baseDate.day, 14, 30),
        score: 0,
        explanation: 'Manual option 2',
      ),
      TimeSlot(
        id: 's3',
        start: DateTime(baseDate.year, baseDate.month, baseDate.day, 16, 0),
        end: DateTime(baseDate.year, baseDate.month, baseDate.day, 16, 30),
        score: 0,
        explanation: 'Manual option 3',
      ),
    ];
  }
}
