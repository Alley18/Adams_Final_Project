import 'package:flutter/material.dart';

import 'models/alert_item.dart';
import 'models/analytics_summary.dart';
import 'models/driver_state.dart';
import 'services/api_service.dart';
import 'widgets/alert_card.dart';
import 'widgets/info_tile.dart';
import 'widgets/status_chip.dart';

class AdamsLiveApp extends StatelessWidget {
  const AdamsLiveApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'ADAMS Live Mobile',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF08111F),
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF38BDF8), brightness: Brightness.dark),
        useMaterial3: true,
        cardTheme: CardThemeData(
          color: const Color(0xFF111827),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
        ),
      ),
      home: const LiveShell(),
    );
  }
}

class LiveShell extends StatefulWidget {
  const LiveShell({super.key});

  @override
  State<LiveShell> createState() => _LiveShellState();
}

class _LiveShellState extends State<LiveShell> {
  int _index = 0;
  final ApiService _api = ApiService();

  @override
  void dispose() {
    _api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      CommandCenterScreen(api: _api),
      MonitoringScreen(api: _api),
      AnalyticsScreen(api: _api),
      AlertsScreen(api: _api),
      TripsScreen(api: _api),
      SystemScreen(api: _api),
    ];

    final destinations = const [
      NavigationDestination(icon: Icon(Icons.space_dashboard_rounded), label: 'Center'),
      NavigationDestination(icon: Icon(Icons.visibility_rounded), label: 'Monitor'),
      NavigationDestination(icon: Icon(Icons.insights_rounded), label: 'Analytics'),
      NavigationDestination(icon: Icon(Icons.warning_amber_rounded), label: 'Alerts'),
      NavigationDestination(icon: Icon(Icons.route_rounded), label: 'Trips'),
      NavigationDestination(icon: Icon(Icons.settings_ethernet_rounded), label: 'System'),
    ];

    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF0F172A),
        title: const Text('ADAMS AI Driver Command'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(64),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: ValueListenableBuilder<String>(
              valueListenable: _api.liveSpeech,
              builder: (_, speech, __) => _LiveSpeechBanner(api: _api, speech: speech),
            ),
          ),
        ),
        actions: [
          IconButton(onPressed: _api.refreshAll, icon: const Icon(Icons.refresh_rounded), tooltip: 'Refresh now'),
          IconButton(onPressed: _showBackendDialog, icon: const Icon(Icons.link_rounded), tooltip: 'Backend URL'),
          const SizedBox(width: 8),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 900) {
            return Row(
              children: [
                NavigationRail(
                  selectedIndex: _index,
                  onDestinationSelected: (value) => setState(() => _index = value),
                  labelType: NavigationRailLabelType.all,
                  destinations: const [
                    NavigationRailDestination(icon: Icon(Icons.space_dashboard_rounded), label: Text('Center')),
                    NavigationRailDestination(icon: Icon(Icons.visibility_rounded), label: Text('Monitor')),
                    NavigationRailDestination(icon: Icon(Icons.insights_rounded), label: Text('Analytics')),
                    NavigationRailDestination(icon: Icon(Icons.warning_amber_rounded), label: Text('Alerts')),
                    NavigationRailDestination(icon: Icon(Icons.route_rounded), label: Text('Trips')),
                    NavigationRailDestination(icon: Icon(Icons.settings_ethernet_rounded), label: Text('System')),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: screens[_index]),
              ],
            );
          }
          return screens[_index];
        },
      ),
      bottomNavigationBar: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 900) return const SizedBox.shrink();
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (value) => setState(() => _index = value),
            destinations: destinations,
          );
        },
      ),
      floatingActionButton: ValueListenableBuilder<DriverState?>(
        valueListenable: _api.currentState,
        builder: (_, state, __) {
          if (state == null || !state.isHighRisk) return const SizedBox.shrink();
          return FloatingActionButton.extended(
            backgroundColor: Colors.redAccent,
            onPressed: () => setState(() => _index = 1),
            icon: const Icon(Icons.emergency_rounded),
            label: const Text('High Risk'),
          );
        },
      ),
    );
  }

  Future<void> _showBackendDialog() async {
    final controller = TextEditingController(text: _api.baseUrl.value);
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Backend URL'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            hintText: 'http://127.0.0.1:8000',
            labelText: 'Base URL',
            helperText: 'Use your computer or Raspberry Pi IP on real phones.',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              _api.updateBaseUrl(controller.text);
              Navigator.pop(context);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}

