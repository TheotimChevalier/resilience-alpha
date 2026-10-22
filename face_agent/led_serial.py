import threading
import time

import serial


class LedSerialBridge:
    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        timeout: float = 2.0,
        reset_delay: float = 2.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reset_delay = reset_delay
        self._connection: serial.Serial | None = None
        self._lock = threading.Lock()

    def send(self, state: str) -> None:
        with self._lock:
            try:
                connection = self._connection
                if connection is None or not connection.is_open:
                    connection = serial.Serial(
                        self.port,
                        self.baudrate,
                        timeout=self.timeout,
                        write_timeout=self.timeout,
                    )
                    self._connection = connection
                    time.sleep(self.reset_delay)
                    connection.reset_input_buffer()

                connection.write(f"{state}\n".encode("ascii"))
                connection.flush()
                response = connection.readline().decode("ascii").strip()
                if response != f"OK:{state}":
                    raise serial.SerialException("ESP8266 did not acknowledge the LED state")
            except (serial.SerialException, OSError, UnicodeDecodeError):
                self._close_connection()
                raise

    def close(self) -> None:
        with self._lock:
            self._close_connection()

    def _close_connection(self) -> None:
        if self._connection is not None:
            if self._connection.is_open:
                self._connection.close()
            self._connection = None
