import '../models/conversation.dart';
import '../models/meeting_request.dart';
import '../models/message.dart';

class AppState {
  const AppState({
    required this.conversations,
    required this.messagesByConversation,
    required this.requestsById,
    required this.generatingRequests,
  });

  final List<Conversation> conversations;
  final Map<String, List<Message>> messagesByConversation;
  final Map<String, MeetingRequest> requestsById;
  final Set<String> generatingRequests;

  AppState copyWith({
    List<Conversation>? conversations,
    Map<String, List<Message>>? messagesByConversation,
    Map<String, MeetingRequest>? requestsById,
    Set<String>? generatingRequests,
  }) {
    return AppState(
      conversations: conversations ?? this.conversations,
      messagesByConversation:
          messagesByConversation ?? this.messagesByConversation,
      requestsById: requestsById ?? this.requestsById,
      generatingRequests: generatingRequests ?? this.generatingRequests,
    );
  }
}
