#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

#include "secrets.h"

constexpr uint8_t RED_PIN = D5;
constexpr uint8_t GREEN_PIN = D6;
constexpr unsigned long BLINK_INTERVAL_MS = 400;
constexpr unsigned long CHALLENGE_TIMEOUT_MS = 120000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
String ledState = "off";
unsigned long stateStartedAt = 0;
unsigned long lastBlinkAt = 0;
unsigned long lastMqttAttemptAt = 0;
bool blinkOn = false;
uint8_t redPulses = 0;

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

void onMessage(char* topic, byte* payload, unsigned int length) {
  if (String(topic) != MQTT_TOPIC) return;
  String message;
  message.reserve(length);
  for (unsigned int index = 0; index < length; index++) {
    message += static_cast<char>(payload[index]);
  }

  if (message.indexOf("\"state\":\"password_pending\"") >= 0) {
    applyState("password_pending");
  } else if (message.indexOf("\"state\":\"face_denied\"") >= 0) {
    applyState("face_denied");
  } else if (message.indexOf("\"state\":\"password_denied\"") >= 0) {
    applyState("password_denied");
  } else if (message.indexOf("\"state\":\"granted\"") >= 0) {
    applyState("granted");
  } else {
    applyState("off");
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
}

void reconnectMqtt() {
  if (mqttClient.connected() || millis() - lastMqttAttemptAt < 5000) return;
  lastMqttAttemptAt = millis();
  const String clientId = "resilience-led-" + String(ESP.getChipId(), HEX);
  if (mqttClient.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD)) {
    mqttClient.subscribe(MQTT_TOPIC, 1);
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
  connectWifi();
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(onMessage);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  reconnectMqtt();
  mqttClient.loop();
  updateLed();
  delay(10);
}
