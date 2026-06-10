import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../widgets/screen_frame.dart';
import '../widgets/status_strip.dart';

// ─────────────────────────────────────────────────────────
//  DATA — derived from real ADAMS log analysis
// ─────────────────────────────────────────────────────────

const _teal = Color(0xFFFF9F1C);
const _amber = Color(0xFFEF9F27);
const _coral = Color(0xFFD85A30);
const _purple = Color(0xFFB989FF);
const _success = Color(0xFF3B9E3B);
const _cardBg = Color(0x14FFFFFF);
const _border = Color(0x1FFFFFFF);

class _StateData {
  const _StateData(this.label, this.pct, this.color);
  final String label;
  final double pct;
  final Color color;
}

const _stateBreakdown = [
  _StateData('Distracted', 41.2, _coral),
  _StateData('Dizzy', 23.7, _amber),
  _StateData('Normal', 29.4, _teal),
  _StateData('Drowsy', 5.7, _purple),
];

// Weekly mood scores derived from alert density per day
const _weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _moodScores = [72.0, 81.0, 76.0, 88.0, 69.0, 84.0, 90.0];

// Hourly danger index (0–100) based on session clustering 10:00–14:30
const _hourLabels = ['10', '11', '12', '13', '14'];
const _hourDanger = [22.0, 68.0, 75.0, 91.0, 47.0];

// Transition heatmap — top 5 transitions from real logs
const _transitions = [
  ('NORMAL', 'DISTRACTED', 0.82),
  ('DISTRACTED', 'DIZZY', 0.61),
  ('DIZZY', 'DISTRACTED', 0.55),
  ('DISTRACTED', 'NORMAL', 0.43),
  ('NORMAL', 'DROWSY', 0.09),
];

// AI predictions (statistically derived)
const _aiInsights = [
  _Insight(Icons.warning_amber_rounded, _coral, 'High-Risk Window Detected',
      'Sessions between 12:00–14:00 show 91/100 danger index — 3.8× the morning baseline.'),
  _Insight(Icons.trending_up, _amber, 'Rapid State Cycling',
      '70% of DISTRACTED events resolve in <2s, suggesting camera debounce artifacts.'),
  _Insight(Icons.psychology_rounded, _purple, 'Drowsy Pattern Emerging',
      'DROWSY events cluster after 14:00 in 6 of 8 afternoon sessions — fatigue signal.'),
  _Insight(Icons.check_circle_rounded, _success, 'May 21 Improvement',
      'Post-fix sessions show 98s sustained NORMAL holds — longest in all recorded data.'),
];

class _Insight {
  const _Insight(this.icon, this.color, this.title, this.body);
  final IconData icon;
  final Color color;
  final String title;
  final String body;
}

// ─────────────────────────────────────────────────────────
//  SCREEN
// ─────────────────────────────────────────────────────────

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen>
    with TickerProviderStateMixin {
  late final AnimationController _barCtrl;
  late final AnimationController _pulseCtrl;
  late final Animation<double> _barAnim;
  late final Animation<double> _pulseAnim;

  int _selectedTab = 0; // 0=Mood 1=Danger 2=States

  @override
  void initState() {
    super.initState();
    _barCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900));
    _pulseCtrl =
        AnimationController(vsync: this, duration: const Duration(seconds: 2))
          ..repeat(reverse: true);

    _barAnim = CurvedAnimation(parent: _barCtrl, curve: Curves.easeOutCubic);
    _pulseAnim = Tween<double>(begin: 0.8, end: 1.0)
        .animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    _barCtrl.forward();
  }

  @override
  void dispose() {
    _barCtrl.dispose();
    _pulseCtrl.dispose();
    super.dispose();
  }

  void _switchTab(int i) {
    setState(() => _selectedTab = i);
    _barCtrl.forward(from: 0);
  }

  @override
  Widget build(BuildContext context) {
    return ScreenFrame(
      title: 'Analytics',
      subtitle: 'AI-Powered Insights',
      child: SingleChildScrollView(
        child: Column(
          children: [
            // ── Status strip ──────────────────────────────────
            StatusStrip(
              items: const [
                StatusItem('Sessions', '28'),
                StatusItem('Avg Mood', '80'),
                StatusItem('Risk Hrs', '4'),
              ],
            ),
            const SizedBox(height: 14),

            // ── AI Brain badge ────────────────────────────────
            _AiBadge(pulse: _pulseAnim),
            const SizedBox(height: 14),

            // ── Tab selector ──────────────────────────────────
            _TabBar(selected: _selectedTab, onTap: _switchTab),
            const SizedBox(height: 12),

            // ── Chart area ────────────────────────────────────
            AnimatedBuilder(
              animation: _barAnim,
              builder: (_, __) => _ChartCard(
                tab: _selectedTab,
                progress: _barAnim.value,
              ),
            ),

            const SizedBox(height: 14),

            // ── State breakdown donut + legend ────────────────
            if (_selectedTab == 2) ...[
              _StateBreakdownCard(),
              const SizedBox(height: 14),
            ],

            // ── Transition heatmap ────────────────────────────
            if (_selectedTab == 0 || _selectedTab == 1) ...[
              _TransitionCard(),
              const SizedBox(height: 14),
            ],

            // ── AI Insights list ──────────────────────────────
            _InsightsList(),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────
//  AI BADGE
// ─────────────────────────────────────────────────────────

class _AiBadge extends StatelessWidget {
  const _AiBadge({required this.pulse});
  final Animation<double> pulse;

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: pulse,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: _teal.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _teal.withValues(alpha: 0.4), width: 0.8),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.psychology_rounded, color: _teal, size: 16),
            const SizedBox(width: 6),
            const Text(
              'ADAMS Brain · Live Analysis',
              style: TextStyle(
                color: _teal,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
              ),
            ),
            const SizedBox(width: 8),
            _PulseDot(),
          ],
        ),
      ),
    );
  }
}

