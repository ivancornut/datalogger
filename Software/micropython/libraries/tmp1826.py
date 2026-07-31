# This library is based on the DS18B20 library with adaptations for work with tmp1826 devices
import time
from micropython import const

_CONVERT = const(0x44)
_RD_SCRATCH = const(0xBE)
_WR_SCRATCH = const(0x4E)

# Scratchpad-2 / user EEPROM functions
_WR_SCRATCH2 = const(0x0F)   # WRITE SCRATCHPAD-2
_RD_SCRATCH2 = const(0xAA)   # READ SCRATCHPAD-2
_COPY_SCRATCH2 = const(0x55)  # COPY SCRATCHPAD-2 (commit to EEPROM)
_READ_EEPROM = const(0xF0)   # READ EEPROM directly
_COPY_QUALIFIER = const(0xA5)  # qualifier byte required by COPY SCRATCHPAD-2

# EEPROM programming time: datasheet tPROG max = 21 ms for an 8-byte word.
# Use margin. In ms.
_TPROG_MS = const(25)
# Idle time before reading an EEPROM block: datasheet tREADIDLE max = 560 us.
_TREADIDLE_US = const(1000)

# Default 8-byte EEPROM block reserved for sensor metadata.
# Must be on an 8-byte boundary (0x0000, 0x0008, 0x0010, ...).
_META_ADDR = const(0x0000)


