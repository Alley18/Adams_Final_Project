"""
ADAMS Brain
===========
AI safety controller for the Advanced Driver Alertness Monitoring System.
Uses the Groq API (LLaMA 3.3-70B) to generate structured JSON safety
instructions from driver telemetry AND power a full conversational
driving assistant.

Authors : ADAMS Team
Version : 3.1.0
"""

import os
import json
import logging
import re
from typing import Literal

from groq import Groq
from dotenv import load_dotenv

logger = logging.getLogger("adams.brain")

_basedir = os.path.abspath(os.path.dirname(__file__))
for _candidate in (
    os.path.join(_basedir, ".env"),
    os.path.join(_basedir, "..", ".env"),
):
    if os.path.exists(_candidate):
        load_dotenv(_candidate)
        logger.debug("Loaded .env from %s", _candidate)
        break

AlertLevel = Literal["INFO", "WARNING", "DANGER", "ERROR"]
RouteType  = Literal["FASTEST", "SCENIC", "REST_STOP"]

# ---------------------------------------------------------------------------
# Safety alert prompt — structured JSON output only
# ---------------------------------------------------------------------------
_SAFETY_SYSTEM_PROMPT = """
You are the ADAMS Safety Controller (Advanced Driver Alertness Monitoring System).

Analyse the driver telemetry and return a JSON safety instruction following
these rules exactly:

| Driver state                              | level    | buzzer | route      |
|-------------------------------------------|----------|--------|------------|
| Sleepy / drowsy / eyes closed             | DANGER   | true   | REST_STOP  |
| Angry / stressed / fearful / distracted   | WARNING  | false  | SCENIC     |
| Neutral / happy / calm                    | INFO     | false  | FASTEST    |

Return ONLY valid JSON with exactly these four keys:
  "level"           – one of INFO | WARNING | DANGER | ERROR  (string)
  "message"         – a natural spoken alert, maximum 8 words  (string)
  "buzzer_active"   – whether to activate the buzzer           (boolean)
  "suggested_route" – one of FASTEST | SCENIC | REST_STOP      (string)
""".strip()

# ---------------------------------------------------------------------------
# Conversational assistant prompt
# ---------------------------------------------------------------------------
_ASSISTANT_SYSTEM_PROMPT = """
You are ADAMS, an in-car AI assistant. You are riding in the passenger seat.

MOST IMPORTANT RULE:
Answer the driver's EXACT question directly and concisely.
Never ignore what they asked. Never replace their question with safety advice
unless the telemetry shows DANGER level drowsiness.

Your response rules:
- 1 to 2 sentences maximum. You are being spoken aloud while someone drives.
- Answer the actual question first. Safety nudge can come at the end if needed.
- Be conversational and natural, not robotic.
- Never say "As an AI" or "I cannot" — just answer helpfully.
- If you don't know something (like exact local traffic), say so briefly and
  offer what you do know.

Telemetry context is provided for tone only:
- If drowsy: weave in a gentle rest suggestion AFTER answering.
- If angry/stressed: keep your tone calm and simple.
- If neutral/happy: be warm and natural.
- Never lecture. Never repeat safety warnings more than once per response.

Examples of good responses:
  Driver: "What's the capital of France?"
  ADAMS: "Paris — and it's about a 2-hour flight from London if you're ever headed there."

  Driver: "Play some jazz"
  ADAMS: "I'd love to — connecting to your music now. Some Miles Davis should set a good mood."

  Driver: "How far is the next rest stop?" (drowsy telemetry)
  ADAMS: "About 8 kilometres ahead on this road. Given how tired you seem, let's definitely pull in."

  Driver: "What time is it?"
  ADAMS: "I don't have direct clock access, but your dashboard should show it."
""".strip()

_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"level", "message", "buzzer_active", "suggested_route"}
)

_HOW_ARE_YOU_RE = re.compile(
    r"\b(how are you|how are you doing|how's it going|how is it going)\b",
    re.IGNORECASE,
)