class _LiveSpeechBanner extends StatelessWidget {
  final ApiService api;
  final String speech;
  const _LiveSpeechBanner({required this.api, required this.speech});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [Colors.blueAccent.withOpacity(0.25), Colors.cyanAccent.withOpacity(0.08)]),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.blueAccent.withOpacity(0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.graphic_eq_rounded, color: Colors.lightBlueAccent),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              speech,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
          ValueListenableBuilder<bool>(
            valueListenable: api.isHealthy,
            builder: (_, healthy, __) => StatusChip(label: healthy ? 'Online' : 'Offline', color: healthy ? Colors.greenAccent : Colors.redAccent),
          ),
        ],
      ),
    );
  }
}

class CommandCenterScreen extends StatelessWidget {
  final ApiService api;
  const CommandCenterScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<DriverState?>(
      valueListenable: api.currentState,
      builder: (_, state, __) {
        if (state == null) return const Center(child: CircularProgressIndicator());
        return ValueListenableBuilder<AnalyticsSummary>(
          valueListenable: api.analytics,
          builder: (_, analytics, __) => RefreshIndicator(
            onRefresh: api.refreshAll,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _HeroCard(state: state, api: api),
                const SizedBox(height: 16),
                _ResponsiveGrid(children: [
                  _MetricCard(title: 'Risk Score', value: '${state.riskScore}/100', icon: Icons.speed_rounded, color: state.levelColor),
                  _MetricCard(title: 'Events', value: '${analytics.totalEvents}', icon: Icons.dataset_rounded, color: Colors.lightBlueAccent),
                  _MetricCard(title: 'Danger', value: '${analytics.dangerCount}', icon: Icons.report_rounded, color: Colors.redAccent),
                  _MetricCard(title: 'Warnings', value: '${analytics.warningCount}', icon: Icons.warning_rounded, color: Colors.orangeAccent),
                ]),
                const SizedBox(height: 16),
                _ActionPanel(state: state, api: api),
                const SizedBox(height: 16),
                _SourceCard(api: api, state: state),
              ],
            ),
          ),
        );
      },
    );
  }
}

class MonitoringScreen extends StatelessWidget {
  final ApiService api;
  const MonitoringScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<DriverState?>(
      valueListenable: api.currentState,
      builder: (_, state, __) {
        if (state == null) return const Center(child: CircularProgressIndicator());
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Container(
              padding: const EdgeInsets.all(22),
              decoration: BoxDecoration(
                color: const Color(0xFF111827),
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: state.levelColor.withOpacity(0.45)),
                boxShadow: [BoxShadow(color: state.levelColor.withOpacity(0.16), blurRadius: 24)],
              ),
              child: Column(
                children: [
                  Icon(state.buzzer ? Icons.notification_important_rounded : Icons.visibility_rounded, size: 78, color: state.levelColor),
                  const SizedBox(height: 12),
                  Text(state.driverState, style: TextStyle(fontSize: 30, fontWeight: FontWeight.bold, color: state.levelColor), textAlign: TextAlign.center),
                  const SizedBox(height: 8),
                  Text(state.spokenText, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800), textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  _RiskBar(score: state.riskScore, color: state.levelColor),
                  const SizedBox(height: 14),
                  Text(state.recommendedAction, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70, height: 1.5)),
                ],
              ),
            ),
            const SizedBox(height: 16),
            InfoTile.list(title: 'Current level', subtitle: state.level, icon: Icons.flag_rounded, color: state.levelColor),
            InfoTile.list(title: 'Trigger', subtitle: state.trigger.isEmpty ? 'No trigger reported' : state.trigger, icon: Icons.bolt_rounded, color: Colors.amberAccent),
            InfoTile.list(title: 'Buzzer', subtitle: state.buzzer ? 'Physical alarm should be active' : 'No alarm needed', icon: Icons.volume_up_rounded, color: state.buzzer ? Colors.orangeAccent : Colors.greenAccent),
            InfoTile.list(title: 'AI spoken output', subtitle: state.spokenText, icon: Icons.campaign_rounded, color: Colors.purpleAccent),
            InfoTile.list(title: 'Suggested route', subtitle: state.suggestedRoute, icon: Icons.route_rounded, color: Colors.lightBlueAccent),
          ],
        );
      },
    );
  }
}

class AnalyticsScreen extends StatelessWidget {
  final ApiService api;
  const AnalyticsScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<AnalyticsSummary>(
      valueListenable: api.analytics,
      builder: (_, analytics, __) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SectionTitle(title: 'Safety Analytics', subtitle: 'Live backend statistics and risk trend'),
          const SizedBox(height: 12),
          _ResponsiveGrid(children: [
            _MetricCard(title: 'Highest Risk', value: '${analytics.highestRiskScore}/100', icon: Icons.trending_up_rounded, color: Colors.redAccent),
            _MetricCard(title: 'Latest Risk', value: '${analytics.latestRiskScore}/100', icon: Icons.speed_rounded, color: Colors.orangeAccent),
            _MetricCard(title: 'Drowsy', value: '${analytics.drowsyCount}', icon: Icons.bedtime_rounded, color: Colors.purpleAccent),
            _MetricCard(title: 'Distracted', value: '${analytics.distractedCount}', icon: Icons.phone_android_rounded, color: Colors.amberAccent),
          ]),
          const SizedBox(height: 16),
          _BreakdownCard(title: 'Level Breakdown', data: analytics.levelBreakdown),
          const SizedBox(height: 16),
          _BreakdownCard(title: 'Driver State Breakdown', data: analytics.driverStateBreakdown),
          const SizedBox(height: 16),
          _RecommendationCard(recommendations: analytics.safetyRecommendations),
        ],
      ),
    );
  }
}

