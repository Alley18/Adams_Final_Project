"""
ADAMS Voice
===========
Stable Windows Voice Engine.

Uses:
- win32com SAPI
- proper COM initialization
- thread-safe queue
- reliable speech output

Changes from v4.0:
  - Added is_speaking property so vision_node.py can check voice state.
  - alert() drains queue before inserting so safety alerts aren't buried.
  - Queue items are now 3-tuples (priority, counter, text) — fixes
    PriorityQueue crash when two items share the same priority level
    (Python tries to compare the text strings as a tiebreaker, which
    errors on non-comparable types).

Version: 4.1 Stable
"""

import queue
import threading
import logging
import itertools
import time
import pythoncom
import win32com.client

logger = logging.getLogger("adams.voice")

PRIORITY_ALERT  = 0
PRIORITY_NORMAL = 1

# Unique counter so PriorityQueue never falls back to comparing text strings
_counter = itertools.count()


class AdamsVoice:

    def __init__(self):
        self._queue    = queue.PriorityQueue()
        self._running  = True
        self._is_speaking = False          # ← NEW: tracked inside worker

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="adams-voice",
        )
        self._thread.start()

        logger.info("AdamsVoice ready.")
        print("✅ ADAMS Voice Engine: Ready")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        """True while SAPI is actively outputting audio."""
        return self._is_speaking

    def speak(self, text: str):
        """Queue a normal-priority response (non-blocking)."""
        if not text:
            return
        print(f"🗣️ ADAMS Speaking: {text}")
        self._queue.put((PRIORITY_NORMAL, next(_counter), text))

    def alert(self, text: str):
        """
        High-priority alert — drains any queued normal speech first
        so the alert is heard immediately.
        """
        if not text:
            return
        print(f"🚨 ADAMS Alert: {text}")

        # Drain queued normal speech so alert isn't delayed
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

        self._queue.put((PRIORITY_ALERT, next(_counter), text))

    def stop(self):
        self._running = False
        print("🛑 ADAMS Voice stopped.")

    def wait_until_done(self, timeout: float = 15.0) -> bool:
        """Wait until queued speech has been spoken or timeout expires."""
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._queue.empty() and not self._is_speaking:
                return True
            time.sleep(0.05)

        return False

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker(self):
        try:
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            print("✅ Windows SAPI Voice Ready")
        except Exception as e:
            print(f"❌ Voice init failed: {e}")
            return

        while self._running:
            try:
                priority, _, text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._is_speaking = True
            try:
                print(f"🔊 SPEAKING: {text}")
                speaker.Speak(text)
                print("✅ FINISHED SPEAKING")
            except Exception as e:
                logger.error("Voice error: %s", e)
            finally:
                self._is_speaking = False
                self._queue.task_done()

        pythoncom.CoUninitialize()
