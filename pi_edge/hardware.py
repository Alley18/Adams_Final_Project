import importlib
import logging
import os
import time
from collections import deque
from typing import Any

try:
    GPIO: Any = importlib.import_module("RPi.GPIO")
except (ImportError, RuntimeError):
    GPIO = None

try:
    SMBus: Any = importlib.import_module("smbus2").SMBus
except ImportError:
    SMBus = None

try:
    from luma.core.interface.serial import spi, noop
    from luma.core.render import canvas
    from luma.led_matrix.device import max7219
    from PIL import ImageFont
except ImportError:
    spi = None
    noop = None
    canvas = None
    max7219 = None
    ImageFont = None

logger = logging.getLogger("ADAMS")

# =============================
# Pins
# =============================

# IMPORTANT:
# Your buzzer test worked on GPIO18
BUZZER_PIN = 18

BUTTON_PIN = int(
    os.getenv("ADAMS_FSR_PIN", "5")
)

FSR_PIN = BUTTON_PIN

# =============================
# LCD I2C Config
# =============================

LCD_I2C_ADDRESS = 0x27
LCD_I2C_BUS = 1

LCD_CHR = 1
LCD_CMD = 0

LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0

LCD_BACKLIGHT_ON = 0x08
LCD_BACKLIGHT_OFF = 0x00

ENABLE_BIT = 0b00000100

E_PULSE = 0.0005
E_DELAY = 0.0005

# =============================
# Config
# =============================

BUZZ_COOLDOWN_SECONDS = 0.5

FSR_DEBOUNCE_READS = 5
FSR_DEBOUNCE_DELAY = 0.01
FSR_THRESHOLD_COUNT = 3

FSR_STABLE_WINDOW = int(
    os.getenv(
        "ADAMS_FSR_STABLE_WINDOW",
        "5",
    )
)

FSR_STABLE_THRESHOLD = int(
    os.getenv(
        "ADAMS_FSR_STABLE_THRESHOLD",
        "4",
    )
)

FSR_ACTIVE_HIGH = (
    os.getenv(
        "ADAMS_FSR_ACTIVE_HIGH",
        "0",
    )
    != "0"
)

FSR_LOG_INTERVAL_SECONDS = float(
    os.getenv(
        "ADAMS_FSR_LOG_INTERVAL_SECONDS",
        "5",
    )
)

MAX7219_CASCADE = int(
    os.getenv(
        "ADAMS_MAX7219_CASCADE",
        "4",
    )
)

MAX7219_ROTATE = int(
    os.getenv(
        "ADAMS_MAX7219_ROTATE",
        "0",
    )
)

MAX7219_BLOCK_ORIENTATION = int(
    os.getenv(
        "ADAMS_MAX7219_BLOCK_ORIENTATION",
        "90",
    )
)

MAX7219_SPI_PORT = int(
    os.getenv(
        "ADAMS_MAX7219_SPI_PORT",
        "0",
    )
)

MAX7219_SPI_DEVICE = int(
    os.getenv(
        "ADAMS_MAX7219_SPI_DEVICE",
        "0",
    )
)

BUZZ_PATTERNS = {
    "DISTRACTED": [
        (0.15, 0.10),
        (0.15, 0.10),
    ],
    "DIZZY": [
        (0.25, 0.10),
        (0.25, 0.10),
        (0.25, 0.10),
    ],
    "DROWSY": [
        (0.60, 0.10),
        (0.60, 0.00),
    ],
    "EMERGENCY": [
        (0.10, 0.05),
        (0.10, 0.05),
        (0.10, 0.05),
        (0.10, 0.05),
        (0.10, 0.05),
        (0.50, 0.10),
    ],
    "DEFAULT": [
        (0.30, 0.00),
    ],
}


class LCD_I2C:
    def __init__(
        self,
        address=LCD_I2C_ADDRESS,
        bus=LCD_I2C_BUS,
    ):
        self._addr = address
        self._backlight = (
            LCD_BACKLIGHT_ON
        )
        self._bus = None
        self._ok = False

        if SMBus is None:
            logger.warning(
                "smbus2 not installed"
            )
            return

        try:
            self._bus = SMBus(bus)
            self._ok = True
        except Exception as exc:
            logger.error(
                f"LCD init failed: {exc}"
            )

    def clear(self):
        pass

    def show_help(self):
        logger.warning(
            "LCD HELP shown"
        )

    def show_message(
        self,
        line1,
        line2="",
    ):
        pass

    def cleanup(self):
        pass


