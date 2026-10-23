#include <Arduino.h>

constexpr uint8_t LED_PIN = D1;
constexpr unsigned long BLINK_INTERVAL_MS = 1000;

unsigned long lastToggleAt = 0;
bool ledOn = false;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  const unsigned long now = millis();
  if (now - lastToggleAt >= BLINK_INTERVAL_MS) {
    lastToggleAt = now;
    ledOn = !ledOn;
    digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
  }
}
