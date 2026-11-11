"""Fast bulk download of datalogger files over USB serial.

Why: `mpremote cp` moves a file 256 bytes at a time as printed Python text,
with a round trip per chunk (~17 KB/s), and the GUI starts one mpremote
process per file. Here we open the serial port once, enter the raw REPL once,
and run a small program on the device that streams every file as raw bytes in
large chunks. Each file is sent with its size and a CRC32 computed on the
device; the computer checks both before keeping the file.

Wire format (device -> computer, inside the raw REPL stdout):
    \x02DL1\n                 sync marker (anything printed before it is ignored)
    N<count>\n                number of files
    F<size> <name>\n          then exactly <size> raw bytes
    C<crc32 hex>\n            CRC32 of those bytes
    ...                       repeated for each file
    E\n                       end

Usable from the GUI (download_all) or from the command line:
    python fast_download.py                     # SD card -> ./data
    python fast_download.py --remote /test_dl --no-mount --dest /tmp/out
"""

import binascii
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

DEVICE_VID = 0x2E8A  # Raspberry Pi RP2040
CHUNK = 4096         # device read/send block size

# Mounts the SD card exactly like read_sd.py / datalogger_class.py.
# SD_BAUD None keeps the driver's default SPI speed (1.32 MHz).
SD_MOUNT_CODE = """
import vfs, sdcard
from machine import SPI, Pin
_cs = Pin(17, Pin.OUT)
_spi = SPI(0, baudrate=1000000, polarity=0, phase=0, bits=8, firstbit=SPI.MSB,
           sck=Pin(18), mosi=Pin(19), miso=Pin(16))
_sd = sdcard.SDCard(_spi, _cs) if SD_BAUD is None else sdcard.SDCard(_spi, _cs, baudrate=SD_BAUD)
try:
    vfs.umount('/sd')
except OSError:
    pass
vfs.mount(vfs.VfsFat(_sd), '/sd')
"""

SD_UMOUNT_CODE = """
vfs.umount('/sd')
"""

DEVICE_CODE = """
import os, sys, binascii
_w = sys.stdout.buffer.write
_b = bytearray(CHUNK)
_m = memoryview(_b)
_names = sorted(e[0] for e in os.ilistdir(REMOTE) if e[1] == 0x8000)
_w(b'\\x02DL1\\n')
_w(('N%d\\n' % len(_names)).encode())
for _n in _names:
    _p = REMOTE + '/' + _n
    _w(('F%d %s\\n' % (os.stat(_p)[6], _n)).encode())
    _c = 0
    with open(_p, 'rb') as _f:
        while True:
            _k = _f.readinto(_b)
            if not _k:
                break
            _w(_m[:_k])
            _c = binascii.crc32(_m[:_k], _c)
    _w(('C%08x\\n' % (_c & 0xffffffff)).encode())
_w(b'E\\n')
"""


class DownloadError(Exception):
    pass


def find_port(vid=DEVICE_VID):
    """Return the first serial port belonging to an RP2040 board."""
    for p in list_ports.comports():
        if p.vid is not None and (vid is None or p.vid == vid):
            return p.device
    raise DownloadError("No device found")


