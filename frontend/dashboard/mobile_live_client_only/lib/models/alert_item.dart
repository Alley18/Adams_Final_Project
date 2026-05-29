import 'package:flutter/material.dart';

class AlertItem {
  final String id;
  final String timestamp;
  final String level;
  final String message;
  final String input;
  final bool buzzer;
  final String spokenText;
  final String recommendedAction;
  final String driverState;
  final String trigger;
  final String suggestedRoute;
  final String sessionId;
  final int riskScore;
  final int severityRank;

  const AlertItem({
    required this.id,
    required this.timestamp,
    required this.level,
    required this.message,
    required this.input,
    required this.buzzer,
    required this.spokenText,
    required this.recommendedAction,
    required this.driverState,
    required this.trigger,
    required this.suggestedRoute,
    required this.sessionId,
    required this.riskScore,
    required this.severityRank,
  });

  factory AlertItem.fromJson(Map<String, dynamic> json) {
    final message = (json['message'] ?? '').toString();
    final input = (json['input'] ?? '').toString();
    final level = (json['level'] ?? 'INFO').toString();
    final spokenText = (json['spoken_text'] ?? json['speech'] ?? json['tts'] ?? '').toString();
    final buzzer = json['buzzer'] == true || (json['buzzer'] ?? '').toString().toLowerCase() == 'true';
    final driverState = (json['driver_state'] ?? json['driverState'] ?? _deriveDriverState(input, message, level)).toString();
    final riskScore = int.tryParse('${json['risk_score'] ?? 0}') ?? _deriveRisk(level, buzzer, driverState);
    return AlertItem(
      id: (json['event_id'] ?? json['id'] ?? '${json['timestamp'] ?? ''}|$message|$input').toString(),
      timestamp: (json['timestamp'] ?? '').toString(),
      level: level,
      message: message,
      input: input,
      buzzer: buzzer,
      spokenText: spokenText.isNotEmpty ? spokenText : _deriveSpeech(message, level, input),
      recommendedAction: (json['recommended_action'] ?? _deriveAction(message, level, input)).toString(),
      driverState: driverState,
      trigger: (json['trigger'] ?? '').toString(),
      suggestedRoute: (json['suggested_route'] ?? 'N/A').toString(),
      sessionId: (json['session_id'] ?? 'unknown').toString(),
      riskScore: riskScore.clamp(0, 100).toInt(),
      severityRank: int.tryParse('${json['severity_rank'] ?? _severityRank(level)}') ?? _severityRank(level),
    );
  }

  static String _deriveDriverState(String input, String message, String level) {
    final text = '$message $input $level'.toLowerCase();
    if (text.contains('phone') || text.contains('distract')) return 'Distracted';
    if (text.contains('sleep') || text.contains('drows') || text.contains('eyes closed')) return 'Drowsy';
    if (text.contains('panic') || text.contains('distress') || text.contains('erratic')) return 'Distressed';
    return 'Monitoring';
  }

  static String _deriveSpeech(String message, String level, String input) {
    final text = '$message $input'.toLowerCase();
    if (text.contains('sleep') || text.contains('drows') || text.contains('eyes closed')) return 'Wake up';
    if (text.contains('phone') || text.contains('distract')) return 'Focus on the road';
    if (text.contains('panic') || text.contains('distress') || text.contains('erratic')) return 'Stay calm';
    if (level.toUpperCase() == 'INFO') return 'You are safe';
    return message.isNotEmpty ? message : 'Driver monitoring active';
  }

  static String _deriveAction(String message, String level, String input) {
    final text = '$message $input'.toLowerCase();
    if (text.contains('phone')) return 'Keep both eyes on the road and put the phone away.';
    if (text.contains('sleep') || text.contains('drows') || text.contains('eyes closed')) return 'Take a break and do not continue while sleepy.';
    if (text.contains('panic') || text.contains('distress') || text.contains('erratic')) return 'Reduce speed, stay calm, and stabilize the vehicle.';
    if (level.toUpperCase() == 'INFO') return 'Continue monitoring normally.';
    return 'Follow the assistant guidance immediately.';
  }

  static int _severityRank(String level) {
    switch (level.toUpperCase()) {
      case 'CRITICAL':
        return 4;
      case 'DANGER':
        return 3;
      case 'WARNING':
        return 2;
      case 'INFO':
        return 1;
      default:
        return 0;
    }
  }

  static int _deriveRisk(String level, bool buzzer, String driverState) {
    var risk = switch (level.toUpperCase()) {
      'CRITICAL' => 100,
      'DANGER' => 85,
      'WARNING' => 55,
      'INFO' => 15,
      _ => 25,
    };
    if (buzzer) risk += 7;
    if (driverState.toLowerCase().contains('drows')) risk += 10;
    if (driverState.toLowerCase().contains('distract')) risk += 8;
    return risk.clamp(0, 100).toInt();
  }

  bool get isHighRisk => riskScore >= 70 || buzzer || level.toUpperCase() == 'DANGER' || level.toUpperCase() == 'CRITICAL';

  Color get color {
    switch (level.toUpperCase()) {
      case 'CRITICAL':
      case 'DANGER':
        return Colors.redAccent;
      case 'WARNING':
        return Colors.orangeAccent;
      case 'INFO':
        return Colors.greenAccent;
      default:
        return Colors.grey;
    }
  }
}