class AlertsScreen extends StatelessWidget {
  final ApiService api;
  const AlertsScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<AlertItem>>(
      valueListenable: api.alerts,
      builder: (_, alerts, __) {
        if (alerts.isEmpty) return const Center(child: Text('No alerts yet. Start the backend or create a manual test alert.'));
        final highRisk = alerts.where((item) => item.isHighRisk).length;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SectionTitle(title: 'Alert Feed', subtitle: '$highRisk high-risk items in the recent feed'),
            const SizedBox(height: 12),
            ...alerts.map((item) => Padding(padding: const EdgeInsets.only(bottom: 12), child: AlertCard(item: item))),
          ],
        );
      },
    );
  }
}

class TripsScreen extends StatelessWidget {
  final ApiService api;
  const TripsScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<SessionSummary>>(
      valueListenable: api.sessions,
      builder: (_, sessions, __) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SectionTitle(title: 'Trip Sessions', subtitle: 'Session summaries from the backend event log'),
          const SizedBox(height: 12),
          if (sessions.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('No session data yet.'))),
          ...sessions.map((session) => Card(
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: session.highestRiskScore >= 70 ? Colors.redAccent.withOpacity(0.18) : Colors.blueAccent.withOpacity(0.18),
                    child: Icon(Icons.route_rounded, color: session.highestRiskScore >= 70 ? Colors.redAccent : Colors.lightBlueAccent),
                  ),
                  title: Text('Session ${session.sessionId}'),
                  subtitle: Text('${session.events} events • ${session.warningCount} warnings • ${session.dangerCount} danger • last ${session.lastEvent}'),
                  trailing: Text('${session.highestRiskScore}/100', style: const TextStyle(fontWeight: FontWeight.bold)),
                ),
              )),
          const SizedBox(height: 16),
          _ConversationCard(api: api),
        ],
      ),
    );
  }
}

class SystemScreen extends StatelessWidget {
  final ApiService api;
  const SystemScreen({super.key, required this.api});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionTitle(title: 'System & Backend', subtitle: 'Connection, schema, and developer controls'),
        const SizedBox(height: 12),
        ValueListenableBuilder<String>(
          valueListenable: api.statusMessage,
          builder: (_, message, __) => Card(
            child: ListTile(
              leading: ValueListenableBuilder<bool>(
                valueListenable: api.isHealthy,
                builder: (_, healthy, __) => Icon(healthy ? Icons.cloud_done_rounded : Icons.cloud_off_rounded, color: healthy ? Colors.greenAccent : Colors.redAccent),
              ),
              title: Text(message),
              subtitle: ValueListenableBuilder<int>(
                valueListenable: api.latencyMs,
                builder: (_, latency, __) => Text('Backend: ${api.baseUrl.value} • Latency: ${latency}ms'),
              ),
              trailing: FilledButton.icon(onPressed: api.refreshAll, icon: const Icon(Icons.refresh_rounded), label: const Text('Refresh')),
            ),
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: api.createTestWarning,
          icon: const Icon(Icons.add_alert_rounded),
          label: const Text('Create Manual Test Warning'),
        ),
        const SizedBox(height: 16),
        _JsonCard(title: 'Backend Config', listenable: api.backendConfig),
        const SizedBox(height: 16),
        _JsonCard(title: 'API Schema', listenable: api.schema),
      ],
    );
  }
}

class _HeroCard extends StatelessWidget {
  final DriverState state;
  final ApiService api;
  const _HeroCard({required this.state, required this.api});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [state.levelColor.withOpacity(0.9), const Color(0xFF1D4ED8)]),
        borderRadius: BorderRadius.circular(28),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Current Live Driver State', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 12),
          Text(state.driverState, style: const TextStyle(fontSize: 30, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text(state.spokenText, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          _RiskBar(score: state.riskScore, color: Colors.white),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              StatusChip(label: state.level, color: Colors.white),
              StatusChip(label: state.buzzer ? 'Buzzer ON' : 'Buzzer OFF', color: state.buzzer ? Colors.orangeAccent : Colors.greenAccent),
              StatusChip(label: 'Rows: ${api.rowsLoaded.value}', color: Colors.lightBlueAccent),
              StatusChip(label: 'Session: ${state.sessionId}', color: Colors.white70),
            ],
          ),
        ],
      ),
    );
  }
}

