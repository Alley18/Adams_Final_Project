import importlib
import logging
import os
import time
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
BUZZER_PIN = 17

# FSR wired as voltage divider → GPIO digital read
# Wire: 3.3V → FSR → junction → 10kΩ resistor → GND
#        junction -> GPIO pin 27 by default
# When pressed: voltage rises → GPIO reads HIGH
FSR_PIN = int(os.getenv("ADAMS_FSR_PIN", "27"))

# =============================
# LCD I2C Config
# =============================
LCD_I2C_ADDRESS = 0x27   # most common; try 0x3F if 0x27 doesn't work
LCD_I2C_BUS     = 1      # /dev/i2c-1 on Pi 3/4/5

# HD44780 command constants
LCD_CHR = 1   # sending data
LCD_CMD = 0   # sending command

LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0

LCD_BACKLIGHT_ON  = 0x08
LCD_BACKLIGHT_OFF = 0x00

ENABLE_BIT = 0b00000100

E_PULSE = 0.0005
E_DELAY = 0.0005

# =============================
# Config
# =============================
BUZZ_COOLDOWN_SECONDS = 2

FSR_DEBOUNCE_READS  = 5       # majority vote over N reads
FSR_DEBOUNCE_DELAY  = 0.01    # seconds between reads
FSR_THRESHOLD_COUNT = 3       # how many HIGH reads = hand on wheel
FSR_ACTIVE_HIGH = os.getenv("ADAMS_FSR_ACTIVE_HIGH", "1") != "0"
FSR_LOG_INTERVAL_SECONDS = float(os.getenv("ADAMS_FSR_LOG_INTERVAL_SECONDS", "5"))

MAX7219_CASCADE = int(os.getenv("ADAMS_MAX7219_CASCADE", "4"))
MAX7219_ROTATE = int(os.getenv("ADAMS_MAX7219_ROTATE", "0"))
MAX7219_BLOCK_ORIENTATION = int(os.getenv("ADAMS_MAX7219_BLOCK_ORIENTATION", "90"))
MAX7219_SPI_PORT = int(os.getenv("ADAMS_MAX7219_SPI_PORT", "0"))
MAX7219_SPI_DEVICE = int(os.getenv("ADAMS_MAX7219_SPI_DEVICE", "0"))

BUZZ_PATTERNS = {
    "DISTRACTED": [(0.15, 0.10), (0.15, 0.10)],
    "DIZZY":      [(0.25, 0.10), (0.25, 0.10), (0.25, 0.10)],
    "DROWSY":     [(0.60, 0.10), (0.60, 0.00)],
    "EMERGENCY":  [(0.10, 0.05), (0.10, 0.05), (0.10, 0.05),
                   (0.10, 0.05), (0.10, 0.05), (0.50, 0.10)],  # rapid then long
    "DEFAULT":    [(0.30, 0.00)],
}


# ─────────────────────────────────────────────────────────────
# LCD helper (bit-bang over I2C PCF8574 backpack)
# ─────────────────────────────────────────────────────────────