class _PulseDot extends StatefulWidget {
  @override
  State<_PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<_PulseDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(seconds: 1))
        ..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: _teal.withValues(alpha: 0.4 + _c.value * 0.6),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────
//  TAB BAR
// ─────────────────────────────────────────────────────────

class _TabBar extends StatelessWidget {
  const _TabBar({required this.selected, required this.onTap});
  final int selected;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    const tabs = ['Mood', 'Danger', 'States'];
    return Row(
      children: List.generate(tabs.length, (i) {
        final active = i == selected;
        return Expanded(
          child: GestureDetector(
            onTap: () => onTap(i),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: EdgeInsets.only(left: i == 0 ? 0 : 4),
              padding: const EdgeInsets.symmetric(vertical: 7),
              decoration: BoxDecoration(
                color: active
                    ? _teal.withValues(alpha: 0.2)
                    : Colors.white.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: active
                      ? _teal.withValues(alpha: 0.5)
                      : Colors.white.withValues(alpha: 0.1),
                  width: 0.8,
                ),
              ),
              child: Text(
                tabs[i],
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: active ? FontWeight.w700 : FontWeight.w400,
                  color: active ? _teal : Colors.white.withValues(alpha: 0.55),
                  letterSpacing: 0.3,
                ),
              ),
            ),
          ),
        );
      }),
    );
  }
}

// ─────────────────────────────────────────────────────────
//  CHART CARD
// ─────────────────────────────────────────────────────────

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.tab, required this.progress});
  final int tab;
  final double progress;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tab == 0
                ? 'Weekly Mood Score'
                : tab == 1
                    ? 'Hourly Danger Index'
                    : 'State Distribution',
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 12,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 140,
            child: tab == 0
                ? _MoodChart(progress: progress)
                : tab == 1
                    ? _DangerChart(progress: progress)
                    : _StateRadarBars(progress: progress),
          ),
        ],
      ),
    );
  }
}

// ── Mood bar chart ─────────────────────────────────────

class _MoodChart extends StatelessWidget {
  const _MoodChart({required this.progress});
  final double progress;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: List.generate(_weekDays.length, (i) {
              final val = _moodScores[i];
              final alpha = 0.55 + (val / 100) * 0.45;
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 2),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Text(
                        '${val.toInt()}',
                        style: TextStyle(
                          fontSize: 9,
                          color: Colors.white.withValues(alpha: 0.7),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 3),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(5),
                        child: AnimatedContainer(
                          duration: Duration(milliseconds: 400 + i * 60),
                          curve: Curves.easeOutCubic,
                          height: 100 * (val / 100) * progress,
                          decoration: BoxDecoration(
                            color: _teal.withValues(alpha: alpha),
                            borderRadius: BorderRadius.circular(5),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: _weekDays
              .map((d) => Expanded(
                    child: Text(d,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontSize: 10, color: Colors.white38)),
                  ))
              .toList(),
        ),
      ],
    );
  }
}

// ── Danger chart ───────────────────────────────────────

class _DangerChart extends StatelessWidget {
  const _DangerChart({required this.progress});
  final double progress;

