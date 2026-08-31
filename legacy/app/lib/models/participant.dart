class Participant {
  const Participant({
    required this.id,
    required this.name,
    required this.email,
    this.isMe = false,
  });

  final String id;
  final String name;
  final String email;
  final bool isMe;
}