class LCD_I2C:
    """
    Minimal HD44780 driver over a PCF8574 I2C backpack.
    Works with the common 1602/2004 blue/green LCD modules.
    """

    def __init__(self, address: int = LCD_I2C_ADDRESS, bus: int = LCD_I2C_BUS):
        self._addr = address
        self._backlight = LCD_BACKLIGHT_ON
        self._bus = None
        self._ok = False

        if SMBus is None:
            logger.warning("smbus2 not installed – LCD disabled. Run: pip install smbus2")
            return

        try:
            self._bus = SMBus(bus)
            self._init_lcd()
            self._ok = True
            logger.info(f"LCD initialised at I2C address 0x{address:02X}")
        except Exception as exc:
            logger.error(f"LCD init failed: {exc}")

    # ── low-level I2C ──────────────────────────────────────

    def _write_byte(self, data: int) -> None:
        self._bus.write_byte(self._addr, data)
        time.sleep(E_DELAY)

    def _toggle_enable(self, data: int) -> None:
        self._write_byte(data | ENABLE_BIT)
        time.sleep(E_PULSE)
        self._write_byte(data & ~ENABLE_BIT)
        time.sleep(E_PULSE)

    def _send_nibble(self, data: int, mode: int) -> None:
        high = (data & 0xF0) | mode | self._backlight
        self._write_byte(high)
        self._toggle_enable(high)

    def _send_byte(self, data: int, mode: int) -> None:
        self._send_nibble(data, mode)
        self._send_nibble((data << 4) & 0xF0, mode)

    # ── init sequence (HD44780 4-bit mode) ─────────────────

    def _init_lcd(self) -> None:
        time.sleep(0.05)
        for _ in range(3):
            self._send_nibble(0x30, LCD_CMD)
            time.sleep(0.005)
        self._send_nibble(0x20, LCD_CMD)   # switch to 4-bit

        for cmd in (
            0x28,  # 4-bit, 2 lines, 5×8 font
            0x0C,  # display ON, cursor OFF, blink OFF
            0x06,  # entry mode: increment, no shift
            0x01,  # clear display
        ):
            self._send_byte(cmd, LCD_CMD)
            time.sleep(0.005)

    # ── public API ─────────────────────────────────────────

    def clear(self) -> None:
        if not self._ok:
            return
        self._send_byte(0x01, LCD_CMD)
        time.sleep(0.005)

    def write(self, text: str, line: int = 1, center: bool = True) -> None:
        """Write up to 16 chars on line 1 or 2."""
        if not self._ok:
            return
        addr = LCD_LINE_1 if line == 1 else LCD_LINE_2
        padded = text[:16].ljust(16) if not center else text[:16].center(16)
        self._send_byte(addr, LCD_CMD)
        for ch in padded:
            self._send_byte(ord(ch), LCD_CHR)

    def show_help(self) -> None:
        """Display the HELP alert on both lines."""
        if not self._ok:
            return
        self.clear()
        self.write("*** HELP ***",  line=1, center=True)
        self.write("Need assistance?", line=2, center=True)
        logger.warning("LCD: HELP message displayed")

    def show_message(self, line1: str, line2: str = "") -> None:
        if not self._ok:
            return
        self.clear()
        self.write(line1, line=1, center=True)
        if line2:
            self.write(line2, line=2, center=True)

    def backlight(self, on: bool) -> None:
        self._backlight = LCD_BACKLIGHT_ON if on else LCD_BACKLIGHT_OFF
        if self._ok:
            self._write_byte(self._backlight)

    def cleanup(self) -> None:
        if not self._ok:
            return
        try:
            self.clear()
            self.backlight(False)
            self._bus.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# Main hardware controller
# ─────────────────────────────────────────────────────────────

