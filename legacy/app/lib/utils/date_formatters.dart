import 'package:flutter/material.dart';

String formatTime(BuildContext context, DateTime time) {
  return TimeOfDay.fromDateTime(time).format(context);
}

String formatMonthDay(DateTime date) {
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec'
  ];
  return '${months[date.month - 1]} ${date.day}';
}

String formatMonthDayYear(DateTime date) {
  return '${formatMonthDay(date)}, ${date.year}';
}

String formatChatTimestamp(DateTime time) {
  final now = DateTime.now();
  final difference = now.difference(time);
  if (difference.inMinutes < 60) {
    return '${difference.inMinutes}m';
  }
  if (difference.inHours < 24) {
    return '${difference.inHours}h';
  }
  if (difference.inDays < 7) {
    return '${difference.inDays}d';
  }
  return formatMonthDay(time);
}
