from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

from ai_engine.brain import AdamsBrain
from ai_engine.logger import log_event
from ai_engine.adams_voice import AdamsVoice


SCENARIOS = [
    "Eye openness: 95%, Emotion: Neutral, Gaze: Forward",
    "Eye openness: 5%, Yawning: YES, Duration: 3s",
    "Eye openness: 85%, Emotion: Angry, Gaze: Road",
    "Eye openness: 90%, Emotion: Happy, Gaze: Road",
]


def run_scenarios(use_voice: bool = False) -> None:
    adams = AdamsBrain()
    voice = AdamsVoice() if use_voice else None

    print("ADAMS cognitive monitoring smoke test")
    print("=" * 50)

    for detection in SCENARIOS:
        raw_response = adams.generate_advice(detection)
        log_event(detection, raw_response)

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON response for {detection!r}: {exc}")
            continue

        level = data.get("level", "UNKNOWN")
        message = data.get("message", "No message")
        buzzer_active = bool(data.get("buzzer_active", False))
        suggested_route = data.get("suggested_route", "N/A")

        print(f"\n[DATA] {detection}")
        print(f"[{level}] {message}")
        print(f"Route: {suggested_route}")
        print(f"Buzzer active: {buzzer_active}")
        print(adams.filter_notification(level, "New Text: Where are you?"))
        print("-" * 50)

        if voice:
            voice.alert(message) if buzzer_active else voice.speak(message)
            voice.wait_until_done(timeout=10.0)

        time.sleep(1)

    if voice:
        voice.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ADAMS AI safety smoke scenarios.")
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Speak scenario messages with the Windows SAPI voice engine.",
    )
    args = parser.parse_args()
    run_scenarios(use_voice=args.voice)


if __name__ == "__main__":
    main()