class HardwareController:

    def __init__(self):
        self.last_buzz_time = 0.0
        self.gpio_enabled = GPIO is not None
        self.last_fsr_sample = None
        self._last_hands_on_wheel = None
        self._last_fsr_log_time = 0.0

        # LCD is independent of GPIO
        self.lcd = LCD_I2C()
        self.matrix = None
        self.matrix_font = None
        self._setup_matrix()

        if not self.gpio_enabled:
            logger.warning("GPIO unavailable – simulation mode")
            return

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # ── Outputs ──────────────────────────────────────
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.LOW)

        # ── FSR input ────────────────────────────────────
        # Default wiring: pin reads HIGH when the FSR is pressed.
        pull_mode = GPIO.PUD_DOWN if FSR_ACTIVE_HIGH else GPIO.PUD_UP
        GPIO.setup(FSR_PIN, GPIO.IN, pull_up_down=pull_mode)

        logger.info(
            "GPIO initialised (buzzer + FSR): buzzer_pin=%s, fsr_pin=%s, "
            "active_high=%s, threshold=%s/%s",
            BUZZER_PIN,
            FSR_PIN,
            FSR_ACTIVE_HIGH,
            FSR_THRESHOLD_COUNT,
            FSR_DEBOUNCE_READS,
        )

    # =============================
    # BUZZER  (unchanged logic)
    # =============================

    def buzz_alert(self, state: str = "DEFAULT") -> None:
        if not self.gpio_enabled:
            logger.warning("Buzzer skipped: GPIO unavailable")
            return

        now = time.time()
        if now - self.last_buzz_time < BUZZ_COOLDOWN_SECONDS:
            logger.debug("Buzzer skipped: cooldown active")
            return
        self.last_buzz_time = now

        pattern = BUZZ_PATTERNS.get(state, BUZZ_PATTERNS["DEFAULT"])
        logger.warning("Buzzer alert: %s pattern (%s pulse(s))", state, len(pattern))

        try:
            for on_t, off_t in pattern:
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                time.sleep(on_t)
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                time.sleep(off_t)
        finally:
            GPIO.output(BUZZER_PIN, GPIO.LOW)

    # =============================
    # FSR / WHEEL SENSOR
    # =============================

    def read_fsr_sample(self) -> dict:
        """
        Read the force sensor with debounce and return diagnostic details.

        Default wiring:
            3.3V -> FSR -> junction -> 10k resistor -> GND
                            junction -> GPIO 27

        No pressure -> pin LOW -> hands OFF
        Pressure    -> pin HIGH -> hands ON
        """
        if not self.gpio_enabled:
            sample = {
                "pin": FSR_PIN,
                "reads": [],
                "high_count": 0,
                "low_count": 0,
                "active_count": FSR_DEBOUNCE_READS,
                "threshold": FSR_THRESHOLD_COUNT,
                "active_high": FSR_ACTIVE_HIGH,
                "hands_on": True,
                "simulated": True,
            }
            self.last_fsr_sample = sample
            return sample

        reads = []
        for _ in range(FSR_DEBOUNCE_READS):
            reads.append(1 if GPIO.input(FSR_PIN) == GPIO.HIGH else 0)
            time.sleep(FSR_DEBOUNCE_DELAY)

        high_count = sum(reads)
        low_count = FSR_DEBOUNCE_READS - high_count
        active_count = high_count if FSR_ACTIVE_HIGH else low_count
        hands_on = active_count >= FSR_THRESHOLD_COUNT

        sample = {
            "pin": FSR_PIN,
            "reads": reads,
            "high_count": high_count,
            "low_count": low_count,
            "active_count": active_count,
            "threshold": FSR_THRESHOLD_COUNT,
            "active_high": FSR_ACTIVE_HIGH,
            "hands_on": hands_on,
            "simulated": False,
        }
        self.last_fsr_sample = sample
        return sample

    def _log_fsr_sample(self, sample: dict) -> None:
        hands_on = sample["hands_on"]
        now = time.time()
        state_changed = hands_on != self._last_hands_on_wheel
        log_due = now - self._last_fsr_log_time >= FSR_LOG_INTERVAL_SECONDS

        if not state_changed and not log_due:
            return

        self._last_hands_on_wheel = hands_on
        self._last_fsr_log_time = now
        logger.info(
            "FSR hands=%s pin=%s reads=%s high=%s low=%s active=%s/%s active_high=%s",
            "ON" if hands_on else "OFF",
            sample["pin"],
            sample["reads"],
            sample["high_count"],
            sample["low_count"],
            sample["active_count"],
            sample["threshold"],
            sample["active_high"],
        )

    def is_hands_on_wheel(self) -> bool:
        """
        Reads FSR pin with majority voting for debounce stability.

        Wiring assumed:
            3.3V ──[FSR]──┬──[10kΩ]── GND
                          │
                        GPIO 27 by default (PUD_DOWN)

        No pressure  → FSR very high resistance → pin stays LOW  → hands OFF
        Pressure     → FSR resistance drops    → voltage rises  → pin HIGH → hands ON
        """
        sample = self.read_fsr_sample()
        self._log_fsr_sample(sample)
        hands_on = sample["hands_on"]
        return hands_on

    def read_logged_fsr_sample(self) -> dict:
        """Read the FSR once, log changes/periodic diagnostics, and return details."""
        sample = self.read_fsr_sample()
        self._log_fsr_sample(sample)
        return sample

    # =============================
    # Matrix display helpers
    # =============================

    def _setup_matrix(self) -> None:
        if max7219 is None or spi is None or canvas is None or ImageFont is None:
            return

        try:
            serial = spi(port=MAX7219_SPI_PORT, device=MAX7219_SPI_DEVICE, gpio=noop())
            self.matrix = max7219(
                serial,
                cascaded=MAX7219_CASCADE,
                block_orientation=MAX7219_BLOCK_ORIENTATION,
                rotate=MAX7219_ROTATE,
            )
            self.matrix.clear()
            self.matrix_font = ImageFont.load_default()
            logger.info(
                "MAX7219 matrix initialized: cascaded=%s rotate=%s",
                MAX7219_CASCADE,
                MAX7219_ROTATE,
            )
        except Exception as exc:
            logger.warning("MAX7219 matrix init failed: %s", exc)
            self.matrix = None

    def _show_help_matrix(self) -> None:
        if self.matrix is None or self.matrix_font is None:
            return

        try:
            with canvas(self.matrix) as draw:
                draw.rectangle((0, 0, self.matrix.width, self.matrix.height), fill="black")
                draw.text((0, 0), "HELP", font=self.matrix_font, fill="white")
        except Exception as exc:
            logger.warning("Matrix HELP draw failed: %s", exc)
            self.matrix.clear()

    # =============================
    # LCD convenience wrappers
    # =============================

    def show_help_on_display(self) -> None:
        """Display the HELP alert on the available status display."""
        if self.matrix is not None:
            self._show_help_matrix()
        else:
            self.lcd.show_help()

    def clear_display(self) -> None:
        if self.matrix is not None:
            try:
                self.matrix.clear()
            except Exception:
                pass
        self.lcd.clear()

    def show_status_on_display(self, state: str) -> None:
        """Optionally show the current driver state on the LCD."""
        if self.matrix is not None:
            try:
                self.matrix.clear()
            except Exception:
                pass
        self.lcd.show_message(f"State: {state[:14]}", "ADAMS Monitor")

    # =============================
    # CLEANUP
    # =============================

    def cleanup(self) -> None:
        self.lcd.cleanup()

        if not self.gpio_enabled:
            return

        GPIO.output(BUZZER_PIN, GPIO.LOW)
        GPIO.cleanup()
        logger.info("GPIO cleanup complete")
