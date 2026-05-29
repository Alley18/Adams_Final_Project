class AnalyticsSummary {
  final int totalEvents;
  final int dangerCount;
  final int warningCount;
  final int infoCount;
  final int buzzerActivations;
  final int distractedCount;
  final int drowsyCount;
  final int latestRiskScore;
  final int highestRiskScore;
  final String currentSessionId;
  final String firstEvent;
  final String lastEvent;
  final Map<String, int> levelBreakdown;
  final Map<String, int> driverStateBreakdown;
  final List<Map<String, dynamic>> recentTimeline;
  final List<String> safetyRecommendations;

  const AnalyticsSummary({
    required this.totalEvents,
    required this.dangerCount,
    required this.warningCount,
    required this.infoCount,
    required this.buzzerActivations,
    required this.distractedCount,
    required this.drowsyCount,
    required this.latestRiskScore,
    required this.highestRiskScore,
    required this.currentSessionId,
    required this.firstEvent,
    required this.lastEvent,
    required this.levelBreakdown,
    required this.driverStateBreakdown,
    required this.recentTimeline,
    required this.safetyRecommendations,
  });

  factory AnalyticsSummary.empty() => const AnalyticsSummary(
        totalEvents: 0,
        dangerCount: 0,
        warningCount: 0,
        infoCount: 0,
        buzzerActivations: 0,
        distractedCount: 0,
        drowsyCount: 0,
        latestRiskScore: 0,
        highestRiskScore: 0,
        currentSessionId: 'unknown',
        firstEvent: 'N/A',
        lastEvent: 'N/A',
        levelBreakdown: {},
        driverStateBreakdown: {},
        recentTimeline: [],
        safetyRecommendations: [],
      );

  factory AnalyticsSummary.fromJson(Map<String, dynamic> json) {
    return AnalyticsSummary(
      totalEvents: _toInt(json['total_events']),
      dangerCount: _toInt(json['danger_count']),
      warningCount: _toInt(json['warning_count']),
      infoCount: _toInt(json['info_count']),
      buzzerActivations: _toInt(json['buzzer_activations']),
      distractedCount: _toInt(json['distracted_count']),
      drowsyCount: _toInt(json['drowsy_count']),
      latestRiskScore: _toInt(json['latest_risk_score']),
      highestRiskScore: _toInt(json['highest_risk_score']),
      currentSessionId: (json['current_session_id'] ?? 'unknown').toString(),
      firstEvent: (json['first_event'] ?? 'N/A').toString(),
      lastEvent: (json['last_event'] ?? 'N/A').toString(),
      levelBreakdown: _stringIntMap(json['level_breakdown']),
      driverStateBreakdown: _stringIntMap(json['driver_state_breakdown']),
      recentTimeline: (json['recent_timeline'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .toList(),
      safetyRecommendations: (json['safety_recommendations'] as List<dynamic>? ?? <dynamic>[])
          .map((item) => item.toString())
          .toList(),
    );
  }

  static int _toInt(dynamic value) => int.tryParse('${value ?? 0}') ?? 0;

  static Map<String, int> _stringIntMap(dynamic value) {
    if (value is! Map) return <String, int>{};
    return value.map((key, item) => MapEntry(key.toString(), _toInt(item)));
  }
}

class SessionSummary {
  final String sessionId;
  final int events;
  final int dangerCount;
  final int warningCount;
  final int buzzerActivations;
  final int highestRiskScore;
  final String firstEvent;
  final String lastEvent;

  const SessionSummary({
    required this.sessionId,
    required this.events,
    required this.dangerCount,
    required this.warningCount,
    required this.buzzerActivations,
    required this.highestRiskScore,
    required this.firstEvent,
    required this.lastEvent,
  });

  factory SessionSummary.fromJson(Map<String, dynamic> json) => SessionSummary(
        sessionId: (json['session_id'] ?? 'unknown').toString(),
        events: AnalyticsSummary._toInt(json['events']),
        dangerCount: AnalyticsSummary._toInt(json['danger_count']),
        warningCount: AnalyticsSummary._toInt(json['warning_count']),
        buzzerActivations: AnalyticsSummary._toInt(json['buzzer_activations']),
        highestRiskScore: AnalyticsSummary._toInt(json['highest_risk_score']),
        firstEvent: (json['first_event'] ?? 'N/A').toString(),
        lastEvent: (json['last_event'] ?? 'N/A').toString(),
      );
}

class ConversationTurn {
  final String sessionId;
  final String timestamp;
  final String role;
  final String text;
  final String driverState;

  const ConversationTurn({
    required this.sessionId,
    required this.timestamp,
    required this.role,
    required this.text,
    required this.driverState,
  });

  factory ConversationTurn.fromJson(Map<String, dynamic> json) => ConversationTurn(
        sessionId: (json['session_id'] ?? 'unknown').toString(),
        timestamp: (json['timestamp'] ?? '').toString(),
        role: (json['role'] ?? '').toString(),
        text: (json['text'] ?? '').toString(),
        driverState: (json['driver_state'] ?? '').toString(),
      );
}
