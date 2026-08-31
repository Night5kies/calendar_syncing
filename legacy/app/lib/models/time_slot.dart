class TimeSlot {
  const TimeSlot({
    required this.id,
    required this.start,
    required this.end,
    required this.score,
    required this.explanation,
    this.isConfirmed = false,
  });

  final String id;
  final DateTime start;
  final DateTime end;
  final int score;
  final String explanation;
  final bool isConfirmed;

  TimeSlot copyWith({bool? isConfirmed}) {
    return TimeSlot(
      id: id,
      start: start,
      end: end,
      score: score,
      explanation: explanation,
      isConfirmed: isConfirmed ?? this.isConfirmed,
    );
  }
}
