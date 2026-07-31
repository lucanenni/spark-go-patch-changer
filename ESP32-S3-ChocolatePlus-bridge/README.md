# ESP32-S3 ChocolatePlus bridge

Firmware for a cheap ESP32-S3 "pocket dongle" board (AliExpress, GNPE clone of
the LilyGO T-Dongle-S3 - USB-A male plug, ESP32-S3 N16R8, 0.96" ST7735 LCD)
that turns it into a USB-MIDI <-> BLE bridge: plug it into an **MVave
Chocolate Plus**'s USB **HOST** port, and it translates the pedal's MIDI
commands into the Positive Grid **Spark GO**'s BLE protocol (see
[PROTOCOL.md](../PROTOCOL.md) at the repo root).

The Chocolate Plus's HOST port works like a USB-MIDI host expecting a
class-compliant USB-MIDI *peripheral* on the other end (the same way people
drive a Neural DSP Nano Cortex from it) - so this dongle enumerates as a
**USB-MIDI device**, not a USB host.

## Status / limitations

- Confirmed booting end-to-end on real hardware (all boot checkpoints pass,
  `loop()` runs, screen shows the normal status view). Getting there required
  two hard-won, easy-to-accidentally-undo pins - **read the big comment at
  the top of `[env:esp32-s3-dongle]` in `platformio.ini` before touching
  `platform =` or the `Adafruit TinyUSB Library` version**:
  - `platform = espressif32@6.4.0` exactly (Arduino-ESP32 core 2.0.11,
    esp-idf v4.4.5 commit `ac5d805d0e`). This board's ESP32-S3 silicon is an
    old revision (`esptool` reports "revision v0.2") that silently never
    boots - no crash, no output, nothing on screen, forever - on any other
    esp-idf version tried (4.4.4, and the entire 5.x line via newer platform
    releases). Found by recompiling the manufacturer's own precompiled demo
    firmware's exact source through our toolchain and comparing the
    `esp-idf: vX.X.X <commit>` string embedded in both binaries
    (`strings firmware.bin | grep esp-idf`) until they matched exactly.
  - `Adafruit TinyUSB Library @ 2.2.7`, not the newer default the project
    started with (3.1.0) - that version compiles fine but reboots the board
    partway through `midi_bridge::begin()`'s TinyUSB init on this old
    esp-idf. 2.2.7 was picked as the oldest nearby release that still
    compiles against this project's MIDI Library usage.
- USB-MIDI enumeration confirmed working (`Spark GO Bridge` shows up in Audio
  MIDI Setup on a Mac) - but only once `midi_bridge::begin()` explicitly
  calls the core's own `USB.begin()`. On ESP32, Adafruit_TinyUSB defers
  descriptor-building to the arduino-esp32 core - `Adafruit_USBD_MIDI`'s
  constructor registers the interface, but the actual hardware bring-up only
  happens inside `USB.begin()`, normally auto-triggered by CDC-on-boot (which
  this firmware can't use - conflicts with Adafruit_TinyUSB at link time, see
  the `platform_flags` comment above). Without the explicit call, the dongle
  never enumerates on *any* host, Chocolate Plus or otherwise - confirmed via
  an isolated MIDI-only test build showing `TinyUSBDevice.mounted()` stuck
  false forever. Same reason `usb_midi.setStringDescriptor(...)` has no
  effect on ESP32 - `USB.productName(...)` (called before `USB.begin()`) is
  what actually sets the USB product name here.
- Confirmed working end-to-end against real hardware: the Chocolate Plus's
  HOST port recognizes the dongle and sends real PC/CC messages, patch
  switching and the tuner (start/stop + live note+cents) both work against a
  real Spark GO. Two more non-obvious BLE fixes it took real hardware to
  find (see the comment at the top of `spark_ble.cpp` for detail):
  - `NimBLERemoteCharacteristic::subscribe()`'s CCCD write must be
    write-**with**-response - write-without-response reported success
    (`cccdFound`/`lastSubscribeOk` both true) but the Spark GO never
    actually started sending notifications.
  - A patch-change command is sometimes acked with the generic `CMD 0x04`
    ack (no payload) instead of the richer `CMD 0x03` confirmation
    PROTOCOL.md documents (which carries the new patch number) - both are
    now handled, using the locally-remembered requested patch number when
    the generic ack (no data) arrives instead.
  Diagnosed using `src/bletest_main.cpp` (see "Isolated diagnostic builds"
  below) - much faster than
  guessing from on-screen counters alone, since it can hex-dump every raw
  BLE notification straight to Serial without needing the Chocolate Plus at
  all (there's no CDC/TinyUSB conflict when nothing in the build touches
  USB-MIDI).