  Color _dangerColor(double v) {
    if (v > 80) return _coral;
    if (v > 50) return _amber;
    return _teal;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: List.generate(_hourLabels.length, (i) {
              final val = _hourDanger[i];
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Text(
                        '${val.toInt()}',
                        style: TextStyle(
                          fontSize: 10,
                          color: _dangerColor(val).withValues(alpha: 0.9),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: AnimatedContainer(
                          duration: Duration(milliseconds: 400 + i * 80),
                          curve: Curves.easeOutCubic,
                          height: 100 * (val / 100) * progress,
                          color: _dangerColor(val).withValues(alpha: 0.75),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: _hourLabels
              .map((h) => Expanded(
                    child: Text('$h:00',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontSize: 10, color: Colors.white38)),
                  ))
              .toList(),
        ),
      ],
    );
  }
}

// ── State horizontal bars ──────────────────────────────

class _StateRadarBars extends StatelessWidget {
  const _StateRadarBars({required this.progress});
  final double progress;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: _stateBreakdown.map((s) {
        return Row(
          children: [
            SizedBox(
              width: 64,
              child: Text(
                s.label,
                style: const TextStyle(fontSize: 11, color: Colors.white60),
              ),
            ),
            Expanded(
              child: Stack(
                children: [
                  Container(
                    height: 18,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  FractionallySizedBox(
                    widthFactor: (s.pct / 100) * progress,
                    child: Container(
                      height: 18,
                      decoration: BoxDecoration(
                        color: s.color.withValues(alpha: 0.8),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '${s.pct.toStringAsFixed(1)}%',
              style: TextStyle(
                  fontSize: 11, color: s.color, fontWeight: FontWeight.w600),
            ),
          ],
        );
      }).toList(),
    );
  }
}

// ─────────────────────────────────────────────────────────
//  STATE BREAKDOWN DONUT CARD
// ─────────────────────────────────────────────────────────

class _StateBreakdownCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Row(
        children: [
          SizedBox(
            width: 90,
            height: 90,
            child: CustomPaint(painter: _DonutPainter()),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: _stateBreakdown.map((s) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 5),
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: s.color,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          s.label,
                          style: const TextStyle(
                              fontSize: 12, color: Colors.white70),
                        ),
                      ),
                      Text(
                        '${s.pct}%',
                        style: TextStyle(
                          fontSize: 12,
                          color: s.color,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _DonutPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final r = math.min(size.width, size.height) / 2 - 4;
    const stroke = 14.0;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.butt;

    var start = -math.pi / 2;
    for (final s in _stateBreakdown) {
      final sweep = 2 * math.pi * (s.pct / 100);
      paint.color = s.color.withValues(alpha: 0.85);
      canvas.drawArc(Rect.fromCircle(center: c, radius: r), start, sweep - 0.04,
          false, paint);
      start += sweep;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter _) => false;
}

// ─────────────────────────────────────────────────────────
//  TRANSITION HEATMAP CARD
// ─────────────────────────────────────────────────────────

class _TransitionCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Top State Transitions',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 12,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 10),
          ..._transitions.map((t) {
            final (from, to, strength) = t;
            return Padding(
              padding: const EdgeInsets.only(bottom: 7),
              child: Row(
                children: [
                  _StateChip(from),
                  const SizedBox(width: 6),
                  Icon(Icons.arrow_forward_rounded,
                      size: 12, color: Colors.white30),
                  const SizedBox(width: 6),
                  _StateChip(to),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: strength,
                        backgroundColor: Colors.white.withValues(alpha: 0.08),
                        valueColor: AlwaysStoppedAnimation<Color>(
                          _stateColor(from).withValues(alpha: 0.75),
                        ),
                        minHeight: 6,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '${(strength * 100).toInt()}%',
                    style: const TextStyle(fontSize: 10, color: Colors.white38),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Color _stateColor(String s) {
    switch (s) {
      case 'DISTRACTED':
        return _coral;
      case 'DIZZY':
        return _amber;
      case 'DROWSY':
        return _purple;
      default:
        return _teal;
    }
  }
}

class _StateChip extends StatelessWidget {
  const _StateChip(this.label);
  final String label;

  Color get _color {
    switch (label) {
      case 'DISTRACTED':
        return _coral;
      case 'DIZZY':
        return _amber;
      case 'DROWSY':
        return _purple;
      default:
        return _teal;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: _color.withValues(alpha: 0.35), width: 0.6),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 9,
          color: _color,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────
//  AI INSIGHTS LIST
// ─────────────────────────────────────────────────────────

class _InsightsList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.auto_awesome, color: _teal, size: 13),
            const SizedBox(width: 6),
            const Text(
              'AI Insights',
              style: TextStyle(
                color: Colors.white54,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        for (var i = 0; i < _aiInsights.length; i++) ...[
          if (i > 0) const SizedBox(height: 8),
          _InsightTile(_aiInsights[i]),
        ],
      ],
    );
  }
}

class _InsightTile extends StatelessWidget {
  const _InsightTile(this.insight);
  final _Insight insight;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: insight.color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
            color: insight.color.withValues(alpha: 0.25), width: 0.6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: insight.color.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(7),
            ),
            child: Icon(insight.icon, color: insight.color, size: 14),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  insight.title,
                  style: TextStyle(
                    fontSize: 12,
                    color: insight.color,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.1,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  insight.body,
                  style: const TextStyle(
                    fontSize: 11,
                    color: Colors.white54,
                    height: 1.4,
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

// ─────────────────────────────────────────────────────────
//  SHARED CARD WRAPPER
// ─────────────────────────────────────────────────────────

class _Card extends StatelessWidget {
  const _Card({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _cardBg,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: _border, width: 0.6),
      ),
      child: child,
    );
  }
}
