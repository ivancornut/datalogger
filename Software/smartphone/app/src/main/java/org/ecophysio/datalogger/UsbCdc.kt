package org.ecophysio.datalogger

import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbEndpoint
import android.hardware.usb.UsbInterface
import android.hardware.usb.UsbManager
import java.io.IOException

/**
 * Minimal USB CDC-ACM (virtual serial port) driver, enough to talk to the
 * MicroPython REPL of a Raspberry Pi Pico. Uses only the Android USB host API,
 * so no third-party serial library is needed.
 */
class UsbCdc private constructor(
    private val conn: UsbDeviceConnection,
    private val control: UsbInterface?,
    private val data: UsbInterface,
    private val epIn: UsbEndpoint,
    private val epOut: UsbEndpoint,
) : AutoCloseable {

    private val readBuf = ByteArray(16384)

    companion object {
        const val PICO_VID = 0x2E8A

        fun open(manager: UsbManager, device: UsbDevice): UsbCdc {
            var control: UsbInterface? = null
            var data: UsbInterface? = null
            for (i in 0 until device.interfaceCount) {
                val itf = device.getInterface(i)
                when (itf.interfaceClass) {
                    UsbConstants.USB_CLASS_COMM -> if (control == null) control = itf
                    UsbConstants.USB_CLASS_CDC_DATA -> if (data == null) data = itf
                }
            }
            if (data == null) throw IOException("No serial interface on this USB device")

            var epIn: UsbEndpoint? = null
            var epOut: UsbEndpoint? = null
            for (i in 0 until data.endpointCount) {
                val ep = data.getEndpoint(i)
                if (ep.type != UsbConstants.USB_ENDPOINT_XFER_BULK) continue
                if (ep.direction == UsbConstants.USB_DIR_IN) epIn = ep else epOut = ep
            }
            if (epIn == null || epOut == null) throw IOException("Serial endpoints not found")

            val conn = manager.openDevice(device) ?: throw IOException("Could not open USB device")
            if (control != null) conn.claimInterface(control, true)
            if (!conn.claimInterface(data, true)) {
                conn.close()
                throw IOException("Could not claim USB interface")
            }
            val port = UsbCdc(conn, control, data, epIn, epOut)
            port.configure()
            return port
        }
    }

    private fun configure() {
        val idx = control?.id ?: 0
        // SET_LINE_CODING 115200 8N1 (ignored by the Pico, but polite)
        val lineCoding = byteArrayOf(0x00, 0xC2.toByte(), 0x01, 0x00, 0, 0, 8)
        conn.controlTransfer(0x21, 0x20, 0, idx, lineCoding, lineCoding.size, 1000)
        // SET_CONTROL_LINE_STATE: DTR | RTS. MicroPython only sends output
        // once the host has raised DTR.
        conn.controlTransfer(0x21, 0x22, 0x03, idx, null, 0, 1000)
    }

    /** Write all bytes or throw. */
    fun write(bytes: ByteArray, timeoutMs: Int = 5000) {
        var off = 0
        while (off < bytes.size) {
            val n = minOf(bytes.size - off, 16384)
            val w = conn.bulkTransfer(epOut, bytes, off, n, timeoutMs)
            if (w < 0) throw IOException("USB write failed (device unplugged?)")
            off += w
        }
    }

    /**
     * Read whatever arrives within [timeoutMs]. Returns an empty array on
     * timeout. Note: on Android a failed transfer and a timeout both return -1.
     */
    fun read(timeoutMs: Int): ByteArray {
        val n = conn.bulkTransfer(epIn, readBuf, readBuf.size, timeoutMs)
        return if (n > 0) readBuf.copyOf(n) else ByteArray(0)
    }

    override fun close() {
        try {
            conn.controlTransfer(0x21, 0x22, 0x00, control?.id ?: 0, null, 0, 200)
        } catch (_: Exception) {
        }
        try { conn.releaseInterface(data) } catch (_: Exception) {}
        control?.let { try { conn.releaseInterface(it) } catch (_: Exception) {} }
        conn.close()
    }
}
