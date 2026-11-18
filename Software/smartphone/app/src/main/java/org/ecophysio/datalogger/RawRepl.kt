package org.ecophysio.datalogger

import java.io.IOException

class ReplException(message: String) : IOException(message)

/**
 * MicroPython raw-REPL client, a Kotlin port of _RawRepl in
 * Software/computer/fast_download.py (which is what mpremote does too).
 *
 * Raw REPL exchange:  ^A -> "raw REPL; CTRL-B to exit\r\n>"
 *                     <code> ^D -> "OK" <stdout> ^D <stderr> ^D ">"
 */
class RawRepl(private val port: UsbCdc, var timeoutMs: Long = 10_000) {

    private var buf = ByteArray(65536)
    private var len = 0

    // ---- buffer helpers ---------------------------------------------------

    private fun append(b: ByteArray) {
        if (len + b.size > buf.size) buf = buf.copyOf(maxOf(buf.size * 2, len + b.size))
        System.arraycopy(b, 0, buf, len, b.size)
        len += b.size
    }

    private fun consume(n: Int): ByteArray {
        val out = buf.copyOf(n)
        System.arraycopy(buf, n, buf, 0, len - n)
        len -= n
        return out
    }

    private fun indexOf(marker: ByteArray, from: Int = 0): Int {
        outer@ for (i in from..len - marker.size) {
            for (j in marker.indices) if (buf[i + j] != marker[j]) continue@outer
            return i
        }
        return -1
    }

    private fun fill(deadline: Long) {
        val data = port.read(100)
        if (data.isNotEmpty()) append(data)
        else if (System.currentTimeMillis() > deadline) throw ReplException("Timeout waiting for the datalogger")
    }

    fun drain() {
        while (port.read(50).isNotEmpty()) { /* discard */ }
        len = 0
    }

    fun readUntil(marker: ByteArray, timeout: Long = timeoutMs): ByteArray {
        val deadline = System.currentTimeMillis() + timeout
        var searchFrom = 0
        while (true) {
            val i = indexOf(marker, searchFrom)
            if (i >= 0) return consume(i + marker.size)
            searchFrom = maxOf(0, len - marker.size + 1)
            fill(deadline)
        }
    }

    /** Hand exactly [n] bytes to [sink] as they arrive. */
    fun readExact(n: Int, sink: (ByteArray, Int) -> Unit) {
        var left = n
        while (left > 0) {
            if (len > 0) {
                val take = minOf(left, len)
                sink(buf, take)
                consume(take)
                left -= take
                continue
            }
            fill(System.currentTimeMillis() + timeoutMs)
        }
    }

    /** One line without the trailing \n; throws with the device traceback if the program died. */
    fun readLine(): String {
        val line = readUntil(byteArrayOf('\n'.code.toByte()))
        if (line.contains(0x04)) throw ReplException(readError(line))
        return String(line, 0, line.size - 1, Charsets.UTF_8).trimEnd('\r')
    }

    private fun ByteArray.contains(b: Int) = any { it.toInt() == b }

    private fun readError(already: ByteArray): String {
        val done = already.size >= 2 && already[already.size - 2].toInt() == 4 && already.last() == '>'.code.toByte()
        val rest = if (done) ByteArray(0) else try { readUntil(byteArrayOf(4, '>'.code.toByte()), 3000) } catch (_: ReplException) { ByteArray(0) }
        var text = String(already + rest, Charsets.UTF_8)
        if (text.endsWith("\u0004>")) text = text.dropLast(2)
        text = text.replace('\u0004', '\n').trim()
        return if (text.isEmpty()) "Device error" else text
    }

    // ---- raw REPL -----------------------------------------------------------

    /** Interrupt main.py and switch to the raw REPL. */
    fun enter() {
        port.write("\r\u0003".toByteArray())
        Thread.sleep(100)
        port.write("\u0003".toByteArray())
        Thread.sleep(100)
        drain()
        port.write("\r\u0001".toByteArray())
        readUntil("raw REPL; CTRL-B to exit\r\n>".toByteArray(), 3000)
    }

    /** Back to the normal REPL (no reset). */
    fun leave() {
        try { port.write(byteArrayOf(2), 500) } catch (_: Exception) {}
    }

    /** Send a program and wait until the device has accepted it. */
    fun execStart(code: String) {
        val data = code.toByteArray(Charsets.UTF_8)
        // Plain raw REPL has no flow control: send in small paced chunks like mpremote.
        var i = 0
        while (i < data.size) {
            val end = minOf(i + 256, data.size)
            port.write(data.copyOfRange(i, end))
            Thread.sleep(10)
            i = end
        }
        port.write(byteArrayOf(4))
        val resp = readUntil("OK".toByteArray(), 5000)
        if (!String(resp).endsWith("OK")) throw ReplException("Datalogger refused the program")
    }

    /** Wait for the program to finish; returns stdout or throws with stderr. */
    fun execFinish(timeout: Long = timeoutMs): String {
        val out = readUntil(byteArrayOf(4), timeout)
        val err = readUntil(byteArrayOf(4, '>'.code.toByte()), timeout)
        val errText = String(err, 0, err.size - 2, Charsets.UTF_8).trim()
        if (errText.isNotEmpty()) throw ReplException(errText)
        return String(out, 0, out.size - 1, Charsets.UTF_8)
    }

    fun exec(code: String, timeout: Long = timeoutMs): String {
        execStart(code)
        return execFinish(timeout)
    }

    /**
     * Skip everything up to [marker]. Returns null when found, or the output
     * read so far if the program ended before printing it (an exception).
     */
    fun waitForMarker(marker: ByteArray, timeout: Long = 30_000): String? {
        val deadline = System.currentTimeMillis() + timeout
        while (true) {
            val i = indexOf(marker)
            if (i >= 0) { consume(i + marker.size); return null }
            if (indexOf(byteArrayOf(4)) >= 0) return readError(consume(len))
            fill(deadline)
        }
    }
}
