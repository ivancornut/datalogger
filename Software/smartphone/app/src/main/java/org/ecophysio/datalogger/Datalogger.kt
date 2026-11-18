package org.ecophysio.datalogger

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDateTime
import java.util.zip.CRC32

data class RemoteFile(val name: String, val size: Long)

data class DeviceInfo(
    val name: String,
    val time: LocalDateTime?,
    val timeError: String?,
    val battery: Double?,
    val batteryError: String?,
    val internalTemp: Double?,
)

/**
 * High-level datalogger operations. Every operation runs a small MicroPython
 * program through the raw REPL, the same way the PC tools do with mpremote.
 *
 * Watchdog: main.py arms an 8 s hardware watchdog that cannot be disarmed.
 * Instead of fighting it we (re)arm it ourselves and the app feeds it every few
 * seconds while connected. If the phone is unplugged, the feeding stops, the
 * Pico resets within 8 s and main.py resumes logging on its own.
 * Not thread-safe: callers serialise access (MainViewModel uses a Mutex).
 */
class Datalogger(private val port: UsbCdc) : AutoCloseable {

    private val repl = RawRepl(port)

    companion object {
        private const val CHUNK = 4096
        private val SYNC = "\u0002DL1\n".toByteArray()

        // Kept in the device's globals for the whole session.
        private val SETUP = """
import json, os, sys, binascii, machine, vfs
from machine import Pin, I2C, ADC, SPI, WDT
_wdt = WDT(timeout=8000)
_wdt.feed()
try:
    with open('info.json') as _f:
        _cfg = json.load(_f)
except Exception:
    _cfg = {}
_rtc = None
def _get_rtc():
    global _rtc
    if _rtc is None:
        _i2c = I2C(0, scl=Pin(5), sda=Pin(4))
        if _cfg.get('rtc_type', 'Adafruit') == 'DS3232':
            from ds3231 import DS3231
            _rtc = DS3231(_i2c)
            _rtc.output_32kHz(False)
        else:
            import urtc
            _rtc = urtc.PCF8523(_i2c)
    return _rtc
def _rtc_now():
    d = _get_rtc().datetime()
    if _cfg.get('rtc_type', 'Adafruit') == 'DS3232':
        return [d[0], d[1], d[2], d[4], d[5], d[6]]
    return [d.year, d.month, d.day, d.hour, d.minute, d.second]
def _rtc_set(t):
    r = _get_rtc()
    if _cfg.get('rtc_type', 'Adafruit') == 'DS3232':
        r.datetime(t)
    else:
        import urtc
        r.datetime(urtc.datetime_tuple(year=t[0], month=t[1], day=t[2], hour=t[3], minute=t[4], second=t[5]))
def _mount():
    import sdcard
    _wdt.feed()
    _cs = Pin(17, Pin.OUT)
    _spi = SPI(0, baudrate=1000000, polarity=0, phase=0, bits=8, firstbit=SPI.MSB,
               sck=Pin(18), mosi=Pin(19), miso=Pin(16))
    _sd = sdcard.SDCard(_spi, _cs)
    _umount()
    vfs.mount(vfs.VfsFat(_sd), '/sd')
    _wdt.feed()
def _umount():
    try:
        vfs.umount('/sd')
    except OSError:
        pass
print(json.dumps({'name': _cfg.get('device_name', '')}))
"""

        private val INFO = """
_wdt.feed()
_r = {'name': _cfg.get('device_name', '')}
try:
    _r['time'] = _rtc_now()
except Exception as e:
    _r['time_err'] = repr(e)
try:
    _r1 = float(_cfg.get('batt_R1', 22))
    _r2 = float(_cfg.get('batt_R2', 68))
    _a = ADC(26)
    _s = 0
    for _i in range(10):
        _s += _a.read_u16()
    _r['batt'] = _s / 10 * 3.3 / 65535 * (_r1 + _r2) / _r1
except Exception as e:
    _r['batt_err'] = repr(e)
_v = ADC(4).read_u16() * 3.3 / 65535
_r['temp'] = 27 - (_v - 0.706) / 0.001721
print(json.dumps(_r))
"""

        private val LIST = """
_mount()
try:
    _l = []
    for _e in os.ilistdir('/sd'):
        if _e[1] == 0x8000:
            _l.append([_e[0], _e[3] if len(_e) > 3 else os.stat('/sd/' + _e[0])[6]])
    print(json.dumps(_l))
finally:
    _umount()
"""

        // Same wire format as Software/computer/fast_download.py, plus watchdog feeding.
        private val DOWNLOAD = """
_mount()
try:
    _w = sys.stdout.buffer.write
    _b = bytearray(CHUNK)
    _m = memoryview(_b)
    _w(b'\x02DL1\n')
    _w(('N%d\n' % len(_names)).encode())
    for _n in _names:
        _p = '/sd/' + _n
        _w(('F%d %s\n' % (os.stat(_p)[6], _n)).encode())
        _c = 0
        with open(_p, 'rb') as _f:
            while True:
                _wdt.feed()
                _k = _f.readinto(_b)
                if not _k:
                    break
                _w(_m[:_k])
                _c = binascii.crc32(_m[:_k], _c)
        _w(('C%08x\n' % (_c & 0xffffffff)).encode())
    _w(b'E\n')
finally:
    _umount()
"""

        private fun pyStr(s: String): String {
            val sb = StringBuilder("'")
            for (ch in s) {
                when {
                    ch == '\\' -> sb.append("\\\\")
                    ch == '\'' -> sb.append("\\'")
                    ch.code < 0x20 -> sb.append(String.format("\\x%02x", ch.code))
                    else -> sb.append(ch)
                }
            }
            return sb.append("'").toString()
        }
    }

