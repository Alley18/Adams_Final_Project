import logging
import time
from pathlib import Path

from hardware import HardwareController


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BUZZER_TEST] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "buzzer_test.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("BUZZER_TEST")


def main() -> None:
    hardware = HardwareController()

    if not hardware.gpio_enabled:
        logger.error("GPIO is unavailable. Run this on the Raspberry Pi.")
        return

    try:
        for state in ("DEFAULT", "DISTRACTED", "DIZZY", "DROWSY", "EMERGENCY"):
            logger.info("Testing buzzer state: %s", state)
            hardware.buzz_alert(state)
            time.sleep(2.2)
    finally:
        hardware.cleanup()


if __name__ == "__main__":
    main()
