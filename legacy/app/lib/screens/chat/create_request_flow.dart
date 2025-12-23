import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/meeting_request.dart';
import '../../models/participant.dart';
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
  String _timezone = 'Pacific Time';
  DateTime? _startDate;
  DateTime? _endDate;
  final Set<String> _days = {'Mon', 'Wed', 'Thu'};
  final Set<String> _timesOfDay = {'Morning', 'Afternoon'};
  late List<Participant> _participants;

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
              email: '${entry.value.toLowerCase().replaceAll(' ', '.')}@mail.co',
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
                    label: _currentStep == 2 ? 'Create Request' : 'Continue',
                    onPressed: _currentStep == 2 ? _submit : details.onStepContinue,
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
            content: _detailsStep(context),
          ),
          Step(
            title: const Text('Participants'),
            isActive: _currentStep >= 1,
            content: _participantsStep(context),
          ),
          Step(
            title: const Text('Review'),
            isActive: _currentStep >= 2,
            content: _reviewStep(context),
          ),
        ],
      ),
    );
  }

  Widget _detailsStep(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InputField(
          label: 'Title',
          hint: 'Monthly planning sync',
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
          ],
          onChanged: (value) {
            if (value == null) return;
            setState(() => _duration = value);
          },
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          value: _timezone,
          decoration: const InputDecoration(labelText: 'Timezone'),
          items: const [
            DropdownMenuItem(value: 'Pacific Time', child: Text('Pacific Time')),
            DropdownMenuItem(value: 'Eastern Time', child: Text('Eastern Time')),
            DropdownMenuItem(value: 'UTC', child: Text('UTC')),
          ],
          onChanged: (value) {
            if (value == null) return;
            setState(() => _timezone = value);
          },
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: InputField(
                label: 'Start date',
                hint: _startDate == null
                    ? 'Select'
                    : formatMonthDayYear(_startDate!),
                readOnly: true,
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 60)),
                  );
                  if (picked == null) return;
                  setState(() => _startDate = picked);
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: InputField(
                label: 'End date',
                hint:
                    _endDate == null ? 'Select' : formatMonthDayYear(_endDate!),
                readOnly: true,
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 90)),
                  );
                  if (picked == null) return;
                  setState(() => _endDate = picked);
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        const Text('Days of week'),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
              .map((day) => FilterChip(
                    label: Text(day),
                    selected: _days.contains(day),
                    onSelected: (selected) {
                      setState(() {
                        if (selected) {
                          _days.add(day);
                        } else {
                          _days.remove(day);
                        }
                      });
                    },
                  ))
              .toList(),
        ),
        const SizedBox(height: 16),
        const Text('Time of day'),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: ['Morning', 'Afternoon', 'Evening']
              .map((slot) => FilterChip(
                    label: Text(slot),
                    selected: _timesOfDay.contains(slot),
                    onSelected: (selected) {
                      setState(() {
                        if (selected) {
                          _timesOfDay.add(slot);
                        } else {
                          _timesOfDay.remove(slot);
                        }
                      });
                    },
                  ))
              .toList(),
        ),
        const SizedBox(height: 16),
        InputField(
          label: 'Meeting type (optional)',
          hint: 'Video call',
          controller: _meetingTypeController,
        ),
        const SizedBox(height: 16),
        InputField(
          label: 'Notes (optional)',
          hint: 'Agenda or context',
          controller: _notesController,
          maxLines: 3,
        ),
      ],
    );
  }

  Widget _participantsStep(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _participants
              .map((participant) => Chip(
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
                  ))
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
          onPressed: () {
            final email = _emailController.text.trim();
            if (email.isEmpty) return;
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
          },
          icon: const Icon(Icons.add),
          label: const Text('Add'),
        ),
      ],
    );
  }

  Widget _reviewStep(BuildContext context) {
    final title = _titleController.text.isEmpty
        ? 'Untitled request'
        : _titleController.text.trim();
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
          'Date range: ${_startDate == null ? 'Not set' : formatMonthDayYear(_startDate!)} - ${_endDate == null ? 'Not set' : formatMonthDayYear(_endDate!)}',
        ),
        const SizedBox(height: 8),
        Text('Days: ${_days.join(', ')}'),
        const SizedBox(height: 8),
        Text('Times: ${_timesOfDay.join(', ')}'),
        const SizedBox(height: 16),
        Text(
          'Participants (${_participants.length})',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: 6),
        ..._participants.map((participant) => Text(participant.email)),
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
    if (_currentStep < 2) {
      setState(() => _currentStep += 1);
    }
  }

  void _prevStep() {
    if (_currentStep > 0) {
      setState(() => _currentStep -= 1);
    }
  }

  void _submit() {
    final now = DateTime.now();
    final title = _titleController.text.trim().isEmpty
        ? 'New request'
        : _titleController.text.trim();
    final request = MeetingRequest(
      id: 'req_${now.millisecondsSinceEpoch}',
      title: title,
      durationMinutes: _duration,
      timezone: _timezone,
      dateRangeStart: _startDate ?? now.add(const Duration(days: 2)),
      dateRangeEnd: _endDate ?? now.add(const Duration(days: 7)),
      daysOfWeek: _days.toList(),
      timesOfDay: _timesOfDay.toList(),
      participants: _participants,
      status: MeetingRequestStatus.pending,
      slots: const [],
      meetingType:
          _meetingTypeController.text.trim().isEmpty ? null : _meetingTypeController.text.trim(),
      notes: _notesController.text.trim().isEmpty ? null : _notesController.text.trim(),
    );
    ref
        .read(appStateProvider.notifier)
        .addRequestMessage(widget.conversationId, request);
    if (!mounted) return;
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Request created.')),
    );
  }
}