- **Tap Tempo (CC8) and Guitar/Channel Volume (CC21) are implemented**,
  ported from the desktop/web clients where both were confirmed against real
  Spark GO hardware (see the root `PROTOCOL.md`'s "Tap tempo" and "Mixer"
  sections) - **not yet re-confirmed through this firmware specifically**,
  same caveat as effect toggling below. Tap Tempo computes a BPM locally from
  the last few tap intervals (resetting after a >2s gap, same logic as
  `desktop/spark_go_gui.py`) and sends it fresh on every tap; there's no
  protocol-level start/stop. Guitar Volume maps the incoming CC value
  (0-127) linearly to the protocol's 0.0-1.0 float; only that one mixer
  channel does anything on the Spark GO.
- **Master Volume (CC20) is deliberately not implemented, and never will be
  via this command.** The amp's physical Music Volume buttons are plain
  Bluetooth AVRCP volume commands sent to the paired phone - a mechanism
  entirely separate from the Spark GO's own BLE service, confirmed by
  watching the phone's volume change when pressing them. Receiving CC20 just
  logs "not supported" (see the on-screen last-event line) rather than
  silently doing nothing.
- **Effect toggling (CC0-6) has been ported but not yet confirmed against
  real Spark GO hardware** (unlike patch switching and the tuner, which
  have). The wire format itself is the same well-tested envelope/packing/
  checksum used everywhere else in this protocol, so it's expected to work,
  but hasn't been explicitly exercised with a real toggle command yet.
- The tuner's cents reading is provisional/uncalibrated (inherited from
  PROTOCOL.md's own notes) - good for a rough on-screen needle, not a
  lab-grade tuner.
- (Re)connect attempts (BLE scan + connect) block briefly; USB-MIDI input
  isn't serviced during that window. Only matters at startup and on rare
  reconnects.

## Hardware notes (unofficial clone - confirm on your unit)

These pins come from verified buyer reviews of the exact AliExpress listing
this was bought from, not an official schematic:

| Signal | Pin |
|---|---|
| TFT SCLK | GPIO10 |
| TFT MOSI | GPIO11 |
| TFT CS | GPIO12 |
| TFT DC | GPIO13 |
| TFT RST | GPIO14 |
| BOOT button (usable as a normal input at runtime) | GPIO0 |

Backlight pin is **not confirmed by any review** - `config.h` leaves it
unmanaged (assumes always-on) until you check continuity on your board. If
you find the real pin, wire it up in `display::begin()`.

If colors/geometry look wrong on first boot, the `ST7735_GREENTAB160x80`
variant define in `platformio.ini` is the most likely thing to need
adjusting - ST7735 panels come in several offset variants.

## Building / flashing

