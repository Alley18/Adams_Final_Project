import logging
import time
from pathlib import Path

from hardware import HardwareController


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FSR_TEST] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "fsr_test.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("FSR_TEST")


def main() -> None:
    hardware = HardwareController()
    logger.info("Starting FSR test. Press Ctrl+C to stop.")

    if not hardware.gpio_enabled:
        logger.error("GPIO is unavailable. Run this test on the Raspberry Pi.")
        return

    try:
        while True:
            sample = hardware.read_fsr_sample()
            state = "ON" if sample["hands_on"] else "OFF"
            logger.info(
                "hands=%s pin=%s reads=%s high=%s low=%s active=%s/%s active_high=%s",
                state,
                sample["pin"],
                sample["reads"],
                sample["high_count"],
                sample["low_count"],
                sample["active_count"],
                sample["threshold"],
                sample["active_high"],
            )
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("FSR test stopped.")
    finally:
        hardware.cleanup()


if __name__ == "__main__":
    main()
