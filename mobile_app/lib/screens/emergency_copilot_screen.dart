import 'dart:async';

import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

// ─────────────────────────────────────────────────────────────────────────────
// USAGE — call this from any button press in your app:
//
//   ElevatedButton(
//     onPressed: () => EmergencyCoPilotScreen.show(context),
//     child: Text('Trigger Emergency'),
//   )
//
// That's it. No Firebase listener, no auto-trigger, no drowsy detection.
// ─────────────────────────────────────────────────────────────────────────────

class EmergencyCoPilotScreen extends StatefulWidget {
  const EmergencyCoPilotScreen({super.key});

  // Convenience static method — call this from your button
  static void show(BuildContext context) {
    Navigator.of(context).push(PageRouteBuilder(
      opaque: true,
      barrierDismissible: false,
      pageBuilder: (_, __, ___) => const EmergencyCoPilotScreen(),
    ));
  }

  @override
  State<EmergencyCoPilotScreen> createState() => _EmergencyCoPilotScreenState();
}

class _EmergencyCoPilotScreenState extends State<EmergencyCoPilotScreen> {
  static const int _responseSeconds = 10;

  final FlutterTts _tts = FlutterTts();
  Timer? _countdownTimer;
  Timer? _pulseTimer;

  int  _secondsLeft = _responseSeconds;
  bool _escalated   = false;
  bool _resolved    = false;

  @override
  void initState() {
    super.initState();
    _initTts();
    _startFlow();
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _pulseTimer?.cancel();
    _tts.stop();
    super.dispose();
  }

  Future<void> _initTts() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.48);
    await _tts.setPitch(1.0);
    await _tts.setVolume(1.0);
  }

  void _startFlow() {
    _secondsLeft = _responseSeconds;
    _speakWarning();
    _vibrate();

    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _resolved || _escalated) { timer.cancel(); return; }
      if (_secondsLeft <= 1) { timer.cancel(); _escalate(); return; }
      setState(() => _secondsLeft -= 1);
    });
  }

  Future<void> _speakWarning() async {
    await _tts.stop();
    await _tts.speak(
      'Emergency co-pilot mode active. Driver response required. Tap I am OK to confirm.',
    );
  }

  Future<void> _vibrate() async {
    await HapticFeedback.vibrate();
    await HapticFeedback.heavyImpact();
  }

  Future<void> _escalate() async {
    if (_escalated || _resolved) return;
    _countdownTimer?.cancel();

    setState(() { _secondsLeft = 0; _escalated = true; });

    // Pulse vibration every 2 s after escalation
    _pulseTimer = Timer.periodic(const Duration(seconds: 2), (_) => _vibrate());

    await _vibrate();
    await _tts.stop();
    await _tts.speak('No driver response detected. Starting demo emergency call.');
    await _logIncident('ESCALATED');
  }

  Future<void> _resolve() async {
    if (_resolved) return;
    _resolved = true;
    _countdownTimer?.cancel();
    _pulseTimer?.cancel();
    await _tts.stop();
    await _logIncident(_escalated ? 'ACKNOWLEDGED_AFTER_ESCALATION' : 'CANCELLED_BY_DRIVER');
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _logIncident(String status) async {
    try {
      await FirebaseDatabase.instance.ref('emergency_incidents').push().set({
        'status':    status,
        'trigger':   'manual_button',
        'timestamp': ServerValue.timestamp,
      });
    } catch (_) {
      // Never block the UI for logging
    }
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Material(
        color: const Color(0xFF120506),
        child: SafeArea(
          child: Stack(
            children: [
              // Background glow
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      center: Alignment.topCenter,
                      radius: 1.15,
                      colors: [
                        const Color(0xFFB71C1C).withValues(alpha: 0.72),
                        const Color(0xFF120506),
                      ],
                    ),
                  ),
                ),
              ),

              Padding(
                padding: const EdgeInsets.all(22),
                child: Column(
                  children: [
                    // Header
                    Row(children: [
                      Container(
                        width: 46, height: 46,
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFC107).withValues(alpha: 0.16),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFFFFC107), width: 1.2),
                        ),
                        child: const Icon(Icons.crisis_alert, color: Color(0xFFFFC107), size: 28),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('EMERGENCY CO-PILOT',
                                style: TextStyle(color: Colors.white, fontSize: 17,
                                    fontWeight: FontWeight.w900)),
                            Text('Manually triggered',
                                style: TextStyle(color: Colors.white60, fontSize: 12)),
                          ],
                        ),
                      ),
                    ]),

                    const Spacer(),

                    // Countdown circle
                    Container(
                      width: 188, height: 188,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: _escalated ? const Color(0xFFFFC107) : Colors.white,
                          width: 7,
                        ),
                        color: Colors.black.withValues(alpha: 0.28),
                        boxShadow: [BoxShadow(
                          color: const Color(0xFFE53935).withValues(alpha: 0.48),
                          blurRadius: 40, spreadRadius: 8,
                        )],
                      ),
                      child: Center(child: Text(
                        _escalated ? 'SOS' : '$_secondsLeft',
                        style: TextStyle(
                          color: _escalated ? const Color(0xFFFFC107) : Colors.white,
                          fontSize: _escalated ? 48 : 68,
                          fontWeight: FontWeight.w900,
                        ),
                      )),
                    ),

                    const SizedBox(height: 22),

                    Text(
                      _escalated ? 'Demo emergency call started' : 'Driver response required',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 26,
                          fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _escalated
                          ? 'Emergency contact / 911 notification is simulated for demonstration.'
                          : 'Emergency was triggered manually. Tap I\'m OK if this was a test.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.74),
                          fontSize: 15, height: 1.35),
                    ),

                    const Spacer(),

                    // Fake call panel (after escalation)
                    if (_escalated)
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.34),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFFFFC107)),
                        ),
                        child: const Row(children: [
                          Icon(Icons.phone_in_talk, color: Color(0xFFFFC107), size: 30),
                          SizedBox(width: 12),
                          Expanded(child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Calling demo emergency contact...',
                                  style: TextStyle(color: Colors.white, fontSize: 15,
                                      fontWeight: FontWeight.w800)),
                              SizedBox(height: 3),
                              Text('Manual trigger — demonstration mode',
                                  style: TextStyle(color: Colors.white60, fontSize: 12)),
                            ],
                          )),
                        ]),
                      ),

                    // Skip to demo call button (before escalation)
                    if (!_escalated) ...[
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity, height: 48,
                        child: OutlinedButton.icon(
                          onPressed: _escalate,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFFFFC107),
                            side: const BorderSide(color: Color(0xFFFFC107), width: 1.4),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8)),
                          ),
                          icon: const Icon(Icons.warning_amber_rounded, size: 20),
                          label: const Text('Skip to Demo Call',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                        ),
                      ),
                    ],

                    const SizedBox(height: 18),

                    // I'm OK button
                    SizedBox(
                      width: double.infinity, height: 58,
                      child: FilledButton.icon(
                        onPressed: _resolve,
                        style: FilledButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: const Color(0xFF8B0000),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8)),
                        ),
                        icon: const Icon(Icons.check_circle),
                        label: Text(
                          _escalated ? 'Driver Responded' : "I'm OK",
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}