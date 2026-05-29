import 'package:flutter/material.dart';

class DriverState {
  final String timestamp;
  final String input;
  final String level;
  final String message;
  final bool buzzer;
  final String driverState;
  final String sourcePath;
  final String spokenText;
  final String recommendedAction;
  final String trigger;
  final String suggestedRoute;
  final String sessionId;
  final String eventId;
  final int riskScore;

  const DriverState({
    required this.timestamp,
    required this.input,
    required this.level,
    required this.message,
    required this.buzzer,
    required this.driverState,
    required this.sourcePath,
    required this.spokenText,
    required this.recommendedAction,
    required this.trigger,
    required this.suggestedRoute,
    required this.sessionId,
    required this.eventId,
    required this.riskScore,
  });

  factory DriverState.fromJson(Map<String, dynamic> json) {
    final message = (json['message'] ?? '').toString();
    final input = (json['input'] ?? '').toString();
    final level = (json['level'] ?? 'INFO').toString();
    final spoken = (json['spoken_text'] ?? json['speech'] ?? json['tts'] ?? '').toString();
    final driverState = (json['driver_state'] ?? json['driverState'] ?? _deriveDriverState(input, message, level)).toString();
    final buzzer = json['buzzer'] == true || (json['buzzer'] ?? '').toString().toLowerCase() == 'true';
    final risk = int.tryParse('${json['risk_score'] ?? json['riskScore'] ?? _deriveRisk(level, buzzer, driverState)}') ?? 0;
    return DriverState(
      timestamp: (json['timestamp'] ?? '').toString(),
      input: input,
      level: level,
      message: message,
      buzzer: buzzer,
      driverState: driverState,
      sourcePath: (json['source_path'] ?? '').toString(),
      spokenText: spoken.isNotEmpty ? spoken : _deriveSpeech(message, level, input),
      recommendedAction: (json['recommended_action'] ?? _deriveAction(message, level, input)).toString(),
      trigger: (json['trigger'] ?? '').toString(),
      suggestedRoute: (json['suggested_route'] ?? 'N/A').toString(),
      sessionId: (json['session_id'] ?? 'unknown').toString(),
      eventId: (json['event_id'] ?? '').toString(),
      riskScore: risk.clamp(0, 100).toInt(),
    );
  }

  static String _deriveDriverState(String input, String message, String level) {
    final text = '$input $message $level'.toLowerCase();
    if (text.contains('phone') || text.contains('distract')) return 'Distracted';
    if (text.contains('drows') || text.contains('sleep') || text.contains('eyes closed') || text.contains('yawn')) return 'Drowsy';
    if (text.contains('panic') || text.contains('distress') || text.contains('calm')) return 'Distressed';
    if (text.contains('attentive') || text.contains('focused') || text.contains('normal')) return 'Focused';
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
    if (text.contains('sleep') || text.contains('drows') || text.contains('eyes closed')) return 'Stop safely, get fresh air, and rest before continuing.';
    if (text.contains('panic') || text.contains('distress') || text.contains('erratic')) return 'Slow down, breathe, and regain control before continuing.';
    if (level.toUpperCase() == 'INFO') return 'Continue driving carefully.';
    return 'Monitor the driver and be ready to intervene.';
  }

  static int _deriveRisk(String level, bool buzzer, String driverState) {
    final normalized = level.toUpperCase();
    var score = switch (normalized) {
      'CRITICAL' => 100,
      'DANGER' => 85,
      'WARNING' => 55,
      'INFO' => 15,
      _ => 25,
    };
    if (buzzer) score += 7;
    if (driverState.toLowerCase().contains('drows')) score += 10;
    if (driverState.toLowerCase().contains('distract')) score += 8;
    return score.clamp(0, 100).toInt();
  }

  String get eventKey => eventId.isNotEmpty ? eventId : '$timestamp|$level|$message|$input|$spokenText|$buzzer';

  bool get isHighRisk => riskScore >= 70 || buzzer || level.toUpperCase() == 'DANGER' || level.toUpperCase() == 'CRITICAL';

  Color get levelColor {
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
