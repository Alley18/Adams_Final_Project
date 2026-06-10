import 'dart:async';

import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

import 'screens/analytics_screen.dart';
import 'screens/co_pilot_screen.dart';
import 'screens/emergency_copilot_screen.dart';
import 'screens/guardian_screen.dart';
import 'screens/mood_route_screen.dart';
import 'services/firebase_bootstrap.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await dotenv.load(fileName: '.env');
  await FirebaseBootstrap.initialize();
  runApp(const AdamsMobileApp());
}

class AdamsMobileApp extends StatelessWidget {
  const AdamsMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'ADAMS',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFFF9F1C),
          brightness: Brightness.dark,
        ).copyWith(
          primary: const Color(0xFFFF9F1C),
          secondary: const Color(0xFFFFC857),
          surface: const Color(0xFF15181D),
          onSurface: const Color(0xFFF7F2EA),
        ),
        scaffoldBackgroundColor: const Color(0xFF0C0F13),
        useMaterial3: true,
        textTheme: ThemeData.dark().textTheme.apply(
              bodyColor: const Color(0xFFF7F2EA),
              displayColor: const Color(0xFFF7F2EA),
            ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF171B21),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: Color(0xFF323842)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: Color(0xFF323842)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: Color(0xFFFF9F1C), width: 1.4),
          ),
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: const Color(0xFF11151A),
          indicatorColor: const Color(0xFFFF9F1C).withValues(alpha: 0.18),
          labelTextStyle: WidgetStateProperty.resolveWith(
            (states) => TextStyle(
              color: states.contains(WidgetState.selected)
                  ? const Color(0xFFFFC857)
                  : const Color(0xFF8F98A3),
              fontSize: 12,
              fontWeight: states.contains(WidgetState.selected)
                  ? FontWeight.w700
                  : FontWeight.w500,
              letterSpacing: 0,
            ),
          ),
          iconTheme: WidgetStateProperty.resolveWith(
            (states) => IconThemeData(
              color: states.contains(WidgetState.selected)
                  ? const Color(0xFFFFC857)
                  : const Color(0xFF8F98A3),
            ),
          ),
        ),
      ),
      home: const AdamsShell(),
    );
  }
}

class AdamsShell extends StatefulWidget {
  const AdamsShell({super.key});

  @override
  State<AdamsShell> createState() => _AdamsShellState();
}

class _AdamsShellState extends State<AdamsShell> {
  static const Duration _sustainedDrowsyHandsOffBeforeEmergency =
      Duration(seconds: 30);

  int selectedIndex = 0;

  StreamSubscription<DatabaseEvent>? _driverStatusSub;
  Timer? _dangerAuditTimer;

  DateTime? _dangerStartedAt;
  Map<dynamic, dynamic>? _latestDriverStatus;
  bool _emergencyActive = false;
  bool _emergencyDemoMode = false;
  String _emergencyReason = '';

  static const screens = [
    CoPilotScreen(),
    GuardianScreen(),
    MoodRouteScreen(),
    AnalyticsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _startEmergencyMonitor();
  }

  @override
  void dispose() {
    _driverStatusSub?.cancel();
    _dangerAuditTimer?.cancel();
    super.dispose();
  }

