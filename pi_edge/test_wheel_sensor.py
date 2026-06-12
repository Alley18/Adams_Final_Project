"""
test_wheel_sensor.py – Focused FSR Wheel Contact Detection Test

Continuously reads the wheel sensor and displays:
- Real-time ON/OFF state
- Raw GPIO readings and debounce breakdown
- State change events with timestamps
- Threshold and configuration details

Usage:
    python test_wheel_sensor.py

Press Ctrl+C to stop.
"""

import logging
import time
from pathlib import Path
import hardware as hw_module
from hardware import HardwareController

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WHEEL_TEST] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "wheel_test.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("WHEEL_TEST")


def main() -> None:
    hardware = HardwareController()

    if not hardware.gpio_enabled:
        logger.error(
            "GPIO is unavailable on this machine.\n"
            "This test MUST run on a Raspberry Pi with RPi.GPIO installed.\n"
            "Command: pip install RPi.GPIO"
        )
        return

    logger.info("=" * 70)
    logger.info("WHEEL SENSOR TEST - Real-Time FSR Detection")
    logger.info("=" * 70)
    logger.info(f"FSR Pin: {hw_module.FSR_PIN}")
    logger.info(f"Active High: {hw_module.FSR_ACTIVE_HIGH}")
    logger.info(f"Debounce Reads: {hw_module.FSR_DEBOUNCE_READS}")
    logger.info(f"Threshold Count: {hw_module.FSR_THRESHOLD_COUNT}")
    logger.info("=" * 70)
    logger.info("Press Ctrl+C to stop.\n")

    last_state = None
    state_start_time = None
    reading_count = 0

    try:
        while True:
            sample = hardware.read_fsr_sample()
            reading_count += 1
            current_state = sample["hands_on"]
            now = time.time()

            # ── State change detected ──────────────────────────────
            if current_state != last_state:
                if last_state is not None:
                    held_duration = now - state_start_time
                    action = "👋 HANDS OFF" if not current_state else "✋ HANDS ON"
                    logger.warning(
                        f"{action} wheel – held for {held_duration:.2f}s"
                    )

                last_state = current_state
                state_start_time = now

            # ── Current reading display ────────────────────────────
            state_label = "ON ✓" if current_state else "OFF ✗"
            held_duration = now - state_start_time if state_start_time else 0.0
            reads_str = "".join(str(r) for r in sample["reads"])

            logger.info(
                f"[{reading_count:04d}] STATE={state_label:6s} | "
                f"held={held_duration:6.2f}s | "
                f"reads=[{reads_str}] | "
                f"high={sample['high_count']}/5 low={sample['low_count']}/5 | "
                f"active={sample['active_count']}/{sample['threshold']}"
            )

            time.sleep(0.2)

    except KeyboardInterrupt:
        logger.info("\n" + "=" * 70)
        logger.info(f"Test stopped. Total readings: {reading_count}")
        logger.info("=" * 70)

    finally:
        hardware.cleanup()


if __name__ == "__main__":
    main()
