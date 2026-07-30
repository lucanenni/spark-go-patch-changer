#include "tuner.h"

#include "spark_ble.h"

namespace tuner {

namespace {

bool g_on = false;
Reading g_reading;

void turnOff() {
  g_on = false;
  spark_ble::tunerStop();
  g_reading = Reading();
}

}  // namespace

void begin() {
  g_on = false;
  g_reading = Reading();
}

bool toggle() {
  if (g_on) {
    turnOff();
  } else {
    g_on = true;
    spark_ble::tunerStart();
  }
  return g_on;
}

bool isOn() { return g_on; }

void forceOff() {
  if (g_on) turnOff();
}

void handleFrame(const spark_protocol::TunerFrame& frame) {
  if (!g_on) return;
  if (frame.idle) {
    g_reading = Reading();
    return;
  }
  g_reading.hasSignal = true;
  g_reading.noteName = spark_protocol::noteName(frame.note);
  g_reading.cents = frame.cents;
}

Reading currentReading() { return g_reading; }

}  // namespace tuner