Don't want to set up PlatformIO? **[Flash it straight from a browser](https://lucanenni.github.io/spark-go-utils/flash/)**
instead (Chrome/Edge/Opera on a computer, no software install) - built with
[ESP Web Tools](https://esphome.github.io/esp-web-tools/) against pre-built
binaries in `../docs/flash/firmware/`. No support provided for this route
either, same as everything else here.

```bash
cd ESP32-S3-ChocolatePlus-bridge
pio run --target upload
```

(Requires [PlatformIO](https://platformio.org/).) The board has no separate
USB-serial chip, and the main USB-A plug is dedicated to USB-MIDI - so
uploading needs manual bootloader entry (hold BOOT while plugging the dongle
in, release after a second or two) every time, since there's no CDC port for
esptool to auto-reset through.

`Serial.begin(115200)` goes out over the TX/RX pins (GPIO43/44), **not** the
main USB-A plug. To see the startup banner and `[BLE] ...` connection-state
log lines (Looking for Spark GO.../Scanning.../Connecting.../Connected/
Disconnected), wire an external USB-serial adapter to those pins and open
`pio device monitor` (115200 baud) against that adapter's port - the on-board
display shows the same connection state either way, so this is only useful
for debugging without the screen in view.

## Boot diagnostics

`setup()` in `main.cpp` writes a one-line checkpoint to the screen after each
init step, in order: `display OK` -> `USB-MIDI OK` -> `tuner OK` ->
`BLE init OK` -> `setup() done` (each under a `Booting` header). If the
firmware hangs or crashes partway through `setup()`, whichever line is still
on screen tells you exactly which step it never got past - e.g. stuck on
"display OK" means `midi_bridge::begin()` (USB-MIDI/TinyUSB init) never
returned; stuck on "BLE init OK" would be odd since that's the last one
before the main loop.

Once `setup()` completes, `loop()` takes over and the screen switches to the
normal status view (BLE connection state, current patch, last MIDI command) -
so seeing that view at all, even stuck on "Disconnected"/"Scanning...", means
startup succeeded and the remaining issue is BLE-side (finding/connecting to
the Spark GO), not a boot hang.

Adding a per-file try/catch isn't meaningful in C++ Arduino code - a hang or
a hard crash (Guru Meditation Error) look the same from the screen's
perspective (whatever was last drawn stays there), which is exactly what
these checkpoints are for.

### Isolated diagnostic builds

Three extra PlatformIO environments, each a minimal standalone `src/*_main.cpp`
(picked via `build_src_filter`) that strips the real firmware down to just one
subsystem - useful because the real firmware can't have Serial-over-USB (CDC
conflicts with Adafruit_TinyUSB at link time), so these are the fastest way to
get direct visibility into one part without needing the Chocolate Plus at all:

- `esp32-s3-dongle-displaytest` (`src/displaytest_main.cpp`) - TFT_eSPI only.
  Cycles RED/GREEN/BLUE then shows text + a blinking square. Has CDC enabled
  (no TinyUSB in this build to conflict with).
- `esp32-s3-dongle-miditest` (`src/miditest_main.cpp`) - USB-MIDI + display
  only, no BLE. Shows `TinyUSBDevice.mounted()` status and any PC/CC received
  on screen. No CDC here (Adafruit_TinyUSB is present) - check from the host
  OS side (Audio MIDI Setup > MIDI Studio) instead.
- `esp32-s3-dongle-bletest` (`src/bletest_main.cpp`) - BLE only (reuses the
  real `spark_ble`/`spark_protocol`/`spark_state.cpp`), no USB-MIDI/display.
  Has CDC enabled - hex-dumps every raw BLE notification and logs every
  connection/preset/tuner event straight to Serial, plus takes typed
  commands (`status`, `active`, `patch <1-4>`, `tuner on`/`off`). This is
  what found both BLE bugs listed under Status/limitations above - much
  faster than guessing from on-screen counters on the real firmware.

Build/flash/monitor any of them the same way:
```bash
pio run -e <env-name> --target upload
pio device monitor -e <env-name> -b 115200   # displaytest/bletest only
```

## Programming the Chocolate Plus's footswitches

Using MVave's **CubeSuite** app, map footswitches to send these messages
(bank/footswitch assignment is up to you - this is just what the bridge
listens for):

| Function | Type | Number |
|---|---|---|
| Switch to Preset 1-4 | Program Change | 0-3 |
| Toggle Gate | Control Change | 0 |
| Toggle Comp/Wah | Control Change | 1 |
| Toggle Drive | Control Change | 2 |
| Toggle Amp Slot | Control Change | 3 |
| Toggle Mod/EQ | Control Change | 4 |
| Toggle Delay | Control Change | 5 |
| Toggle Reverb | Control Change | 6 |
| Toggle Tuner | Control Change | 7 |
| Tap Tempo | Control Change | 8 |
| Guitar/Channel Volume | Control Change | 21 |
| Master Volume | Control Change | 20 *(deliberately not implemented - see above)* |

The mapping (channel, CC/PC numbers) lives in `include/config.h` if you want
to change it.

## Layout

- `include/config.h` - hardware pins, MIDI channel, the mapping table above.
- `src/spark_protocol.h/.cpp` - Spark GO BLE wire format: envelope, patch/
  tuner/effect-toggle payload builders, 7-bit packing, checksum, notification
  parsers. Ported from the already hardware-validated Python reference (see
  the repo's `backup-before-restructure` branch), not re-derived.
- `src/spark_ble.h/.cpp` - NimBLE central: scan/connect by name, write/notify
  by characteristic UUID, notification reassembly (BLE notifications don't
  align to message boundaries), auto-reconnect.
- `src/spark_state.h/.cpp` - live cache of the active patch and each pedal
  slot's current name/on-off state, seeded from a preset read and kept fresh
  from the device's own real-time confirmations (never by re-reading the
  preset, which reflects saved data, not live state).
- `src/tuner.h/.cpp` - local tuner on/off toggle (the device doesn't report
  this on its own) + latest decoded reading for the display.
- `src/midi_bridge.h/.cpp` - USB-MIDI device (TinyUSB), PC/CC parsing per the
  mapping table.
- `src/display.h/.cpp` - TFT_eSPI status view (connection, current patch,
  last MIDI command) and tuner view.
- `src/main.cpp` - wires everything together.
