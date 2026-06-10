import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../services/assistant_service.dart';
import '../widgets/big_circle_button.dart';
import '../widgets/screen_frame.dart';

class CoPilotScreen extends StatefulWidget {
  const CoPilotScreen({super.key});

  @override
  State<CoPilotScreen> createState() => _CoPilotScreenState();
}

class _CoPilotScreenState extends State<CoPilotScreen> {
  final AssistantService assistant = AssistantService();
  final SpeechToText speech = SpeechToText();
  final FlutterTts tts = FlutterTts();
  final TextEditingController promptController = TextEditingController();

  // FIX: ScrollController so we can auto-scroll to the latest message
  final ScrollController _scrollController = ScrollController();

  final List<ChatMessage> messages = [
    const ChatMessage(
      role: ChatRole.assistant,
      text: 'I am ready. Tap the mic and tell me what you need.',
    ),
  ];

  bool speechReady = false;
  bool isListening = false;
  bool isThinking = false;
  bool isSpeaking = false;
  String liveSpeech = '';

  @override
  void initState() {
    super.initState();
    setupVoice();
  }

  @override
  void dispose() {
    promptController.dispose();
    _scrollController.dispose();
    speech.stop();
    tts.stop();
    super.dispose();
  }

  Future<void> setupVoice() async {
    speechReady = await speech.initialize(
      onStatus: handleSpeechStatus,
      onError: (_) {
        if (mounted) setState(() => isListening = false);
      },
    );

    await tts.setLanguage('en-US');
    await tts.setSpeechRate(0.48);
    await tts.setPitch(1.08);
    await tts.awaitSpeakCompletion(true);
    await selectFemaleVoice();

    tts.setStartHandler(() {
      if (mounted) setState(() => isSpeaking = true);
    });
    tts.setCompletionHandler(() {
      if (mounted) setState(() => isSpeaking = false);
    });
    tts.setCancelHandler(() {
      if (mounted) setState(() => isSpeaking = false);
    });

    if (mounted) setState(() {});
  }

  Future<void> selectFemaleVoice() async {
    final voices = await tts.getVoices;
    if (voices is! List) return;

    for (final voice in voices) {
      if (voice is! Map) continue;
      final name = voice['name']?.toString().toLowerCase() ?? '';
      final locale = voice['locale']?.toString().toLowerCase() ?? '';
      final looksFemale = name.contains('female') ||
          name.contains('woman') ||
          name.contains('samantha') ||
          name.contains('jenny') ||
          name.contains('aria') ||
          name.contains('zira');

      if (locale.startsWith('en') && looksFemale) {
        await tts.setVoice({
          'name': voice['name'].toString(),
          'locale': voice['locale'].toString(),
        });
        return;
      }
    }
  }

  void handleSpeechStatus(String status) {
    if (!mounted) return;
    if (status == 'done' || status == 'notListening') {
      setState(() => isListening = false);
    }
  }

  Future<void> toggleListening() async {
    if (isThinking) return;

    if (isSpeaking) {
      await tts.stop();
      setState(() => isSpeaking = false);
    }

    if (!speechReady) {
      showMessage('Microphone is not ready. Check app permissions.');
      return;
    }

    if (isListening) {
      await speech.stop();
      setState(() => isListening = false);
      if (liveSpeech.trim().isNotEmpty) {
        await sendPrompt(liveSpeech);
      }
      return;
    }

    setState(() {
      liveSpeech = '';
      isListening = true;
    });

    await speech.listen(
      pauseFor: const Duration(seconds: 3),
      listenFor: const Duration(seconds: 18),
      listenOptions: SpeechListenOptions(listenMode: ListenMode.confirmation),
      onResult: handleSpeechResult,
    );
  }

  void handleSpeechResult(SpeechRecognitionResult result) {
    setState(() => liveSpeech = result.recognizedWords);

    if (result.finalResult && result.recognizedWords.trim().isNotEmpty) {
      speech.stop();
      sendPrompt(result.recognizedWords);
    }
  }

  Future<void> sendPrompt([String? prompt]) async {
    final text = (prompt ?? promptController.text).trim();
    if (text.isEmpty || isThinking) return;

    await speech.stop();
    await tts.stop();

    setState(() {
      isListening = false;
      isSpeaking = false;
      isThinking = true;
      liveSpeech = '';
      messages.add(ChatMessage(role: ChatRole.driver, text: text));
      promptController.clear();
    });

    // Scroll to bottom after driver message renders
    _scrollToBottom();

    final reply = await assistant.ask(text);

    if (!mounted) return;

    setState(() {
      messages.add(ChatMessage(role: ChatRole.assistant, text: reply));
      isThinking = false;
    });

    // Scroll to bottom after assistant reply renders
    _scrollToBottom();

    await tts.speak(reply);
  }

  // FIX: scroll to the bottom of the chat list
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void showMessage(String text) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    // FIX: removed "Setup needed" from being spoken — only shown visually
    final assistantState = isThinking
        ? 'Thinking'
        : isListening
            ? 'Listening'
            : isSpeaking
                ? 'Speaking'
                : 'Ready';

