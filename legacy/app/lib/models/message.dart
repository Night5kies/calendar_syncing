enum MessageType {
  text,
  requestCard,
}

class Message {
  const Message({
    required this.id,
    required this.conversationId,
    required this.senderName,
    required this.isMe,
    required this.timestamp,
    required this.type,
    this.text,
    this.requestId,
  });

  final String id;
  final String conversationId;
  final String senderName;
  final bool isMe;
  final DateTime timestamp;
  final MessageType type;
  final String? text;
  final String? requestId;
}
