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
            borderSide:
                const BorderSide(color: Color(0xFFFF9F1C), width: 1.4),
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
  int _selectedIndex = 0;

  static const _screens = [
    CoPilotScreen(),
    GuardianScreen(),
    MoodRouteScreen(),
    AnalyticsScreen(),
  ];

  // Simply push the emergency screen on top — no state needed here
  void _triggerEmergency() {
    EmergencyCoPilotScreen.show(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            IndexedStack(
              index: _selectedIndex,
              children: _screens,
            ),
            // Demo button — top right corner
            Positioned(
              top: 10,
              right: 10,
              child: Tooltip(
                message: 'Demo emergency mode',
                child: IconButton.filledTonal(
                  onPressed: _triggerEmergency,
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
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
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