class AdamsBrain:
    """
    Dual-mode AI brain for ADAMS.

    Safety mode  → generate_advice() → structured JSON alert
    Assistant mode → chat()          → natural spoken response
    """

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.5,       # slightly higher = more natural conversation
        max_tokens: int = 150,
        max_history_turns: int = 10,
    ) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file or environment variables."
            )

        self.client            = Groq(api_key=api_key)
        self.model             = model
        self.temperature       = temperature
        self.max_tokens        = max_tokens
        self.max_history_turns = max_history_turns

        self._history: list[dict] = []
        self._driver_context: str = "Driver state: normal."

        logger.info("AdamsBrain v3.1 ready (model=%s).", self.model)

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def update_driver_context(self, state: str | dict) -> None:
        if isinstance(state, dict):
            state = json.dumps(state)
        self._driver_context = state

    def clear_history(self) -> None:
        self._history = []
        logger.info("Conversation history cleared.")

    # ------------------------------------------------------------------
    # Safety mode
    # ------------------------------------------------------------------

    def generate_advice(self, driver_state: str | dict) -> str:
        if not driver_state:
            return self._default_response("INFO", "Scanning environment.", False, "FASTEST")

        if isinstance(driver_state, dict):
            driver_state = json.dumps(driver_state)

        if len(driver_state.strip()) < 3:
            return self._default_response("INFO", "Scanning environment.", False, "FASTEST")

        self.update_driver_context(driver_state)

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SAFETY_SYSTEM_PROMPT},
                    {"role": "user",   "content": f"Driver Telemetry: {driver_state}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,        # safety mode stays deterministic
                max_tokens=self.max_tokens,
            )
            raw: str = completion.choices[0].message.content
            return self._validate_response(raw)

        except Exception:
            logger.exception("Groq API call failed (safety mode)")
            return self._default_response("ERROR", "Safety AI offline.", False, "FASTEST")

    # ------------------------------------------------------------------
    # Assistant mode
    # ------------------------------------------------------------------

    def chat(self, driver_utterance: str) -> str:
        """
        Answer the driver's question naturally.

        The telemetry context is passed as a system note — NOT as the
        main content — so the model focuses on the driver's actual words.
        """
        if not driver_utterance or not driver_utterance.strip():
            return "I didn't catch that — could you say it again?"

        quick_reply = self._quick_reply(driver_utterance)
        if quick_reply:
            self._history.append({"role": "user", "content": driver_utterance})
            self._history.append({"role": "assistant", "content": quick_reply})
            logger.info("Brain quick reply: %r", quick_reply)
            return quick_reply

        # Telemetry goes into the system layer, not mixed into the user message.
        # This is the key fix: before, context was prepended to the user message
        # which caused the model to treat the telemetry as the primary input.
        system_with_context = (
            _ASSISTANT_SYSTEM_PROMPT
            + f"\n\n[Current driver telemetry: {self._driver_context}]"
        )

        # User message is ONLY what the driver actually said
        self._history.append({"role": "user", "content": driver_utterance})

        # Trim history
        max_messages = self.max_history_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_with_context},
                    *self._history,
                ],
                temperature=self.temperature,
                max_tokens=120,          # short enough for natural spoken output
            )

            reply: str = completion.choices[0].message.content.strip()
            self._history.append({"role": "assistant", "content": reply})

            logger.info("Brain chat reply: %r", reply[:80])
            return reply

        except Exception:
            logger.exception("Groq API call failed (assistant mode)")
            fallback = "I'm having trouble right now. Keep your eyes on the road."
            self._history.append({"role": "assistant", "content": fallback})
            return fallback

    def _quick_reply(self, driver_utterance: str) -> str:
        """
        Answer tiny social prompts locally so basic conversation still works
        even if the cloud model is slow or temporarily unavailable.
        """
        if _HOW_ARE_YOU_RE.search(driver_utterance):
            return "I'm doing well, thanks for asking. I'm here and ready to help while you drive."

        return ""

    # ------------------------------------------------------------------
    # Notification filter
    # ------------------------------------------------------------------

    def filter_notification(self, driver_level: AlertLevel, notification_text: str) -> str:
        if driver_level in ("DANGER", "WARNING"):
            return "[BLOCKED] High-risk state: focus on the road."
        return f"[ALLOWED] {notification_text}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_response(self, raw: str) -> str:
        try:
            parsed: dict = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Brain returned non-JSON: %r", raw[:120])
            return self._default_response("WARNING", "Check driver status.", False, "FASTEST")

        missing = _REQUIRED_KEYS - parsed.keys()
        if missing:
            logger.warning("Brain JSON missing keys %s", missing)
            return self._default_response("WARNING", "Check driver status.", False, "FASTEST")

        return raw

    @staticmethod
    def _default_response(
        level: AlertLevel,
        message: str,
        buzzer_active: bool,
        suggested_route: RouteType,
    ) -> str:
        return json.dumps({
            "level":          level,
            "message":        message,
            "buzzer_active":  buzzer_active,
            "suggested_route":suggested_route,
        })


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    brain = AdamsBrain()
    print("🧠 ADAMS Brain v3.1 — smoke test\n" + "=" * 60)

    # Safety mode
    print("\n[SAFETY MODE]")
    for case in [
        "Eye openness: 5%, Drowsy: True, Emotion: Tired",
        "Eye openness: 85%, Drowsy: False, Emotion: Angry",
        "Eye openness: 95%, Drowsy: False, Emotion: Happy",
    ]:
        data = json.loads(brain.generate_advice(case))
        print(f"  [{data['level']}] {data['message']} | Buzzer: {data['buzzer_active']}")

    # Assistant mode — direct questions
    print("\n[ASSISTANT MODE]")
    brain.update_driver_context("Eye openness: 90%, Drowsy: False, Emotion: Neutral")
    questions = [
        "What's the capital of Korea?",
        "Tell me a quick joke",
        "How far is Gangnam from here?",
    ]
    for q in questions:
        print(f"  Driver : {q}")
        print(f"  ADAMS  : {brain.chat(q)}\n")
