import 'package:flutter/material.dart';

class ScreenFrame extends StatelessWidget {
  const ScreenFrame({
    required this.title,
    required this.subtitle,
    required this.child,
    this.backgroundColor,
    super.key,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final baseColor = backgroundColor ?? const Color(0xFF0C0F13);
    final isAlert = backgroundColor != null;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: baseColor,
        gradient: isAlert
            ? null
            : const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFF18110B),
                  Color(0xFF0C0F13),
                  Color(0xFF10151B),
                ],
              ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: isAlert
                      ? Colors.white.withValues(alpha: 0.22)
                      : const Color(0xFFFF9F1C).withValues(alpha: 0.24),
                ),
              ),
              child: Row(
                children: [
                  Container(
                    width: 4,
                    height: 44,
                    decoration: BoxDecoration(
                      color: isAlert ? Colors.white : const Color(0xFFFF9F1C),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style:
                              Theme.of(context).textTheme.headlineSmall?.copyWith(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 0,
                                  ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          subtitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              Theme.of(context).textTheme.titleSmall?.copyWith(
                                    color: Colors.white.withValues(alpha: 0.68),
                                    letterSpacing: 0,
                                  ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            Expanded(child: child),
          ],
        ),
      ),
    );
  }
}
