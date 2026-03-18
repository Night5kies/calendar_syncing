import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/meeting_request.dart';
import '../../models/participant.dart';
import '../../models/time_slot.dart';
import '../../state/providers.dart';
import '../../utils/date_formatters.dart';
import '../../widgets/input_field.dart';
import '../../widgets/primary_button.dart';

class CreateRequestFlow extends ConsumerStatefulWidget {
  const CreateRequestFlow({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<CreateRequestFlow> createState() => _CreateRequestFlowState();
}

class _CreateRequestFlowState extends ConsumerState<CreateRequestFlow> {
  int _currentStep = 0;
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _notesController = TextEditingController();
  final TextEditingController _meetingTypeController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();

  int _duration = 30;
  String _timezone = 'Eastern Time';
  late List<Participant> _participants;
  final List<TimeSlot> _slots = [];

  @override
  void initState() {
    super.initState();
    final conversation = ref
        .read(appStateProvider)
        .conversations
        .firstWhere((item) => item.id == widget.conversationId);
    _participants = [
      const Participant(
        id: 'me',
        name: 'You',
        email: 'you@sync.app',
        isMe: true,
      ),
      ...conversation.members
          .asMap()
          .entries
          .map((entry) => Participant(
                id: 'member_${entry.key}',
                name: entry.value,
                email:
                    '${entry.value.toLowerCase().replaceAll(' ', '.')}@mail.co',
              ))
          .toList(),
    ];
  }

  @override
  void dispose() {
    _titleController.dispose();
    _notesController.dispose();
    _meetingTypeController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create request')),
      body: Stepper(
        currentStep: _currentStep,
        onStepContinue: _nextStep,
        onStepCancel: _prevStep,
        controlsBuilder: (context, details) {
          return Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Row(
              children: [
                Expanded(
                  child: PrimaryButton(
                    label: _currentStep == 3 ? 'Create Request' : 'Continue',
                    onPressed:
                        _currentStep == 3 ? _submit : details.onStepContinue,
                  ),
                ),
                if (_currentStep > 0) ...[
                  const SizedBox(width: 12),
                  TextButton(
                    onPressed: details.onStepCancel,
                    child: const Text('Back'),
                  ),
                ],
              ],
            ),
          );
        },
        steps: [
          Step(
            title: const Text('Details'),
            isActive: _currentStep >= 0,
            content: _detailsStep(),
          ),
          Step(
            title: const Text('Participants'),
            isActive: _currentStep >= 1,
            content: _participantsStep(),
          ),
          Step(
            title: const Text('Time options'),
            isActive: _currentStep >= 2,
            content: _timeOptionsStep(context),
          ),
          Step(
            title: const Text('Review'),
            isActive: _currentStep >= 3,
            content: _reviewStep(context),
          ),
        ],
      ),
    );
  }

