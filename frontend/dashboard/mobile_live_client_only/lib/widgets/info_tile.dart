import 'package:flutter/material.dart';

class InfoTile extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final bool compact;

  const InfoTile.list({super.key, required this.title, required this.subtitle, required this.icon, required this.color}) : compact = false;
  const InfoTile.card({super.key, required this.title, required String value, required this.icon, required this.color}) : subtitle = value, compact = true;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(20),
      ),
      child: compact
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, color: color),
                const SizedBox(height: 12),
                Text(title, style: const TextStyle(color: Colors.white70)),
                const SizedBox(height: 8),
                Text(subtitle, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
              ],
            )
          : Row(
              children: [
                CircleAvatar(backgroundColor: color.withOpacity(0.16), child: Icon(icon, color: color)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
                      const SizedBox(height: 4),
                      Text(subtitle, style: const TextStyle(color: Colors.white70)),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}