    return ScreenFrame(
      title: 'Co-Pilot',
      subtitle: 'ADAMS voice assistant',
      child: Column(
        children: [
          AssistantHeader(
            state: assistantState,
            isOnline: assistant.isConfigured,
            heardText: liveSpeech,
          ),
          const SizedBox(height: 14),
          Expanded(
            child: ListView.separated(
              // FIX: attach our scroll controller
              controller: _scrollController,
              padding: const EdgeInsets.only(bottom: 16),
              itemCount: messages.length + (isThinking ? 1 : 0),
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                if (index == messages.length) {
                  return const AssistantBubble(text: 'Give me a second…');
                }
                final message = messages[index];
                return message.role == ChatRole.driver
                    ? DriverBubble(text: message.text)
                    : AssistantBubble(text: message.text);
              },
            ),
          ),
          BigCircleButton(
            icon: isListening ? Icons.hearing : Icons.mic,
            label: isListening ? 'Listening' : 'Talk',
            color: isListening
                ? const Color(0xFFE6B325)
                : const Color(0xFFFF9F1C),
            onPressed: isThinking ? null : toggleListening,
          ),
          const SizedBox(height: 16),
          CommandGrid(
            commands: const [
              DriverCommand(Icons.local_gas_station, 'Fuel'),
              DriverCommand(Icons.coffee, 'Coffee'),
              DriverCommand(Icons.music_note, 'Music'),
              DriverCommand(Icons.newspaper, 'News'),
            ],
            onCommandSelected: (command) => sendPrompt(command.prompt),
          ),
          const SizedBox(height: 12),
          PromptBar(
            controller: promptController,
            enabled: !isThinking,
            onSubmitted: sendPrompt,
          ),
        ],
      ),
    );
  }
}

// ── Widgets ─────────────────────────────────────────────────────────────────

class AssistantHeader extends StatelessWidget {
  const AssistantHeader({
    required this.state,
    required this.isOnline,
    required this.heardText,
    super.key,
  });

  final String state;
  final bool isOnline;
  final String heardText;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF171B21).withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: const Color(0xFFFF9F1C).withValues(alpha: 0.22),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.24),
            blurRadius: 16,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: isOnline
                  ? const Color(0xFFFF9F1C)
                  : const Color(0xFFE6B325),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: (isOnline
                          ? const Color(0xFFFF9F1C)
                          : const Color(0xFFE6B325))
                      .withValues(alpha: 0.45),
                  blurRadius: 12,
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              heardText.isEmpty ? state : heardText,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Icon(
            isOnline ? Icons.cloud_done : Icons.key,
            color: const Color(0xFFFFC857),
          ),
        ],
      ),
    );
  }
}

class PromptBar extends StatelessWidget {
  const PromptBar({
    required this.controller,
    required this.enabled,
    required this.onSubmitted,
    super.key,
  });

  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<String> onSubmitted;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            enabled: enabled,
            minLines: 1,
            maxLines: 3,
            textInputAction: TextInputAction.send,
            onSubmitted: onSubmitted,
            decoration: const InputDecoration(
              hintText: 'Ask ADAMS…',
              border: OutlineInputBorder(),
              contentPadding:
                  EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            ),
          ),
        ),
        const SizedBox(width: 8),
        IconButton.filled(
          onPressed: enabled ? () => onSubmitted(controller.text) : null,
          icon: const Icon(Icons.send),
          tooltip: 'Send',
        ),
      ],
    );
  }
}

class AssistantBubble extends StatelessWidget {
  const AssistantBubble({required this.text, super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 340),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: const Color(0xFF171B21),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: const Color(0xFFFF9F1C).withValues(alpha: 0.16),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              text,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.86),
                height: 1.35,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class DriverBubble extends StatelessWidget {
  const DriverBubble({required this.text, super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 320),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: const Color(0xFFFF9F1C).withValues(alpha: 0.18),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: const Color(0xFFFF9F1C).withValues(alpha: 0.42),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              text,
              style: const TextStyle(
                color: Color(0xFFFFE6B8),
                height: 1.35,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class CommandGrid extends StatelessWidget {
  const CommandGrid({
    required this.commands,
    required this.onCommandSelected,
    super.key,
  });

  final List<DriverCommand> commands;
  final ValueChanged<DriverCommand> onCommandSelected;

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: commands.length,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 2.6,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
      ),
      itemBuilder: (context, index) {
        final command = commands[index];
        return FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF171B21),
            foregroundColor: const Color(0xFFFFC857),
            side: BorderSide(
              color: const Color(0xFFFF9F1C).withValues(alpha: 0.22),
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          onPressed: () => onCommandSelected(command),
          icon: Icon(command.icon),
          label: Text(command.label),
        );
      },
    );
  }
}

class DriverCommand {
  const DriverCommand(this.icon, this.label);
  final IconData icon;
  final String label;

  String get prompt => switch (label) {
        'Fuel' => 'Find a safe fuel stop along my drive.',
        'Coffee' => 'Find a quick coffee stop that will not add much time.',
        'Music' => 'Pick a calm driving music mood for me.',
        'News' => 'Give me a short, low-distraction news briefing.',
        _ => 'Help me with $label while I drive.',
      };
}

class ChatMessage {
  const ChatMessage({required this.role, required this.text});
  final ChatRole role;
  final String text;
}

enum ChatRole { driver, assistant }
