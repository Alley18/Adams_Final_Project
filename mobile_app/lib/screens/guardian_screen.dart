import 'package:flutter/material.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

import '../services/firebase_bootstrap.dart';
import '../widgets/big_circle_button.dart';
import '../widgets/screen_frame.dart';
import '../widgets/status_strip.dart';

class GuardianScreen extends StatefulWidget {
  const GuardianScreen({super.key});

  @override
  State<GuardianScreen> createState() => _GuardianScreenState();
}

class _GuardianScreenState extends State<GuardianScreen> {
  static const _repeatWarningInterval = Duration(seconds: 12);

  static const MethodChannel _alertChannel =
      MethodChannel('adams/guardian_alerts');

  final FlutterTts tts = FlutterTts();

  DateTime? _lastWarningAt;
  String? _lastWarningKey;

  @override
  void initState() {
    super.initState();
    _setupVoice();
  }

  @override
  void dispose() {
    tts.stop();
    super.dispose();
  }

  Future<void> _setupVoice() async {
    await tts.setLanguage('en-US');
    await tts.setSpeechRate(0.5);
    await tts.setPitch(1.0);
    await tts.setVolume(1.0);
    await tts.awaitSpeakCompletion(false);
  }

  void _handleWarning({
    required String driverState,
    required bool handsOnWheel,
    required bool isDanger,
  }) {
    // Reset warning cooldown when safe
    if (!isDanger) {
      _lastWarningKey = null;
      _lastWarningAt = null;
      return;
    }

    final warningKey = '$driverState|$handsOnWheel';
    final now = DateTime.now();

    final shouldRepeat = _lastWarningAt == null ||
        now.difference(_lastWarningAt!) >=
            _repeatWarningInterval;

    // Avoid repeating same warning too frequently
    if (_lastWarningKey == warningKey &&
        !shouldRepeat) {
      return;
    }

    _lastWarningKey = warningKey;
    _lastWarningAt = now;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;

      await _vibrateAlert();

      await tts.stop();
      await tts.speak(
        _warningText(driverState, handsOnWheel),
      );
    });
  }

  Future<void> _vibrateAlert() async {
    try {
      await _alertChannel.invokeMethod<void>(
        'vibrateAlert',
      );
    } on PlatformException {
      await HapticFeedback.vibrate();
      await HapticFeedback.heavyImpact();
    } on MissingPluginException {
      await HapticFeedback.vibrate();
      await HapticFeedback.heavyImpact();
    }
  }

  String _warningText(
    String driverState,
    bool handsOnWheel,
  ) {
    if (!handsOnWheel &&
        driverState != 'NORMAL') {
      return 'Guardian alert. Driver is $driverState and hands are off the wheel.';
    }

    if (!handsOnWheel) {
      return 'Guardian alert. Put your hands back on the wheel.';
    }

    return 'Guardian alert. Driver state is $driverState.';
  }

  bool _parseBool(dynamic value) {
    if (value is bool) return value;

    if (value is String) {
      return value.toLowerCase() == 'true';
    }

    if (value is int) {
      return value != 0;
    }

    return false;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: FirebaseBootstrap.initialize(),
      builder: (
        context,
        firebaseSnapshot,
      ) {
        if (firebaseSnapshot.connectionState !=
            ConnectionState.done) {
          return const _MessageScaffold(
            child: CircularProgressIndicator(),
          );
        }

        final app = firebaseSnapshot.data;

        if (app == null) {
          return _MessageScaffold(
            child: Padding(
              padding:
                  const EdgeInsets.all(24),
              child: Text(
                'Firebase is not configured yet.\n\n'
                '${FirebaseBootstrap.lastError ?? 'Add Firebase settings to .env.'}',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }

        final configuredDatabaseUrl =
            FirebaseBootstrap.databaseUrl;

        final database =
            configuredDatabaseUrl.isEmpty
                ? FirebaseDatabase.instanceFor(
                    app: app,
                  )
                : FirebaseDatabase.instanceFor(
                    app: app,
                    databaseURL:
                        configuredDatabaseUrl,
                  );

        // FIXED:
        // Listen to guardian_live
        // NOT driver_status
        final dbRef =
            database.ref('guardian_live');

        return StreamBuilder<DatabaseEvent>(
          stream: dbRef.onValue,
          builder: (
            context,
            snapshot,
          ) {
            if (snapshot.hasError) {
              return _MessageScaffold(
                child: Text(
                  'Firebase error:\n${snapshot.error}',
                  textAlign:
                      TextAlign.center,
                ),
              );
            }

            if (!snapshot.hasData) {
              return const _MessageScaffold(
                child:
                    CircularProgressIndicator(),
              );
            }

            final rawValue = snapshot
                .data
                ?.snapshot
                .value;

            debugPrint(
              'FIREBASE RAW: $rawValue',
            );

            final data =
                rawValue
                    as Map<dynamic, dynamic>?;

            if (data == null) {
              return const _MessageScaffold(
                child:
                    Text('No Firebase data'),
              );
            }

            debugPrint(
              'FIREBASE DATA: $data',
            );

            // guardian_live fields
            final driverState =
                data['driver_state']
                        ?.toString() ??
                    'UNKNOWN';

            final handsOnWheel =
                _parseBool(
              data['hands_on_wheel'],
            );

            final dangerDuration =
                data[
                    'danger_duration_s'];

            final handsOffDuration =
                data[
                    'hands_off_duration_s'];

            final escalated =
                _parseBool(
              data['escalated'],
            );

            final helpDisplayed =
                _parseBool(
              data['help_displayed'],
            );

            final isDanger =
                driverState !=
                        'NORMAL' ||
                    !handsOnWheel;

            _handleWarning(
              driverState:
                  driverState,
              handsOnWheel:
                  handsOnWheel,
              isDanger:
                  isDanger,
            );

            return ScreenFrame(
              title: 'Guardian',
              subtitle:
                  driverState,
              backgroundColor:
                  isDanger
                      ? const Color(
                          0xFF8B0000)
                      : null,
              child: Column(
                children: [
                  Expanded(
                    child: Center(
                      child:
                          BigCircleButton(
                        icon:
                            isDanger
                                ? Icons
                                    .warning_amber_rounded
                                : Icons
                                    .favorite,
                        label:
                            isDanger
                                ? 'ALERT'
                                : 'OK',
                        color:
                            isDanger
                                ? const Color(
                                    0xFFE6B325)
                                : const Color(
                                    0xFF24B47E),
                      ),
                    ),
                  ),

                  // Live guardian info
                  Padding(
                    padding:
                        const EdgeInsets
                            .symmetric(
                      horizontal: 16,
                    ),
                    child: Column(
                      children: [
                        Text(
                          'Danger Duration: '
                          '${dangerDuration ?? 0}s',
                        ),
                        Text(
                          'Hands Off: '
                          '${handsOffDuration ?? 0}s',
                        ),
                        Text(
                          'Escalated: '
                          '${escalated ? 'YES' : 'NO'}',
                        ),
                        Text(
                          'Help Displayed: '
                          '${helpDisplayed ? 'YES' : 'NO'}',
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(
                    height: 12,
                  ),

                  StatusStrip(
                    items: [
                      StatusItem(
                        'Driver',
                        driverState,
                      ),
                      StatusItem(
                        'Wheel',
                        handsOnWheel
                            ? 'ON'
                            : 'OFF',
                      ),
                      StatusItem(
                        'Alert',
                        isDanger
                            ? 'YES'
                            : 'NO',
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _MessageScaffold
    extends StatelessWidget {
  const _MessageScaffold({
    required this.child,
  });

  final Widget child;

  @override
  Widget build(
    BuildContext context,
  ) {
    return Scaffold(
      body: Center(
        child: child,
      ),
    );
  }
}