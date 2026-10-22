#include <Arduino.h>

constexpr uint8_t RED_PIN = D2;
constexpr uint8_t GREEN_PIN = D1;
constexpr unsigned long BLINK_INTERVAL_MS = 400;
constexpr unsigned long CHALLENGE_TIMEOUT_MS = 120000;

String ledState = "off";
unsigned long stateStartedAt = 0;
unsigned long lastBlinkAt = 0;
bool blinkOn = false;
uint8_t redPulses = 0;
char serialLine[32];
size_t serialLineLength = 0;
bool serialLineOverflow = false;

void setLed(bool red, bool green) {
  digitalWrite(RED_PIN, red ? HIGH : LOW);
  digitalWrite(GREEN_PIN, green ? HIGH : LOW);
}

void applyState(const String& nextState) {
  ledState = nextState;
  stateStartedAt = millis();
  lastBlinkAt = stateStartedAt;
  blinkOn = false;
  redPulses = 0;

  if (ledState == "off" || ledState == "password_pending") {
    setLed(false, false);
  } else if (ledState == "face_denied") {
    setLed(true, false);
  } else if (ledState == "granted") {
    setLed(false, true);
  }
}

bool isValidState(const String& state) {
  return state == "off" || state == "password_pending" || state == "face_denied"
      || state == "password_denied" || state == "granted";
}

void processSerialLine() {
  if (serialLineOverflow) {
    Serial.println("ERR:line-too-long");
    serialLineOverflow = false;
    serialLineLength = 0;
    return;
  }

  serialLine[serialLineLength] = '\0';
  const String state(serialLine);
  if (!isValidState(state)) {
    Serial.println("ERR:invalid-state");
  } else {
    applyState(state);
    Serial.print("OK:");
    Serial.println(state);
  }
  serialLineLength = 0;
}

void processSerial() {
  while (Serial.available() > 0) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\r') continue;
    if (character == '\n') {
      processSerialLine();
    } else if (serialLineLength < sizeof(serialLine) - 1) {
      serialLine[serialLineLength++] = character;
    } else {
      serialLineOverflow = true;
    }
  }
}

void updateLed() {
  const unsigned long now = millis();
  if (ledState == "face_denied" && now - stateStartedAt >= 30000) {
    applyState("off");
  } else if (ledState == "granted" && now - stateStartedAt >= 30000) {
    applyState("off");
  } else if (ledState == "password_pending" && now - stateStartedAt >= CHALLENGE_TIMEOUT_MS) {
    applyState("off");
  } else if (ledState == "password_pending" && now - lastBlinkAt >= BLINK_INTERVAL_MS) {
    lastBlinkAt = now;
    blinkOn = !blinkOn;
    setLed(false, blinkOn);
  } else if (ledState == "password_denied" && now - lastBlinkAt >= 250) {
    lastBlinkAt = now;
    blinkOn = !blinkOn;
    setLed(blinkOn, false);
    if (!blinkOn && ++redPulses >= 10) {
      applyState("off");
    }
  }
}

void setup() {
  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  setLed(false, false);
  Serial.begin(115200);
}

void loop() {
  processSerial();
  updateLed();
  delay(10);
}