  Widget _detailsStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InputField(
          label: 'Title',
          hint: 'Dinner next week',
          controller: _titleController,
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<int>(
          value: _duration,
          decoration: const InputDecoration(labelText: 'Duration'),
          items: const [
            DropdownMenuItem(value: 15, child: Text('15 minutes')),
            DropdownMenuItem(value: 30, child: Text('30 minutes')),
            DropdownMenuItem(value: 45, child: Text('45 minutes')),
            DropdownMenuItem(value: 60, child: Text('60 minutes')),
            DropdownMenuItem(value: 90, child: Text('90 minutes')),
          ],
          onChanged: (value) {
            if (value == null) {
              return;
            }
            setState(() => _duration = value);
          },
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          value: _timezone,
          decoration: const InputDecoration(labelText: 'Timezone'),
          items: const [
            DropdownMenuItem(value: 'Eastern Time', child: Text('Eastern Time')),
            DropdownMenuItem(value: 'Pacific Time', child: Text('Pacific Time')),
            DropdownMenuItem(value: 'UTC', child: Text('UTC')),
          ],
          onChanged: (value) {
            if (value == null) {
              return;
            }
            setState(() => _timezone = value);
          },
        ),
        const SizedBox(height: 16),
        InputField(
          label: 'Meeting type (optional)',
          hint: 'Coffee, lunch, study session',
          controller: _meetingTypeController,
        ),
        const SizedBox(height: 16),
        InputField(
          label: 'Notes (optional)',
          hint: 'Anything guests should know',
          controller: _notesController,
          maxLines: 3,
        ),
      ],
    );
  }

  Widget _participantsStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _participants
              .map(
                (participant) => Chip(
                  label: Text(participant.email),
                  onDeleted: participant.isMe
                      ? null
                      : () {
                          setState(() {
                            _participants = _participants
                                .where((item) => item.id != participant.id)
                                .toList();
                          });
                        },
                ),
              )
              .toList(),
        ),
        const SizedBox(height: 16),
        InputField(
          label: 'Add participant',
          hint: 'email@company.com',
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: _addParticipant,
          icon: const Icon(Icons.add),
          label: const Text('Add'),
        ),
      ],
    );
  }

  Widget _timeOptionsStep(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Add 3 to 5 manual options. This keeps the MVP faster than a group-text back-and-forth.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 12),
        if (_slots.isEmpty)
          Text(
            'No time options yet.',
            style: Theme.of(context).textTheme.bodyMedium,
          )
        else
          Column(
            children: _slots
                .asMap()
                .entries
                .map(
                  (entry) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      '${formatMonthDay(entry.value.start)} · ${formatTime(context, entry.value.start)} - ${formatTime(context, entry.value.end)}',
                    ),
                    subtitle: Text('Option ${entry.key + 1}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () {
                        setState(() => _slots.removeAt(entry.key));
                      },
                    ),
                  ),
                )
                .toList(),
          ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: _slots.length >= 5 ? null : () => _addTimeOption(context),
          icon: const Icon(Icons.add),
          label: const Text('Add time option'),
        ),
      ],
    );
  }

  Widget _reviewStep(BuildContext context) {
    final title =
        _titleController.text.trim().isEmpty ? 'Untitled request' : _titleController.text.trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(title),
          subtitle: Text('$_duration minutes · $_timezone'),
        ),
        const SizedBox(height: 8),
        Text(
          'Participants (${_participants.length})',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: 6),
        ..._participants.map((participant) => Text(participant.email)),
        const SizedBox(height: 16),
        Text(
          'Time options (${_slots.length})',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: 6),
        if (_slots.isEmpty)
          const Text('No time options added.')
        else
          ..._slots.map(
            (slot) => Text(
              '${formatMonthDay(slot.start)} · ${formatTime(context, slot.start)} - ${formatTime(context, slot.end)}',
            ),
          ),
        if (_meetingTypeController.text.trim().isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Type: ${_meetingTypeController.text.trim()}'),
        ],
        if (_notesController.text.trim().isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Notes: ${_notesController.text.trim()}'),
        ],
      ],
    );
  }

  void _nextStep() {
    if (_currentStep == 1 && _participants.isEmpty) {
      _showError('Add at least one participant.');
      return;
    }
    if (_currentStep == 2 && _slots.length < 3) {
      _showError('Add at least 3 time options for the MVP poll.');
      return;
    }
    if (_currentStep < 3) {
      setState(() => _currentStep += 1);
    }
  }

  void _prevStep() {
    if (_currentStep > 0) {
      setState(() => _currentStep -= 1);
    }
  }

  void _addParticipant() {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      return;
    }
    setState(() {
      _participants = [
        ..._participants,
        Participant(
          id: 'extra_${DateTime.now().millisecondsSinceEpoch}',
          name: email.split('@').first,
          email: email,
        ),
      ];
      _emailController.clear();
    });
  }

  Future<void> _addTimeOption(BuildContext context) async {
    final now = DateTime.now();
    final pickedDate = await showDatePicker(
      context: context,
      firstDate: now,
      lastDate: now.add(const Duration(days: 120)),
      initialDate: now.add(const Duration(days: 2)),
    );
    if (pickedDate == null || !mounted) {
      return;
    }

    final pickedTime = await showTimePicker(
      context: context,
      initialTime: const TimeOfDay(hour: 18, minute: 0),
    );
    if (pickedTime == null) {
      return;
    }

    final start = DateTime(
      pickedDate.year,
      pickedDate.month,
      pickedDate.day,
      pickedTime.hour,
      pickedTime.minute,
    );
    final end = start.add(Duration(minutes: _duration));

    setState(() {
      _slots.add(
        TimeSlot(
          id: 'slot_${start.millisecondsSinceEpoch}',
          start: start,
          end: end,
          score: 0,
          explanation: 'Manual option',
        ),
      );
      _slots.sort((a, b) => a.start.compareTo(b.start));
    });
  }

  void _submit() {
    if (_slots.length < 3) {
      _showError('Add at least 3 time options before creating the request.');
      return;
    }

    final now = DateTime.now();
    final title =
        _titleController.text.trim().isEmpty ? 'New request' : _titleController.text.trim();
    final request = MeetingRequest(
      id: 'req_${now.millisecondsSinceEpoch}',
      title: title,
      durationMinutes: _duration,
      timezone: _timezone,
      dateRangeStart: _slots.first.start,
      dateRangeEnd: _slots.last.start,
      daysOfWeek: const [],
      timesOfDay: const [],
      participants: _participants,
      status: MeetingRequestStatus.pending,
      slots: List<TimeSlot>.from(_slots),
      meetingType: _meetingTypeController.text.trim().isEmpty
          ? null
          : _meetingTypeController.text.trim(),
      notes: _notesController.text.trim().isEmpty
          ? null
          : _notesController.text.trim(),
    );
    ref.read(appStateProvider.notifier).addRequestMessage(
          widget.conversationId,
          request,
        );
    if (!mounted) {
      return;
    }
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Request created with manual time options.')),
    );
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}