class HardwareController:

    def __init__(self):
        self.last_buzz_time = 0.0

        self.gpio_enabled = (
            GPIO is not None
        )

        self.last_fsr_sample = None

        self._last_hands_on_wheel = (
            None
        )

        self._last_fsr_log_time = (
            0.0
        )

        self._hands_on_history = (
            deque(
                maxlen=FSR_STABLE_WINDOW
            )
        )

        self._stable_hands_on_wheel = (
            True
        )

        self.lcd = LCD_I2C()

        self.matrix = None
        self.matrix_font = None

        if not self.gpio_enabled:
            logger.warning(
                "GPIO unavailable"
            )
            return

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(
            BUZZER_PIN,
            GPIO.OUT,
        )

        GPIO.output(
            BUZZER_PIN,
            GPIO.LOW,
        )

        pull_mode = (
            GPIO.PUD_DOWN
            if FSR_ACTIVE_HIGH
            else GPIO.PUD_UP
        )

        GPIO.setup(
            BUTTON_PIN,
            GPIO.IN,
            pull_up_down=pull_mode,
        )

        logger.info(
            "GPIO initialized"
        )

    # ==================================
    # FIXED PASSIVE BUZZER
    # ==================================

    def buzz_alert(
        self,
        state="DEFAULT",
    ):

        if not self.gpio_enabled:
            logger.warning(
                "GPIO unavailable"
            )
            return

        now = time.time()

        if (
            now
            - self.last_buzz_time
            < BUZZ_COOLDOWN_SECONDS
        ):
            return

        self.last_buzz_time = now

        pattern = (
            BUZZ_PATTERNS.get(
                state,
                BUZZ_PATTERNS[
                    "DEFAULT"
                ],
            )
        )

        frequencies = {
            "DISTRACTED": 1400,
            "DIZZY": 1100,
            "DROWSY": 800,
            "EMERGENCY": 1800,
            "DEFAULT": 1000,
        }

        frequency = (
            frequencies.get(
                state,
                1000,
            )
        )

        logger.warning(
            "Buzzer alert: %s",
            state,
        )

        pwm = None

        try:
            pwm = GPIO.PWM(
                BUZZER_PIN,
                frequency,
            )

            for (
                on_t,
                off_t,
            ) in pattern:

                pwm.start(50)

                time.sleep(on_t)

                pwm.stop()

                if off_t > 0:
                    time.sleep(
                        off_t
                    )

        except Exception as exc:
            logger.error(
                f"Buzzer failed: {exc}"
            )

        finally:
            try:
                if pwm:
                    pwm.stop()
            except Exception:
                pass

            GPIO.output(
                BUZZER_PIN,
                GPIO.LOW,
            )

    def read_fsr_sample(self):

        if not self.gpio_enabled:
            return {
                "hands_on": True
            }

        reads = []

        for _ in range(
            FSR_DEBOUNCE_READS
        ):
            reads.append(
                1
                if GPIO.input(
                    BUTTON_PIN
                )
                == GPIO.HIGH
                else 0
            )
            time.sleep(
                FSR_DEBOUNCE_DELAY
            )

        high_count = sum(reads)
        low_count = (
            FSR_DEBOUNCE_READS
            - high_count
        )

        active_count = (
            high_count
            if FSR_ACTIVE_HIGH
            else low_count
        )

        hands_on = (
            active_count
            >= FSR_THRESHOLD_COUNT
        )

        return {
            "hands_on": hands_on
        }

    def is_hands_on_wheel(
        self,
    ) -> bool:
        sample = (
            self.read_fsr_sample()
        )
        return sample[
            "hands_on"
        ]

    def show_help_on_display(
        self,
    ):
        self.lcd.show_help()

    def clear_display(self):
        self.lcd.clear()

    def show_status_on_display(
        self,
        state,
    ):
        self.lcd.show_message(
            f"State: {state}",
            "ADAMS Monitor",
        )

    def cleanup(self):
        self.lcd.cleanup()

        if (
            not self.gpio_enabled
        ):
            return

        GPIO.output(
            BUZZER_PIN,
            GPIO.LOW,
        )

        GPIO.cleanup()

        logger.info(
            "GPIO cleanup complete"
        )