    var deviceName: String = ""
        private set

    /** Interrupt main.py, enter the raw REPL and prepare the helpers. */
    fun connect() {
        var last: Exception? = null
        // The Pico may still be booting (it resets itself when USB power appears).
        repeat(4) { attempt ->
            try {
                repl.enter()
                val out = repl.exec(SETUP)
                deviceName = JSONObject(out.trim().lines().last()).optString("name")
                return
            } catch (e: Exception) {
                last = e
                Thread.sleep(if (attempt == 0) 500L else 1500L)
            }
        }
        throw last ?: ReplException("Could not reach the MicroPython REPL")
    }

    fun keepAlive() {
        repl.exec("_wdt.feed()\n", 3000)
    }

    fun readInfo(): DeviceInfo {
        val o = JSONObject(repl.exec(INFO).trim().lines().last())
        val t = o.optJSONArray("time")?.let {
            try {
                LocalDateTime.of(it.getInt(0), it.getInt(1), it.getInt(2), it.getInt(3), it.getInt(4), it.getInt(5))
            } catch (_: Exception) { null }
        }
        return DeviceInfo(
            name = o.optString("name"),
            time = t,
            timeError = if (o.has("time_err")) o.getString("time_err") else if (t == null) "Invalid RTC time" else null,
            battery = if (o.has("batt")) o.getDouble("batt") else null,
            batteryError = if (o.has("batt_err")) o.getString("batt_err") else null,
            internalTemp = if (o.has("temp")) o.getDouble("temp") else null,
        )
    }

    /** Set the RTC. Waits for the next whole second so the clock is set within ~0.1 s. */
    fun setTime(now: () -> LocalDateTime) {
        val code = "_rtc_set(_T)\nprint('ok')\n"
        val start = now()
        val target = start.withNano(0).plusSeconds(1)
        val waitMs = java.time.Duration.between(start, target).toMillis()
        if (waitMs > 0) Thread.sleep(waitMs)
        repl.exec(
            "_T = (%d, %d, %d, %d, %d, %d)\n".format(
                target.year, target.monthValue, target.dayOfMonth, target.hour, target.minute, target.second
            ) + code
        )
    }

    fun listFiles(): List<RemoteFile> {
        val arr = JSONArray(repl.exec(LIST, 20_000).trim().lines().last())
        return (0 until arr.length()).map {
            val e = arr.getJSONArray(it)
            RemoteFile(e.getString(0), e.getLong(1))
        }.sortedBy { it.name }
    }

    /**
     * Stream [names] from the SD card. Each verified file is written to a temp
     * file in [tmpDir] and handed to [onFile]. [progress] gets
     * (index, count, name, bytesReceived, size).
     */
    fun download(
        names: List<String>,
        tmpDir: File,
        progress: (Int, Int, String, Long, Long) -> Unit,
        onFile: (String, File) -> Unit,
    ) {
        val header = "CHUNK = $CHUNK\n_names = [" + names.joinToString(", ") { pyStr(it) } + "]\n"
        repl.execStart(header + DOWNLOAD)
        repl.waitForMarker(SYNC)?.let { throw ReplException(it) }

        val count = repl.readLine().removePrefix("N").toInt()
        for (idx in 0 until count) {
            val line = repl.readLine()
            if (!line.startsWith("F")) throw ReplException("Protocol error: $line")
            val sp = line.indexOf(' ')
            val size = line.substring(1, sp).toLong()
            val name = line.substring(sp + 1)
            val tmp = File(tmpDir, "dl.part")
            val crc = CRC32()
            var got = 0L
            progress(idx, count, name, 0, size)
            FileOutputStream(tmp).use { out ->
                repl.readExact(size.toInt()) { b, n ->
                    out.write(b, 0, n)
                    crc.update(b, 0, n)
                    got += n
                    progress(idx, count, name, got, size)
                }
            }
            val devCrc = repl.readLine().removePrefix("C").toLong(16)
            if (devCrc != crc.value) {
                tmp.delete()
                throw ReplException("CRC mismatch on $name, transfer corrupted")
            }
            onFile(name, tmp)
            tmp.delete()
        }
        if (repl.readLine() != "E") throw ReplException("Protocol error at end of transfer")
        repl.execFinish(10_000)
    }

    /** Hard-reset the Pico so main.py starts again (logging resumes once unplugged). */
    fun restart() {
        try {
            repl.execStart("machine.reset()\n")
        } catch (_: Exception) {
        }
    }

    override fun close() {
        repl.leave()
        port.close()
    }
}