def default_data_dir() -> Path:
    """'data' folder next to this script (or next to the .exe when frozen)."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "data"


class _RawRepl:
    """Minimal MicroPython raw-REPL client with a buffered reader."""

    def __init__(self, port, timeout=10.0):
        self.ser = serial.Serial(port, 115200, timeout=0.2, write_timeout=5)
        self.timeout = timeout
        self.buf = bytearray()

    def close(self):
        try:
            self.ser.write(b"\x02")  # back to the friendly REPL, no reset
            self.ser.flush()
        except Exception:
            pass
        self.ser.close()

    # --- reading helpers -------------------------------------------------
    def _fill(self, deadline):
        n = self.ser.in_waiting
        data = self.ser.read(max(n, 1))
        if data:
            self.buf += data
        elif time.monotonic() > deadline:
            raise DownloadError("Timeout waiting for device")

    def read_until(self, marker: bytes, timeout=None) -> bytes:
        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            i = self.buf.find(marker)
            if i >= 0:
                out = bytes(self.buf[: i + len(marker)])
                del self.buf[: i + len(marker)]
                return out
            self._fill(deadline)

    def read_exact(self, n: int, sink) -> None:
        """Pass exactly n bytes to sink(bytes) as they arrive."""
        while n:
            if self.buf:
                take = min(n, len(self.buf))
                sink(bytes(self.buf[:take]))
                del self.buf[:take]
                n -= take
                continue
            deadline = time.monotonic() + self.timeout
            data = self.ser.read(min(max(self.ser.in_waiting, 1), n))
            if data:
                sink(data)
                n -= len(data)
            elif time.monotonic() > deadline:
                raise DownloadError("Timeout during file transfer")

    def read_line(self) -> bytes:
        line = self.read_until(b"\n")
        if b"\x04" in line:  # program ended early: stderr follows
            raise DownloadError(self._read_error(line))
        return line[:-1]

    def _read_error(self, already=b"") -> str:
        try:
            rest = self.read_until(b"\x04>", timeout=3)
        except DownloadError:
            rest = b""
        text = already + rest
        if text.endswith(b"\x04>"):
            text = text[:-2]
        text = text.replace(b"\x04", b"\n").decode(errors="replace").strip()
        return text or "Device error"

    # --- raw REPL --------------------------------------------------------
    def enter(self):
        self.ser.write(b"\r\x03")  # interrupt whatever is running (main.py ...)
        time.sleep(0.1)
        self.ser.write(b"\x03")
        time.sleep(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\x01")
        self.read_until(b"raw REPL; CTRL-B to exit\r\n>")

    def exec_start(self, code: str):
        data = code.encode()
        for i in range(0, len(data), 256):
            self.ser.write(data[i : i + 256])
            time.sleep(0.01)
        self.ser.write(b"\x04")
        resp = self.read_until(b"OK", timeout=5)
        if not resp.endswith(b"OK"):
            raise DownloadError("Device refused the program")


def _read_sync(repl):
    """Wait for the sync marker. Returns None when found, or the output read
    so far if the program ended first (an exception, e.g. SD mount failed)."""
    deadline = time.monotonic() + 30
    while True:
        if b"\x02DL1\n" in repl.buf:
            repl.read_until(b"\x02DL1\n")
            return None
        if b"\x04" in repl.buf:
            out = bytes(repl.buf)
            repl.buf.clear()
            return out
        repl._fill(deadline)


def download_all(
    dest_dir=None,
    remote="/sd",
    mount_sd=True,
    sd_baudrate=None,
    port=None,
    progress=None,
):
    """Download every file in `remote` on the device into `dest_dir`.

    progress(file_index, file_count, filename, bytes_received, file_size) is
    called as data arrives (from the calling thread).
    Returns a list of (filename, size) for the files written.
    """
    dest = Path(dest_dir) if dest_dir else default_data_dir()
    dest.mkdir(parents=True, exist_ok=True)

    header = f"CHUNK = {CHUNK}\nREMOTE = {remote!r}\nSD_BAUD = {sd_baudrate!r}\n"
    code = header + (SD_MOUNT_CODE if mount_sd else "") + DEVICE_CODE
    if mount_sd:
        code += SD_UMOUNT_CODE

    repl = _RawRepl(port or find_port())
    written = []
    try:
        repl.enter()
        repl.exec_start(code)

        # skip anything printed before the sync marker; stop on early error
        pre = _read_sync(repl)
        if pre is not None:
            raise DownloadError(repl._read_error(pre))

        count = int(repl.read_line()[1:])
        for idx in range(count):
            line = repl.read_line().decode()
            if not line.startswith("F"):
                raise DownloadError(f"Protocol error: {line!r}")
            size_s, name = line[1:].split(" ", 1)
            size = int(size_s)
            final = dest / name
            part = dest / (name + ".part")
            crc = 0
            got = 0

            with open(part, "wb") as f:
                def sink(b):
                    nonlocal crc, got
                    f.write(b)
                    crc = binascii.crc32(b, crc)
                    got += len(b)
                    if progress:
                        progress(idx, count, name, got, size)

                if progress:
                    progress(idx, count, name, 0, size)
                repl.read_exact(size, sink)

            dev_crc = int(repl.read_line().decode()[1:], 16)
            if dev_crc != crc:
                part.unlink(missing_ok=True)
                raise DownloadError(f"CRC mismatch on {name}")
            part.replace(final)
            written.append((name, size))

        if repl.read_line() != b"E":
            raise DownloadError("Protocol error at end of transfer")
        # wait for the program to finish (it unmounts the SD card)
        tail = repl.read_until(b"\x04>", timeout=10)
        err = tail[:-2].split(b"\x04", 1)[-1].strip()
        if err:
            raise DownloadError(err.decode(errors="replace"))
    finally:
        repl.close()
    return written


def _main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port")
    ap.add_argument("--dest", help="destination folder (default: ./data)")
    ap.add_argument("--remote", default="/sd", help="folder on the device")
    ap.add_argument("--no-mount", action="store_true", help="don't mount the SD card")
    ap.add_argument("--sd-baud", type=int, help="SD card SPI speed (default: driver default)")
    a = ap.parse_args()

    last = [None]

    def progress(idx, count, name, got, size):
        if got == size and last[0] != name:
            last[0] = name
            print(f"[{idx + 1}/{count}] {name} ({size} bytes)")

    t = time.monotonic()
    files = download_all(a.dest, a.remote, not a.no_mount, a.sd_baud, a.port, progress)
    dt = time.monotonic() - t
    total = sum(s for _, s in files)
    print(f"{len(files)} files, {total} bytes in {dt:.2f} s ({total / dt / 1024:.1f} KB/s)")


if __name__ == "__main__":
    _main()
