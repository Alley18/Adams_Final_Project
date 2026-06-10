import logging
import importlib
import time
from pathlib import Path
from typing import Any

try:
    GPIO: Any = importlib.import_module("RPi.GPIO")
except (ImportError, RuntimeError):
    GPIO = None


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

PINS_TO_CHECK = [5, 6, 13, 19, 26, 27]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GPIO_SCAN] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "gpio_input_scan.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("GPIO_SCAN")


def main() -> None:
    if GPIO is None:
        logger.error("GPIO is unavailable. Run this on the Raspberry Pi.")
        return

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    for pin in PINS_TO_CHECK:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    logger.info("Scanning BCM pins %s. Press/release the sensor; Ctrl+C stops.", PINS_TO_CHECK)

    try:
        while True:
            values = {
                pin: int(GPIO.input(pin) == GPIO.HIGH)
                for pin in PINS_TO_CHECK
            }
            logger.info("raw GPIO values: %s", values)
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("GPIO scan stopped.")
    finally:
        GPIO.cleanup()
        logger.info("GPIO cleanup complete.")


if __name__ == "__main__":
    main()
