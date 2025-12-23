import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/mock_repository.dart';
import '../models/conversation.dart';
import '../models/meeting_request.dart';
import '../models/message.dart';
import '../models/participant.dart';
import '../models/time_slot.dart';
import 'app_state.dart';

class AppStateNotifier extends StateNotifier<AppState> {
  AppStateNotifier(this._repository) : super(_repository.buildInitialState());

  final MockRepository _repository;

  void markConversationRead(String conversationId) {
    final updated = state.conversations.map((conversation) {
      if (conversation.id == conversationId && conversation.unreadCount > 0) {
        return conversation.copyWith(unreadCount: 0);
      }
      return conversation;
    }).toList();
    state = state.copyWith(conversations: updated);
  }

  void addTextMessage(String conversationId, String text) {
    final message = Message(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      conversationId: conversationId,
      senderName: 'You',
      isMe: true,
      timestamp: DateTime.now(),
      type: MessageType.text,
      text: text,
    );
    _addMessage(conversationId, message, preview: text);
  }

  void addRequestMessage(String conversationId, MeetingRequest request) {
    final message = Message(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      conversationId: conversationId,
      senderName: 'You',
      isMe: true,
      timestamp: DateTime.now(),
      type: MessageType.requestCard,
      requestId: request.id,
    );
    final updatedRequests = Map<String, MeetingRequest>.from(state.requestsById)
      ..[request.id] = request;

    state = state.copyWith(requestsById: updatedRequests);
    _addMessage(conversationId, message,
        preview: 'Request: ${request.title}');
  }

  Future<void> generateTimeSlots(String requestId) async {
    if (state.generatingRequests.contains(requestId)) {
      return;
    }
    final generating = Set<String>.from(state.generatingRequests)
      ..add(requestId);
    state = state.copyWith(generatingRequests: generating);

    await Future.delayed(const Duration(milliseconds: 1400));

    final request = state.requestsById[requestId];
    if (request == null) {
      return;
    }

    final slots = _repository.buildMockSlots(request.dateRangeStart);
    final updated = request.copyWith(
      status: MeetingRequestStatus.optionsGenerated,
      slots: slots,
    );

    final updatedRequests = Map<String, MeetingRequest>.from(state.requestsById)
      ..[requestId] = updated;
    final nextGenerating = Set<String>.from(state.generatingRequests)
      ..remove(requestId);

    state = state.copyWith(
      requestsById: updatedRequests,
      generatingRequests: nextGenerating,
    );
  }

  void confirmSlot(String requestId, TimeSlot slot) {
    final request = state.requestsById[requestId];
    if (request == null) {
      return;
    }

    final updatedSlots = request.slots
        .map((item) => item.copyWith(isConfirmed: item.id == slot.id))
        .toList();
    final updatedRequest = request.copyWith(
      status: MeetingRequestStatus.confirmed,
      slots: updatedSlots,
      selectedSlotId: slot.id,
    );

    final updatedRequests = Map<String, MeetingRequest>.from(state.requestsById)
      ..[requestId] = updatedRequest;
    state = state.copyWith(requestsById: updatedRequests);
  }

  void addParticipants(
    String requestId,
    List<Participant> participants,
  ) {
    final request = state.requestsById[requestId];
    if (request == null) {
      return;
    }
    final updatedRequest = request.copyWith(participants: participants);
    final updatedRequests = Map<String, MeetingRequest>.from(state.requestsById)
      ..[requestId] = updatedRequest;
    state = state.copyWith(requestsById: updatedRequests);
  }

  void updateRequestStatus(String requestId, MeetingRequestStatus status) {
    final request = state.requestsById[requestId];
    if (request == null) {
      return;
    }
    final updatedRequest = request.copyWith(status: status);
    final updatedRequests = Map<String, MeetingRequest>.from(state.requestsById)
      ..[requestId] = updatedRequest;
    state = state.copyWith(requestsById: updatedRequests);
  }

  void _addMessage(String conversationId, Message message,
      {required String preview}) {
    final updatedMessages =
        Map<String, List<Message>>.from(state.messagesByConversation);
    final existing = updatedMessages[conversationId] ?? [];
    updatedMessages[conversationId] = [...existing, message];

    final updatedConversations = state.conversations.map((conversation) {
      if (conversation.id == conversationId) {
        return conversation.copyWith(
          lastMessagePreview: preview,
          lastMessageAt: message.timestamp,
        );
      }
      return conversation;
    }).toList();

    state = state.copyWith(
      messagesByConversation: updatedMessages,
      conversations: updatedConversations,
    );
  }
}
