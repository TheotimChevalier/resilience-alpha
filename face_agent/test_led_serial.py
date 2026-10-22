import serial
import pytest

from face_agent.led_serial import LedSerialBridge


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.writes = []
        self.response = b""
        self.reset_count = 0

    def write(self, value):
        self.writes.append(value)
        self.response = b"OK:" + value.strip() + b"\r\n"
        return len(value)

    def flush(self):
        pass

    def readline(self):
        return self.response

    def reset_input_buffer(self):
        self.reset_count += 1

    def close(self):
        self.is_open = False


def test_send_reuses_serial_connection(monkeypatch):
    connections = []

    def open_serial(*args, **kwargs):
        connection = FakeSerial(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(serial, "Serial", open_serial)
    bridge = LedSerialBridge("COM3", reset_delay=0)

    bridge.send("password_pending")
    bridge.send("granted")

    assert len(connections) == 1
    assert connections[0].writes == [b"password_pending\n", b"granted\n"]
    assert connections[0].reset_count == 1
    bridge.close()
    assert not connections[0].is_open


def test_send_closes_connection_without_acknowledgement(monkeypatch):
    connection = FakeSerial()
    connection.readline = lambda: b"ERR:invalid-state\r\n"
    monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: connection)
    bridge = LedSerialBridge("COM3", reset_delay=0)

    with pytest.raises(serial.SerialException):
        bridge.send("granted")

    assert not connection.is_open