class TMP1826:
    def __init__(self, onewire):
        self.ow = onewire
        self.buf = bytearray(9)  # the first 8 bytes of scratchpad + CRC

    def scan(self):
        return [rom for rom in self.ow.scan() if rom[0] == 0x26]

    def convert_temp(self):
        self.ow.reset(True)
        self.ow.writebyte(self.ow.SKIP_ROM)
        self.ow.writebyte(_CONVERT)

    def read_scratch(self, rom):
        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_RD_SCRATCH)
        self.ow.readinto(self.buf)
        if self.ow.crc8(self.buf):
            raise Exception("CRC error")
        return self.buf

    def write_scratch(self, rom, buf):
        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_WR_SCRATCH)
        self.ow.write(buf)

    def read_temp(self, rom, verbose=False):
        #t = buf[1] << 8 | buf[0] DS18B20
        buf = self.read_scratch(rom)
        raw = buf[1] << 8 | buf[0]

        if raw & 0x8000:   # sign bit set
            raw -= 0x10000

        temp = raw / 16    # bit 0 = 0.0625 = 1/16

        if verbose:
            print(temp)

        return temp

    # ------------------------------------------------------------------
    # Scratchpad-2 / user EEPROM
    #
    # Notes from the datasheet:
    #  - The device has NO byte-wise EEPROM access. All access is in
    #    8-byte blocks, and the address must be on an 8-byte boundary.
    #  - The 2-byte EEPROM address is sent MSB first, LSB last (this is
    #    the opposite byte order from the little-endian temperature bytes).
    #  - Programming to EEPROM is a two-step process: stage the 8 bytes in
    #    scratchpad-2, then COPY SCRATCHPAD-2 with the A5h qualifier.
    # ------------------------------------------------------------------

    def write_scratch2(self, rom, addr, data8):
        """Stage 8 bytes into scratchpad-2 at EEPROM address `addr`.
        Verifies the device CRC computed over (2 addr + 8 data) bytes.
        This does NOT commit to EEPROM -- call copy_scratch2() for that.
        """
        if len(data8) != 8:
            raise ValueError("data must be exactly 8 bytes")
        if addr & 0x07:
            raise ValueError("address must be on an 8-byte boundary")

        addr_hi = (addr >> 8) & 0xFF
        addr_lo = addr & 0xFF

        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_WR_SCRATCH2)
        self.ow.writebyte(addr_hi)   # MSB first
        self.ow.writebyte(addr_lo)
        self.ow.write(bytes(data8))

        # Device returns CRC over the 10 bytes (2 addr + 8 data). Rebuild
        # the same 10 bytes, append the received CRC, and let crc8 confirm
        # the whole sequence shifts out to 0.
        crc = self.ow.readbyte()
        check = bytearray((addr_hi, addr_lo)) + bytes(data8) + bytes((crc,))
        if self.ow.crc8(check):
            raise Exception("WRITE SCRATCHPAD-2 CRC error")

    def read_scratch2(self, rom, addr):
        """Read back the 8 bytes currently staged in scratchpad-2 for
        address `addr`. Returns a bytearray of 8 bytes. Verifies CRC.
        The address must match the one used in the last write_scratch2().
        """
        if addr & 0x07:
            raise ValueError("address must be on an 8-byte boundary")

        addr_hi = (addr >> 8) & 0xFF
        addr_lo = addr & 0xFF

        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_RD_SCRATCH2)
        self.ow.writebyte(addr_hi)   # MSB first
        self.ow.writebyte(addr_lo)

        data = bytearray(8)
        self.ow.readinto(data)
        crc = self.ow.readbyte()

        # CRC is computed over 2 addr bytes + 8 data bytes.
        check = bytearray((addr_hi, addr_lo)) + data + bytes((crc,))
        if self.ow.crc8(check):
            raise Exception("READ SCRATCHPAD-2 CRC error (address mismatch?)")
        return data

    def copy_scratch2(self, rom):
        """Commit the current scratchpad-2 contents to the user EEPROM at
        the address staged by the last write_scratch2(). Blocks for tPROG.
        """
        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_COPY_SCRATCH2)
        self.ow.writebyte(_COPY_QUALIFIER)   # A5h
        time.sleep_ms(_TPROG_MS)             # bus must stay idle during program

    def read_eeprom(self, rom, addr):
        """Read one 8-byte block directly from the user EEPROM at `addr`.
        Returns a bytearray of 8 bytes. READ EEPROM provides no CRC, so
        there is nothing to verify here; use read_scratch2() if you want a
        CRC-checked read path.
        """
        if addr & 0x07:
            raise ValueError("address must be on an 8-byte boundary")

        addr_hi = (addr >> 8) & 0xFF
        addr_lo = addr & 0xFF

        self.ow.reset(True)
        self.ow.select_rom(rom)
        self.ow.writebyte(_READ_EEPROM)
        self.ow.writebyte(addr_hi)   # MSB first
        self.ow.writebyte(addr_lo)

        time.sleep_us(_TREADIDLE_US)  # idle so the device can prefetch the block

        # NOTE: READ EEPROM (F0h) does NOT return a CRC (unlike READ
        # SCRATCHPAD-2). Only read the 8 data bytes -- reading a 9th byte
        # would just sample the idle bus (0xFF) and fail a bogus CRC check.
        data = bytearray(8)
        self.ow.readinto(data)
        return data

    # ------------------------------------------------------------------
    # Convenience layer: store/read sensor metadata (depth + chain number)
    #
    # Byte 0 = depth, byte 1 = chain number, both single bytes (0..255).
    # Remaining 6 bytes of the block are left free (set to 0xFF here so an
    # unwritten-looking value is distinguishable if you ever inspect them).
    # ------------------------------------------------------------------

    def write_metadata(self, rom, depth, chain, addr=_META_ADDR, verify=True):
        """Permanently store depth and chain number in the sensor EEPROM.
        Call this once at provisioning time, NOT in the logging loop.
        """
        if not (0 <= depth <= 255 and 0 <= chain <= 255):
            raise ValueError("depth and chain must each fit in one byte (0..255)")

        block = bytearray(b"\xff" * 8)
        block[0] = depth
        block[1] = chain

        self.write_scratch2(rom, addr, block)
        if verify:
            staged = self.read_scratch2(rom, addr)
            if staged[0] != depth or staged[1] != chain:
                raise Exception("scratchpad-2 verify failed before commit")
        self.copy_scratch2(rom)

    def read_metadata(self, rom, addr=_META_ADDR):
        """Read (depth, chain) back from the sensor EEPROM.
        Cheap enough to call on every read cycle.
        """
        block = self.read_eeprom(rom, addr)
        return block[0], block[1]

    # ------------------------------------------------------------------
    # ASCII text in the user EEPROM
    #
    # The EEPROM stores raw bytes, so ASCII is just bytes 0..127. One
    # 8-byte block holds up to 8 characters. Strings are NUL-padded to the
    # block size and NUL-stripped on read. Longer strings span consecutive
    # 8-byte blocks (one program cycle each).
    # ------------------------------------------------------------------

    def _encode_ascii(self, text):
        """Return `text` as ASCII bytes, rejecting non-ASCII characters."""
        raw = text.encode("ascii")  # raises on chars > 0x7F in CPython;
        for b in raw:               # MicroPython is lax, so check explicitly
            if b > 0x7F:
                raise ValueError("non-ASCII character in text")
        return raw

    def write_label(self, rom, text, addr=_META_ADDR, verify=True):
        """Store a short ASCII string (up to 8 chars) in one EEPROM block.
        Call at provisioning time, not in the logging loop.
        """
        raw = self._encode_ascii(text)
        if len(raw) > 8:
            raise ValueError("label must be 8 characters or fewer "
                             "(use write_text for longer strings)")
        block = bytearray(8)          # NUL-padded (0x00)
        block[0:len(raw)] = raw

        self.write_scratch2(rom, addr, block)
        if verify:
            staged = self.read_scratch2(rom, addr)
            if staged != block:
                raise Exception("scratchpad-2 verify failed before commit")
        self.copy_scratch2(rom)

    def read_label(self, rom, addr=_META_ADDR):
        """Read one 8-byte block back as an ASCII string (NUL-stripped)."""
        block = self.read_eeprom(rom, addr)
        # Keep everything up to the first NUL.
        end = 0
        while end < len(block) and block[end] != 0x00:
            end += 1
        return bytes(block[:end]).decode("ascii")

    def write_text(self, rom, text, addr=_META_ADDR, verify=True):
        """Store an ASCII string of arbitrary length across consecutive
        8-byte EEPROM blocks starting at `addr`. Each block is a separate
        program cycle. Watch the 2 Kb (256-byte / 32-block) total capacity.
        """
        raw = self._encode_ascii(text)
        if addr & 0x07:
            raise ValueError("address must be on an 8-byte boundary")

        # Pad up to a whole number of 8-byte blocks.
        pad = (-len(raw)) % 8
        raw = raw + b"\x00" * pad

        for i in range(0, len(raw), 8):
            block_addr = addr + i
            if block_addr > 0x00F8:   # last block starts at 0x00F8
                raise ValueError("text exceeds EEPROM capacity")
            block = bytearray(raw[i:i + 8])
            self.write_scratch2(rom, block_addr, block)
            if verify:
                if self.read_scratch2(rom, block_addr) != block:
                    raise Exception("scratchpad-2 verify failed before commit")
            self.copy_scratch2(rom)

    def read_text(self, rom, addr=_META_ADDR, blocks=1):
        """Read `blocks` consecutive 8-byte blocks and return the joined
        ASCII string (NUL-stripped from the end).
        """
        out = bytearray()
        for i in range(blocks):
            out += self.read_eeprom(rom, addr + i * 8)
        # Strip trailing NUL padding only.
        while len(out) and out[-1] == 0x00:
            out = out[:-1]
        return bytes(out).decode("ascii")