class _ActionPanel extends StatelessWidget {
  final DriverState state;
  final ApiService api;
  const _ActionPanel({required this.state, required this.api});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Recommended Action', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Text(state.recommendedAction, style: const TextStyle(height: 1.5)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton.icon(onPressed: api.refreshAll, icon: const Icon(Icons.sync_rounded), label: const Text('Sync Now')),
                OutlinedButton.icon(onPressed: api.createTestWarning, icon: const Icon(Icons.add_alert_rounded), label: const Text('Test Alert')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  final ApiService api;
  final DriverState state;
  const _SourceCard({required this.api, required this.state});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Live Source', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _Row(label: 'Backend URL', value: api.baseUrl.value),
            _Row(label: 'Timestamp', value: state.timestamp),
            _Row(label: 'Raw input', value: state.input),
            _Row(label: 'Message', value: state.message),
            _Row(label: 'Trigger', value: state.trigger),
            _Row(label: 'Source file', value: state.sourcePath),
          ],
        ),
      ),
    );
  }
}

class _ResponsiveGrid extends StatelessWidget {
  final List<Widget> children;
  const _ResponsiveGrid({required this.children});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final count = constraints.maxWidth > 900 ? 4 : constraints.maxWidth > 560 ? 2 : 2;
        return GridView.count(
          crossAxisCount: count,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: constraints.maxWidth > 560 ? 1.5 : 1.08,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: children,
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color color;
  const _MetricCard({required this.title, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return InfoTile.card(title: title, value: value, icon: icon, color: color);
  }
}

class _RiskBar extends StatelessWidget {
  final int score;
  final Color color;
  const _RiskBar({required this.score, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text('Risk Score'), Text('$score/100', style: const TextStyle(fontWeight: FontWeight.bold))]),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(99),
          child: LinearProgressIndicator(value: score / 100, minHeight: 12, color: color, backgroundColor: Colors.white.withOpacity(0.18)),
        ),
      ],
    );
  }
}

class _BreakdownCard extends StatelessWidget {
  final String title;
  final Map<String, int> data;
  const _BreakdownCard({required this.title, required this.data});

  @override
  Widget build(BuildContext context) {
    final total = data.values.fold<int>(0, (sum, item) => sum + item);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            if (data.isEmpty) const Text('No breakdown available yet.'),
            ...data.entries.map((entry) {
              final value = total == 0 ? 0.0 : entry.value / total;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(entry.key), Text('${entry.value}')]),
                    const SizedBox(height: 6),
                    LinearProgressIndicator(value: value, minHeight: 8),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  final List<String> recommendations;
  const _RecommendationCard({required this.recommendations});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Backend Safety Recommendations', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            if (recommendations.isEmpty) const Text('No recommendations yet.'),
            ...recommendations.map((item) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [const Icon(Icons.check_circle_rounded, color: Colors.greenAccent, size: 18), const SizedBox(width: 8), Expanded(child: Text(item))]),
                )),
          ],
        ),
      ),
    );
  }
}

class _ConversationCard extends StatelessWidget {
  final ApiService api;
  const _ConversationCard({required this.api});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<List<ConversationTurn>>(
      valueListenable: api.conversation,
      builder: (_, turns, __) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Conversation History', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              if (turns.isEmpty) const Text('No conversation turns were found.'),
              ...turns.map((turn) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(turn.role == 'driver' ? Icons.person_rounded : Icons.smart_toy_rounded, color: turn.role == 'driver' ? Colors.amberAccent : Colors.lightBlueAccent),
                    title: Text(turn.text.isEmpty ? '(empty turn)' : turn.text),
                    subtitle: Text('${turn.role} • ${turn.timestamp} • ${turn.driverState}'),
                  )),
            ],
          ),
        ),
      ),
    );
  }
}

class _JsonCard extends StatelessWidget {
  final String title;
  final ValueNotifier<Map<String, dynamic>?> listenable;
  const _JsonCard({required this.title, required this.listenable});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Map<String, dynamic>?>(
      valueListenable: listenable,
      builder: (_, data, __) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              SelectableText(data == null ? 'Not loaded yet.' : data.toString(), style: const TextStyle(height: 1.5)),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;
  final String subtitle;
  const _SectionTitle({required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)), const SizedBox(height: 4), Text(subtitle, style: const TextStyle(color: Colors.white70))]);
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  const _Row({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 112, child: Text(label, style: const TextStyle(color: Colors.white70))),
          Expanded(child: Text(value.isEmpty ? 'N/A' : value)),
        ],
      ),
    );
  }
}
