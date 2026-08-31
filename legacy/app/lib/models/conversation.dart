class Conversation {
  const Conversation({
    required this.id,
    required this.name,
    required this.avatarInitials,
    required this.lastMessagePreview,
    required this.lastMessageAt,
    required this.unreadCount,
    required this.isGroup,
    required this.isFavorite,
    required this.members,
  });

  final String id;
  final String name;
  final String avatarInitials;
  final String lastMessagePreview;
  final DateTime lastMessageAt;
  final int unreadCount;
  final bool isGroup;
  final bool isFavorite;
  final List<String> members;

  Conversation copyWith({
    String? lastMessagePreview,
    DateTime? lastMessageAt,
    int? unreadCount,
    bool? isFavorite,
    List<String>? members,
  }) {
    return Conversation(
      id: id,
      name: name,
      avatarInitials: avatarInitials,
      lastMessagePreview: lastMessagePreview ?? this.lastMessagePreview,
      lastMessageAt: lastMessageAt ?? this.lastMessageAt,
      unreadCount: unreadCount ?? this.unreadCount,
      isGroup: isGroup,
      isFavorite: isFavorite ?? this.isFavorite,
      members: members ?? this.members,
    );
  }
}
