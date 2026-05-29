"""
ADAMS Ears
==========
Stable wake-word based speech recognition engine.

Version : 4.0.0

Features:
- Real wake-word architecture
- Conversation mode
- Automatic timeout
- Better pause/resume behavior
- Cleaner threading
- Reduced false recognition
"""

import time
import threading
import logging
import re
import speech_recognition as sr

logger = logging.getLogger("adams.ears")

WAKE_WORDS = {
    "hey adams",
    "hey addams",
    "adams",
    "addams",
    "hey adam",
    "adam",
}


class AdamsEars:

    def __init__(
        self,
        energy_threshold: int = 300,
        dynamic_energy: bool = True,
        ambient_duration: float = 1.0,
        mic_index: int = None,
        list_microphones: bool = False,
    ) -> None:

        self.recognizer = sr.Recognizer()

        # Recognition settings
        self.recognizer.energy_threshold = energy_threshold
        self.recognizer.dynamic_energy_threshold = dynamic_energy
        self.recognizer.pause_threshold = 0.8
        self.recognizer.non_speaking_duration = 0.4

        self._ambient_duration = ambient_duration
        self._mic_index = mic_index

        self._running = False
        self._paused = threading.Event()
        self._thread = None

        self.callback = None

        # Conversation state
        self.conversation_active = False
        self.last_conversation_time = 0

        if list_microphones:
            self._print_microphones()

        print("✅ ADAMS Ears: Ready")

    # ==========================================================
    # Lifecycle
    # ==========================================================

    def start(self, callback) -> None:

        if self._running:
            logger.warning("AdamsEars already running.")
            return

        self.callback = callback
        self._running = True

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="adams-ears",
        )

        self._thread.start()

        logger.info("AdamsEars continuous listener started.")

        print("👂 ADAMS waiting for wake word...")

    def stop(self) -> None:

        self._running = False

        logger.info("AdamsEars listener stopped.")

        print("🛑 ADAMS Ears stopped.")

    def pause(self) -> None:

        self._paused.set()

        print("⏸️ ADAMS Ears paused.")

    def resume(self) -> None:

        self._paused.clear()

        print("▶️ ADAMS Ears resumed.")

    # ==========================================================
    # MAIN LOOP
    # ==========================================================

    def _listen_loop(self) -> None:

        while self._running:

            # ------------------------------------------
            # PAUSED
            # ------------------------------------------

            if self._paused.is_set():
                time.sleep(0.2)
                continue

            # ==========================================
            # WAKE MODE
            # ==========================================

            if not self.conversation_active:

                heard = self._capture(
                    timeout=None,
                    phrase_time_limit=3,
                )

                if not heard:
                    continue

                print(f"🧠 Heard: {heard}")

                command = self._command_after_wake_word(heard)

                if command is None:
                    continue

                print("🔔 Wake word detected")

                self.conversation_active = True
                self.last_conversation_time = time.time()

                # Inline command
                if command:

                    print(f"👤 Driver said: {command}")

                    self._fire_callback(command)

                continue

            # ==========================================
            # CONVERSATION MODE
            # ==========================================

            print("🎧 Conversation mode active")

            command = self._capture(
                timeout=6,
                phrase_time_limit=8,
            )

            if command:

                self.last_conversation_time = time.time()

                print(f"👤 Driver: {command}")

                self._fire_callback(command)

            # ==========================================
            # TIMEOUT
            # ==========================================

            if (
                time.time() - self.last_conversation_time
            ) > 10:

                print("💤 Leaving conversation mode")

                self.conversation_active = False

    # ==========================================================
    # CALLBACK
    # ==========================================================

    def _fire_callback(self, text: str) -> None:

        if not self.callback:
            return

        if not text.strip():
            return

        try:

            logger.info(
                "Firing callback with text: %r",
                text,
            )

            self.callback(text)

        except Exception as exc:

            logger.exception(
                "Callback failed: %s",
                exc,
            )

    @staticmethod
    def _command_after_wake_word(text: str) -> str | None:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()

        for wake in sorted(WAKE_WORDS, key=len, reverse=True):
            match = re.search(rf"\b{re.escape(wake)}\b", normalized)
            if match:
                return normalized[match.end():].strip(" ,.!?")

        return None

    # ==========================================================
    # AUDIO CAPTURE
    # ==========================================================

    def _capture(
        self,
        timeout=None,
        phrase_time_limit=None,
    ) -> str:

        if self._paused.is_set():
            return ""

        try:

            mic = (
                sr.Microphone(device_index=self._mic_index)
                if self._mic_index is not None
                else sr.Microphone()
            )

            with mic as source:

                self.recognizer.adjust_for_ambient_noise(
                    source,
                    duration=self._ambient_duration,
                )

                print("\n🎤 Listening...")

                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

            text = self.recognizer.recognize_google(audio)

            logger.info(
                "Recognized speech: %r",
                text,
            )

            return text.lower().strip()

        except sr.WaitTimeoutError:
            return ""

        except sr.UnknownValueError:
            return ""

        except sr.RequestError as exc:

            logger.error(
                "Speech API error: %s",
                exc,
            )

            return ""

        except Exception as exc:

            logger.exception(
                "Unexpected microphone error: %s",
                exc,
            )

            return ""

    # ==========================================================
    # UTILITIES
    # ==========================================================

    @staticmethod
    def _print_microphones() -> None:

        print("\n🎙️ Available microphones:")

        try:

            for i, name in enumerate(
                sr.Microphone.list_microphone_names()
            ):
                print(f"  [{i}] {name}")

        except Exception as exc:

            print(
                f"❌ Could not list microphones: {exc}"
            )

        print()


# ==========================================================
# Standalone Test
# ==========================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    ears = AdamsEars()

    def handle(text):
        print(f"\n✅ CALLBACK: {text}\n")

    ears.start(callback=handle)

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        ears.stop()

        print("👋 Goodbye.")
