import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/alert_item.dart';
import '../models/analytics_summary.dart';
import '../models/driver_state.dart';

class ApiService {
  final ValueNotifier<String> baseUrl = ValueNotifier<String>('http://127.0.0.1:8000');
  final ValueNotifier<DriverState?> currentState = ValueNotifier<DriverState?>(null);
  final ValueNotifier<List<AlertItem>> alerts = ValueNotifier<List<AlertItem>>(<AlertItem>[]);
  final ValueNotifier<AnalyticsSummary> analytics = ValueNotifier<AnalyticsSummary>(AnalyticsSummary.empty());
  final ValueNotifier<List<SessionSummary>> sessions = ValueNotifier<List<SessionSummary>>(<SessionSummary>[]);
  final ValueNotifier<List<ConversationTurn>> conversation = ValueNotifier<List<ConversationTurn>>(<ConversationTurn>[]);
  final ValueNotifier<Map<String, dynamic>?> schema = ValueNotifier<Map<String, dynamic>?>(null);
  final ValueNotifier<Map<String, dynamic>?> backendConfig = ValueNotifier<Map<String, dynamic>?>(null);
  final ValueNotifier<bool> isHealthy = ValueNotifier<bool>(false);
  final ValueNotifier<int> rowsLoaded = ValueNotifier<int>(0);
  final ValueNotifier<DateTime?> lastSync = ValueNotifier<DateTime?>(null);
  final ValueNotifier<int> updateCount = ValueNotifier<int>(0);
  final ValueNotifier<String> liveSpeech = ValueNotifier<String>('Waiting for live speech...');
  final ValueNotifier<String> statusMessage = ValueNotifier<String>('Connecting to backend...');
  final ValueNotifier<int> latencyMs = ValueNotifier<int>(0);

  Timer? _timer;
  bool _busy = false;
  String? _lastStateKey;

  ApiService() {
    if (kIsWeb) {
      baseUrl.value = 'http://127.0.0.1:8000';
    }
    refreshAll();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => refreshAll());
  }

  void updateBaseUrl(String next) {
    final sanitized = next.trim().replaceAll(RegExp(r'/+$'), '');
    if (sanitized.isNotEmpty) {
      baseUrl.value = sanitized;
      schema.value = null;
      backendConfig.value = null;
      currentState.value = null;
      alerts.value = <AlertItem>[];
      sessions.value = <SessionSummary>[];
      conversation.value = <ConversationTurn>[];
      refreshAll();
    }
  }

  Future<void> refreshAll() async {
    if (_busy) return;
    _busy = true;
    final stopwatch = Stopwatch()..start();
    try {
      await Future.wait([
        _fetchHealth(),
        _fetchState(),
        _fetchAlerts(),
        _fetchAnalytics(),
        _fetchSessions(),
        _fetchConversation(),
        _fetchSchema(),
        _fetchConfig(),
      ]);
      lastSync.value = DateTime.now();
      latencyMs.value = stopwatch.elapsedMilliseconds;
      statusMessage.value = isHealthy.value ? 'Live data connected' : 'Backend responded with degraded health';
    } catch (error) {
      isHealthy.value = false;
      statusMessage.value = 'Backend connection failed: $error';
    } finally {
      stopwatch.stop();
      _busy = false;
    }
  }

  Future<void> createTestWarning() async {
    try {
      final response = await http.post(
        Uri.parse('${baseUrl.value}/api/v1/events'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'level': 'WARNING',
          'message': 'Mobile manual test alert',
          'spoken_text': 'Focus on the road',
          'driver_state': 'Mobile Test',
          'trigger': 'mobile_manual_test',
          'buzzer': false,
        }),
      ).timeout(const Duration(seconds: 4));
      if (response.statusCode == 201) {
        statusMessage.value = 'Manual test alert created';
        await refreshAll();
      } else {
        statusMessage.value = 'Manual alert failed (${response.statusCode})';
      }
    } catch (error) {
      statusMessage.value = 'Manual alert failed: $error';
    }
  }

  Future<void> _fetchHealth() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/health')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        isHealthy.value = data['status'] == 'ok' || data['status'] == 'degraded';
        rowsLoaded.value = int.tryParse('${data['rows_loaded'] ?? 0}') ?? 0;
      } else {
        isHealthy.value = false;
      }
    } catch (_) {
      isHealthy.value = false;
    }
  }

  Future<void> _fetchState() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/state')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final state = DriverState.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
        currentState.value = state;
        liveSpeech.value = state.spokenText;
        if (_lastStateKey != state.eventKey) {
          _lastStateKey = state.eventKey;
          updateCount.value = updateCount.value + 1;
          _insertDerivedAlert(state);
        }
      }
    } catch (_) {}
  }

  void _insertDerivedAlert(DriverState state) {
    final item = AlertItem(
      id: state.eventKey,
      timestamp: state.timestamp,
      level: state.level,
      message: state.message,
      input: state.input,
      buzzer: state.buzzer,
      spokenText: state.spokenText,
      recommendedAction: state.recommendedAction,
      driverState: state.driverState,
      trigger: state.trigger,
      suggestedRoute: state.suggestedRoute,
      sessionId: state.sessionId,
      riskScore: state.riskScore,
      severityRank: state.level.toUpperCase() == 'DANGER' ? 3 : state.level.toUpperCase() == 'WARNING' ? 2 : 1,
    );
    final current = List<AlertItem>.from(alerts.value);
    current.removeWhere((e) => e.id == item.id);
    current.insert(0, item);
    if (current.length > 100) {
      current.removeRange(100, current.length);
    }
    alerts.value = current;
  }

  Future<void> _fetchAlerts() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/api/v1/alerts?limit=100')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as List<dynamic>;
        final incoming = data.map((e) => AlertItem.fromJson(e as Map<String, dynamic>)).toList();
        final merged = <String, AlertItem>{
          for (final item in alerts.value) item.id: item,
          for (final item in incoming) item.id: item,
        };
        final mergedList = merged.values.toList()
          ..sort((a, b) {
            final severity = b.severityRank.compareTo(a.severityRank);
            if (severity != 0) return severity;
            return b.timestamp.compareTo(a.timestamp);
          });
        alerts.value = mergedList.take(100).toList();
      }
    } catch (_) {}
  }

  Future<void> _fetchAnalytics() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/api/v1/analytics?limit=100')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        analytics.value = AnalyticsSummary.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      }
    } catch (_) {}
  }

  Future<void> _fetchSessions() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/api/v1/sessions')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as List<dynamic>;
        sessions.value = data.map((item) => SessionSummary.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
  }

  Future<void> _fetchConversation() async {
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/api/v1/conversation?limit=30')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as List<dynamic>;
        conversation.value = data.map((item) => ConversationTurn.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
  }

  Future<void> _fetchSchema() async {
    if (schema.value != null) return;
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/schema')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        schema.value = jsonDecode(response.body) as Map<String, dynamic>;
      }
    } catch (_) {}
  }

  Future<void> _fetchConfig() async {
    if (backendConfig.value != null) return;
    try {
      final response = await http.get(Uri.parse('${baseUrl.value}/api/v1/config')).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        backendConfig.value = jsonDecode(response.body) as Map<String, dynamic>;
      }
    } catch (_) {}
  }

  void dispose() {
    _timer?.cancel();
  }
}
