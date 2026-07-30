// Minimal, standalone USB-MIDI test - deliberately has NO dependency on
// BLE/any other module in this firmware, so it isolates one question: does
// the dongle enumerate as a USB-MIDI device at all when nothing else
// (NimBLE) is running alongside it? Uses the display (not Serial - CDC and
// Adafruit_TinyUSB can't coexist in one build, see platformio.ini) to show
// whether the firmware is even running and whether any MIDI message ever
// arrives, since a Mac not showing the device in Audio MIDI Setup alone
// doesn't tell us if the board is still alive at all.
//
// Build and flash ONLY this with:
//   pio run -e esp32-s3-dongle-miditest --target upload
//
// Then, with the dongle plugged into a Mac (not the Chocolate Plus):
// - Screen should show "MIDI test running" right after boot - if it
//   doesn't, the firmware itself isn't running, unrelated to USB-MIDI.
// - Open Audio MIDI Setup (Applications > Utilities) > Window > Show MIDI
//   Studio - a device named "Spark GO Bridge" should appear.
// - Send it any Program Change or Control Change message (e.g. via a DAW,
//   `sendmidi`, or a simple script) - the screen should update to show it.

#include <Arduino.h>

#include <Adafruit_TinyUSB.h>
#include <MIDI.h>
#include <TFT_eSPI.h>
#include <USB.h>

namespace {

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDI);

TFT_eSPI tft;

void showLine(const String& line) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setCursor(2, 2);
  tft.print(line);
}

void handleProgramChange(uint8_t channel, uint8_t number) {
  showLine("PC ch" + String(channel) + " #" + String(number));
}

void handleControlChange(uint8_t channel, uint8_t number, uint8_t value) {
  showLine("CC ch" + String(channel) + " #" + String(number) + "=" + String(value));
}

}  // namespace

void setup() {
  tft.init();
  tft.setRotation(1);
  showLine("MIDI test running");

  // usb_midi.setStringDescriptor() has no effect on ESP32 (see the
  // Adafruit_TinyUSB README's ESP32 port note) - the product name must be
  // set via the core's own USB object instead, before USB.begin().
  USB.productName("Spark GO Bridge");
  MIDI.begin(MIDI_CHANNEL_OMNI);
  MIDI.setHandleProgramChange(handleProgramChange);
  MIDI.setHandleControlChange(handleControlChange);

  // On ESP32, Adafruit_TinyUSB's begin()/MIDI.begin() only *register* the
  // MIDI interface with the core's descriptor builder (done automatically
  // in Adafruit_USBD_MIDI's constructor, before setup() even runs) - they
  // do NOT bring up the actual USB hardware or start the tud_task() loop.
  // That only happens inside the core's own USB.begin() (normally triggered
  // automatically by CDC-on-boot, which we don't use here) - without this
  // explicit call, TinyUSBDevice.mounted() never becomes true and the OS
  // never sees the device at all, confirmed on real hardware.
  USB.begin();
}

void loop() {
  MIDI.read();

  // TinyUSBDevice.mounted() is the device's OWN view of whether USB
  // enumeration completed - shown continuously so we can tell "device
  // thinks it's mounted but the OS doesn't show it" apart from "device
  // itself never finishes enumerating" (see the comment at the top of this
  // file / the official Adafruit MIDI example, which blocks on this same
  // call before doing anything else).
  static bool lastMounted = false;
  static uint32_t lastDrawMs = 0;
  bool mounted = TinyUSBDevice.mounted();
  if (mounted != lastMounted || millis() - lastDrawMs > 1000) {
    lastMounted = mounted;
    lastDrawMs = millis();
    showLine(String("mounted=") + (mounted ? "YES" : "no") + " t=" + String(millis() / 1000));
  }
}
