import 'dart:async';

import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

class EmergencyCoPilotScreen extends StatefulWidget {
  const EmergencyCoPilotScreen({
    required this.reason,
    required this.demoMode,
    required this.onResolved,
    super.key,
  });

  final String reason;
  final bool demoMode;
  final VoidCallback onResolved;

  @override
  State<EmergencyCoPilotScreen> createState() => _EmergencyCoPilotScreenState();
}

class _EmergencyCoPilotScreenState extends State<EmergencyCoPilotScreen> {
  static const int _responseSeconds = 30;

  final FlutterTts _tts = FlutterTts();

  Timer? _countdownTimer;
  Timer? _pulseTimer;

  int _secondsLeft = _responseSeconds;
  bool _escalated = false;
  bool _loggedEscalation = false;
  bool _resolved = false;

  @override
  void initState() {
    super.initState();
    _initTts();
    _startEmergencyFlow();
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

  void _startEmergencyFlow() {
    _secondsLeft = _responseSeconds;
    _speakWarning();
    _vibrate();

    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(
      const Duration(seconds: 1),
      (timer) {
        if (!mounted || _resolved || _escalated) {
          timer.cancel();
          return;
        }

        if (_secondsLeft <= 1) {
          timer.cancel();
          _triggerEscalation();
          return;
        }

        setState(() {
          _secondsLeft -= 1;
        });
      },
    );
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

  Future<void> _triggerEscalation() async {
    if (_escalated || _resolved) return;

    _countdownTimer?.cancel();
    _pulseTimer?.cancel();
    _pulseTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => _vibrate(),
    );

    if (mounted) {
      setState(() {
        _secondsLeft = 0;
        _escalated = true;
      });
    }

    await _vibrate();
    await _tts.stop();
    await _tts.speak(
      'No driver response detected. Starting demo emergency call.',
    );
    await _logEmergency(status: 'ESCALATED');
  }

  Future<void> _resolve() async {
    if (_resolved) return;
    _resolved = true;

    _countdownTimer?.cancel();
    _pulseTimer?.cancel();
    await _tts.stop();
    await _logEmergency(
      status:
          _escalated ? 'ACKNOWLEDGED_AFTER_ESCALATION' : 'CANCELLED_BY_DRIVER',
    );
    widget.onResolved();
  }

  Future<void> _logEmergency({required String status}) async {
    if (_loggedEscalation && status == 'ESCALATED') return;
    if (status == 'ESCALATED') _loggedEscalation = true;

    try {
      await FirebaseDatabase.instance.ref('emergency_incidents').push().set({
        'status': status,
        'reason': widget.reason,
        'demo_mode': widget.demoMode,
        'timestamp': ServerValue.timestamp,
      });
    } catch (_) {
      // Logging must never block the emergency UI.
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Material(
        color: const Color(0xFF120506),
        child: SafeArea(
          child: Stack(
            children: [
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
                    _Header(demoMode: widget.demoMode),
                    const Spacer(),
                    _Countdown(
                      secondsLeft: _secondsLeft,
                      escalated: _escalated,
                    ),
                    const SizedBox(height: 22),
                    Text(
                      _escalated
                          ? 'Demo emergency call started'
                          : 'Driver response required',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _escalated
                          ? 'Emergency contact / 911 notification is simulated for class demonstration.'
                          : widget.reason,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.74),
                        fontSize: 15,
                        height: 1.35,
                        letterSpacing: 0,
                      ),
                    ),
                    const Spacer(),
                    if (_escalated) _FakeCallPanel(reason: widget.reason),
                    if (!_escalated) ...[
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: OutlinedButton.icon(
                          onPressed: _triggerEscalation,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFFFFC107),
                            side: const BorderSide(
                              color: Color(0xFFFFC107),
                              width: 1.4,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                          icon: const Icon(
                            Icons.warning_amber_rounded,
                            size: 20,
                          ),
                          label: const Text(
                            'Skip to Demo Call',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0,
                            ),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    SizedBox(
                      width: double.infinity,
                      height: 58,
                      child: FilledButton.icon(
                        onPressed: _resolve,
                        style: FilledButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: const Color(0xFF8B0000),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        icon: const Icon(Icons.check_circle),
                        label: Text(
                          _escalated ? 'Driver Responded' : "I'm OK",
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0,
                          ),
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

class _Header extends StatelessWidget {
  const _Header({required this.demoMode});

  final bool demoMode;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: const Color(0xFFFFC107).withValues(alpha: 0.16),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFFFFC107), width: 1.2),
          ),
          child: const Icon(
            Icons.crisis_alert,
            color: Color(0xFFFFC107),
            size: 28,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'EMERGENCY CO-PILOT',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              Text(
                demoMode
                    ? 'Demonstration trigger active'
                    : 'Drowsy and hands off wheel',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.62),
                  fontSize: 12,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Countdown extends StatelessWidget {
  const _Countdown({
    required this.secondsLeft,
    required this.escalated,
  });

  final int secondsLeft;
  final bool escalated;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 188,
      height: 188,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: escalated ? const Color(0xFFFFC107) : Colors.white,
          width: 7,
        ),
        color: Colors.black.withValues(alpha: 0.28),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFE53935).withValues(alpha: 0.48),
            blurRadius: 40,
            spreadRadius: 8,
          ),
        ],
      ),
      child: Center(
        child: Text(
          escalated ? 'SOS' : secondsLeft.toString(),
          style: TextStyle(
            color: escalated ? const Color(0xFFFFC107) : Colors.white,
            fontSize: escalated ? 48 : 68,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _FakeCallPanel extends StatelessWidget {
  const _FakeCallPanel({required this.reason});

  final String reason;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.34),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFFFC107), width: 1),
      ),
      child: Row(
        children: [
          const Icon(Icons.phone_in_talk, color: Color(0xFFFFC107), size: 30),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Calling demo emergency contact...',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  reason,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.62),
                    fontSize: 12,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