  void _startEmergencyMonitor() {
    _driverStatusSub =
        FirebaseDatabase.instance.ref('driver_status').onValue.listen((event) {
      final raw = event.snapshot.value;
      if (raw is! Map<dynamic, dynamic>) {
        _resetDangerCandidate();
        return;
      }

      _latestDriverStatus = raw;
      _auditDangerCandidate();
    });

    _dangerAuditTimer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => _auditDangerCandidate(),
    );
  }

  void _auditDangerCandidate() {
    if (_emergencyActive) return;

    final status = _latestDriverStatus;
    if (status == null || !_isSevereEmergencyCandidate(status)) {
      _resetDangerCandidate();
      return;
    }

    _dangerStartedAt ??= DateTime.now();
    final heldFor = DateTime.now().difference(_dangerStartedAt!);

    if (heldFor >= _sustainedDrowsyHandsOffBeforeEmergency) {
      _activateEmergency(
        reason: _emergencyReasonFromStatus(status),
        demoMode: false,
      );
    }
  }

  bool _isSevereEmergencyCandidate(Map<dynamic, dynamic> data) {
    final driverState = _readString(data, 'driver_state').toUpperCase();
    final trigger = _readString(data, 'trigger').toUpperCase();
    final handsOnWheel = _readBool(data['hands_on_wheel'], fallback: true);

    final drowsy = driverState == 'DROWSY' || trigger.contains('DROWSY');
    return drowsy && !handsOnWheel;
  }

  String _emergencyReasonFromStatus(Map<dynamic, dynamic> data) {
    final driverState = _readString(data, 'driver_state', fallback: 'Unknown');
    final handsOnWheel = _readBool(data['hands_on_wheel'], fallback: true);

    if (!handsOnWheel && driverState.toUpperCase() == 'DROWSY') {
      return 'Driver has been drowsy with hands off the wheel for 30 seconds.';
    }

    return 'Driver has been drowsy and hands are off the wheel.';
  }

  String _readString(
    Map<dynamic, dynamic> data,
    String key, {
    String fallback = '',
  }) {
    return data[key]?.toString().trim() ?? fallback;
  }

  bool _readBool(dynamic value, {required bool fallback}) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      if (normalized == 'true' || normalized == 'yes' || normalized == 'on') {
        return true;
      }
      if (normalized == 'false' || normalized == 'no' || normalized == 'off') {
        return false;
      }
    }
    return fallback;
  }

  void _resetDangerCandidate() {
    _dangerStartedAt = null;
  }

  void _activateEmergency({
    required String reason,
    required bool demoMode,
  }) {
    if (!mounted || _emergencyActive) return;

    setState(() {
      _emergencyActive = true;
      _emergencyDemoMode = demoMode;
      _emergencyReason = reason;
    });
  }

  void _resolveEmergency() {
    setState(() {
      _emergencyActive = false;
      _emergencyDemoMode = false;
      _emergencyReason = '';
      _dangerStartedAt = null;
    });
  }

  void _triggerDemoEmergency() {
    _activateEmergency(
      reason:
          'Professor demo trigger: ADAMS is simulating a confirmed high-risk driver emergency.',
      demoMode: true,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            IndexedStack(
              index: selectedIndex,
              children: screens,
            ),
            Positioned(
              top: 10,
              right: 10,
              child: _EmergencyDemoButton(onPressed: _triggerDemoEmergency),
            ),
            if (_emergencyActive)
              Positioned.fill(
                child: EmergencyCoPilotScreen(
                  reason: _emergencyReason,
                  demoMode: _emergencyDemoMode,
                  onResolved: _resolveEmergency,
                ),
              ),
          ],
        ),
      ),
      bottomNavigationBar: _emergencyActive
          ? null
          : NavigationBar(
              selectedIndex: selectedIndex,
              onDestinationSelected: (index) {
                setState(() {
                  selectedIndex = index;
                });
              },
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.mic_none),
                  selectedIcon: Icon(Icons.mic),
                  label: 'Co-Pilot',
                ),
                NavigationDestination(
                  icon: Icon(Icons.shield_outlined),
                  selectedIcon: Icon(Icons.shield),
                  label: 'Guardian',
                ),
                NavigationDestination(
                  icon: Icon(Icons.route_outlined),
                  selectedIcon: Icon(Icons.route),
                  label: 'Route',
                ),
                NavigationDestination(
                  icon: Icon(Icons.bar_chart_outlined),
                  selectedIcon: Icon(Icons.bar_chart),
                  label: 'Analytics',
                ),
              ],
            ),
    );
  }
}

class _EmergencyDemoButton extends StatelessWidget {
  const _EmergencyDemoButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Demo emergency mode',
      child: Material(
        color: Colors.transparent,
        child: IconButton.filledTonal(
          onPressed: onPressed,
          icon: const Icon(Icons.crisis_alert),
          style: IconButton.styleFrom(
            backgroundColor: const Color(0xFFFF9F1C),
            foregroundColor: const Color(0xFF1A0F02),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
      ),
    );
  }
}
