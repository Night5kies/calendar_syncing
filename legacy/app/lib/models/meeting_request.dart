import 'participant.dart';
import 'time_slot.dart';

enum MeetingRequestStatus {
  draft,
  pending,
  optionsGenerated,
  confirmed,
}

class MeetingRequest {
  const MeetingRequest({
    required this.id,
    required this.title,
    required this.durationMinutes,
    required this.timezone,
    required this.dateRangeStart,
    required this.dateRangeEnd,
    required this.daysOfWeek,
    required this.timesOfDay,
    required this.participants,
    required this.status,
    required this.slots,
    this.meetingType,
    this.notes,
    this.selectedSlotId,
  });

  final String id;
  final String title;
  final int durationMinutes;
  final String timezone;
  final DateTime dateRangeStart;
  final DateTime dateRangeEnd;
  final List<String> daysOfWeek;
  final List<String> timesOfDay;
  final List<Participant> participants;
  final MeetingRequestStatus status;
  final List<TimeSlot> slots;
  final String? meetingType;
  final String? notes;
  final String? selectedSlotId;

  MeetingRequest copyWith({
    String? title,
    int? durationMinutes,
    String? timezone,
    DateTime? dateRangeStart,
    DateTime? dateRangeEnd,
    List<String>? daysOfWeek,
    List<String>? timesOfDay,
    List<Participant>? participants,
    MeetingRequestStatus? status,
    List<TimeSlot>? slots,
    String? meetingType,
    String? notes,
    String? selectedSlotId,
  }) {
    return MeetingRequest(
      id: id,
      title: title ?? this.title,
      durationMinutes: durationMinutes ?? this.durationMinutes,
      timezone: timezone ?? this.timezone,
      dateRangeStart: dateRangeStart ?? this.dateRangeStart,
      dateRangeEnd: dateRangeEnd ?? this.dateRangeEnd,
      daysOfWeek: daysOfWeek ?? this.daysOfWeek,
      timesOfDay: timesOfDay ?? this.timesOfDay,
      participants: participants ?? this.participants,
      status: status ?? this.status,
      slots: slots ?? this.slots,
      meetingType: meetingType ?? this.meetingType,
      notes: notes ?? this.notes,
      selectedSlotId: selectedSlotId ?? this.selectedSlotId,
    );
  }
}
