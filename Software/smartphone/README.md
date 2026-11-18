# Datalogger Android app

An Android app for working with the datalogger in the field, without a computer.
It does not need mpremote and the Pico firmware stays unchanged.

- reads the datalogger clock next to the phone clock and shows the difference
- sets the datalogger clock to the phone's local time
- reads the battery voltage (using `batt_R1`/`batt_R2` from `info.json`) and the Pico's internal temperature
- lists the files on the SD card and downloads them into a folder you pick on the phone.
  It downloads only the files that are new or that changed (compared by size), or the files you tick.
  Each file is checked with a CRC32 before it is saved.

## What you need

- An Android phone (8.0 or newer) that supports USB host / OTG. Most phones do.
- A USB-OTG adapter or a USB-C to micro-USB cable, to go from the phone to the Pico's USB port.

## How it works

The phone acts as the USB host. It sees the Pico as a USB serial port and drives MicroPython's
*raw REPL*, the same way `mpremote` and `Software/computer/fast_download.py` do:

1. Ctrl-C stops `main.py`, then the app switches to the raw REPL.
2. The app sends small MicroPython programs that read the RTC (DS3232 or PCF8523, from
   `rtc_type` in `info.json`), the ADC, and the SD card. They use the same libraries and
   pins as `datalogger_class.py`.
3. Files are streamed with the same wire format as `fast_download.py`.

**Watchdog.** `main.py` arms an 8 s hardware watchdog, and it cannot be turned off. The app
re-arms the watchdog and feeds it every 2.5 s while it is connected. When you tap
**Disconnect**, or simply pull the cable, the feeding stops, the Pico resets, and `main.py`
starts again. Logging resumes once the USB cable is unplugged (while USB power is present,
`main.py` only prints readings).

## Using it

1. Plug the datalogger into the phone. When Android asks, choose this app and tick
   *always open*. This also grants USB access without asking again.
2. The app connects, then shows the clock, battery and SD file list.
3. The first time, tap **Choose folder** and pick (or create) a folder, e.g. `Download/datalogger`.
4. Tap **Download new & changed**.
5. Tap **Disconnect**, then unplug.

## Building

Open this folder in Android Studio, or from the command line:

```bash
./gradlew assembleDebug
```

The APK ends up in `app/build/outputs/apk/debug/app-debug.apk`. To install it on a phone
connected with USB debugging:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Code layout

| File | Role |
|---|---|
| `UsbCdc.kt` | Minimal USB CDC-ACM serial driver (Android USB host API, no extra library) |
| `RawRepl.kt` | MicroPython raw-REPL client, a port of `_RawRepl` in `fast_download.py` |
| `Datalogger.kt` | The MicroPython snippets run on the Pico, and the parsing of their output |
| `FolderStore.kt` | Saves files into the chosen folder (Storage Access Framework) |
| `MainViewModel.kt` / `MainActivity.kt` | State, USB permission handling, Compose UI |
