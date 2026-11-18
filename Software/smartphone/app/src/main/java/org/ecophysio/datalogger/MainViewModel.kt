package org.ecophysio.datalogger

import android.app.Application
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Duration
import java.time.LocalDateTime

data class FileRow(val name: String, val size: Long, val phoneSize: Long?) {
    val upToDate get() = phoneSize == size
}

data class UiState(
    val connected: Boolean = false,
    val busy: Boolean = false,
    val status: String = "Plug the datalogger into the phone with a USB-OTG cable.",
    val deviceName: String = "",
    val info: DeviceInfo? = null,
    /** device clock minus phone clock, seconds */
    val clockOffset: Long? = null,
    val files: List<FileRow> = emptyList(),
    val selected: Set<String> = emptySet(),
    val progressText: String? = null,
    val progress: Float? = null,
    val folder: String? = null,
    val error: String? = null,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    private val usb = app.getSystemService(UsbManager::class.java)
    val store = FolderStore(app)
    private val lock = Mutex()
    private var logger: Datalogger? = null
    private var device: UsbDevice? = null
    private var keepAlive: Job? = null

    init {
        _state.update { it.copy(folder = store.displayName()) }
    }

    fun findPico(): UsbDevice? = usb.deviceList.values.firstOrNull { it.vendorId == UsbCdc.PICO_VID }

    fun hasPermission(d: UsbDevice) = usb.hasPermission(d)

    fun setFolder(uri: Uri) {
        store.treeUri = uri
        _state.update { it.copy(folder = store.displayName()) }
        refreshPhoneSizes()
    }

    fun dismissError() = _state.update { it.copy(error = null) }

    fun toggle(name: String) = _state.update {
        it.copy(selected = if (name in it.selected) it.selected - name else it.selected + name)
    }

    fun selectNone() = _state.update { it.copy(selected = emptySet()) }

    // ---- connection --------------------------------------------------------

    fun connect(d: UsbDevice) {
        if (logger != null || _state.value.busy) return
        device = d
        run("Connecting to the datalogger...") {
            val port = UsbCdc.open(usb, d)
            val dl = Datalogger(port)
            try {
                dl.connect()
            } catch (e: Exception) {
                dl.close()
                throw e
            }
            logger = dl
            _state.update { it.copy(connected = true, deviceName = dl.deviceName) }
            startKeepAlive()
            doReadInfo(dl)
            doListFiles(dl)
            "Connected"
        }
    }

    fun onDetached(d: UsbDevice) {
        if (device?.deviceName == d.deviceName) dropConnection("Datalogger unplugged.")
    }

    private fun dropConnection(msg: String) {
        keepAlive?.cancel()
        keepAlive = null
        val l = logger
        logger = null
        device = null
        viewModelScope.launch(Dispatchers.IO) { try { l?.close() } catch (_: Exception) {} }
        _state.update {
            it.copy(connected = false, busy = false, status = msg, info = null, clockOffset = null,
                progress = null, progressText = null)
        }
    }

    private fun startKeepAlive() {
        keepAlive?.cancel()
        keepAlive = viewModelScope.launch(Dispatchers.IO) {
            while (isActive) {
                delay(2500)
                val l = logger ?: break
                try {
                    lock.withLock { l.keepAlive() }
                } catch (e: Exception) {
                    dropConnection("Lost contact with the datalogger: ${e.message}")
                    break
                }
            }
        }
    }

    /** Leave the REPL; the watchdog then resets the Pico and main.py starts again. */
    fun disconnect(restartNow: Boolean) {
        val l = logger ?: return
        keepAlive?.cancel()
        viewModelScope.launch(Dispatchers.IO) {
            lock.withLock {
                if (restartNow) l.restart()
            }
            dropConnection(
                "Disconnected. The datalogger restarts within 8 s and resumes logging once unplugged."
            )
        }
    }

    // ---- operations --------------------------------------------------------

    fun refreshInfo() = run("Reading clock and battery...") { doReadInfo(need()); "Info updated" }

    fun listFiles() = run("Reading SD card...") { doListFiles(need()); "File list updated" }

    fun setClock() = run("Setting the clock...") {
        val dl = need()
        dl.setTime { LocalDateTime.now() }
        doReadInfo(dl)
        "Clock set to phone time"
    }

    fun downloadNew() {
        val names = _state.value.files.filter { !it.upToDate }.map { it.name }
        download(names)
    }

    fun downloadSelected() = download(_state.value.files.map { it.name }.filter { it in _state.value.selected })

    private fun download(names: List<String>) {
        if (store.treeUri == null) {
            _state.update { it.copy(error = "Choose a destination folder first.") }
            return
        }
        if (names.isEmpty()) {
            _state.update { it.copy(status = "Nothing to download, phone copy is up to date.") }
            return
        }
        run("Downloading...") {
            val dl = need()
            val existing = store.existing().toMutableMap()
            val tmpDir = getApplication<Application>().cacheDir
            var total = 0L
            val t0 = System.currentTimeMillis()
            var lastUi = 0L
            dl.download(
                names, tmpDir,
                progress = { idx, count, name, got, size ->
                    val now = System.currentTimeMillis()
                    if (now - lastUi > 150 || got == size) {
                        lastUi = now
                        _state.update {
                            it.copy(
                                progressText = "File ${idx + 1}/$count: $name",
                                progress = if (size > 0) got.toFloat() / size else 1f,
                            )
                        }
                    }
                },
                onFile = { name, f ->
                    total += f.length()
                    store.save(name, f, existing)
                },
            )
            val secs = (System.currentTimeMillis() - t0) / 1000.0
            refreshPhoneSizesNow()
            _state.update { it.copy(selected = emptySet()) }
            "Downloaded ${names.size} file(s), %.0f KB in %.1f s".format(total / 1024.0, secs)
        }
    }

    private fun doReadInfo(dl: Datalogger) {
        val info = dl.readInfo()
        val offset = info.time?.let { Duration.between(LocalDateTime.now(), it).seconds }
        _state.update { it.copy(info = info, clockOffset = offset, deviceName = info.name.ifEmpty { it.deviceName }) }
    }

    private fun doListFiles(dl: Datalogger) {
        val remote = dl.listFiles()
        val phone = store.existing()
        _state.update { s ->
            s.copy(files = remote.map { FileRow(it.name, it.size, phone[it.name]?.second) },
                selected = s.selected.filter { n -> remote.any { it.name == n } }.toSet())
        }
    }

    private fun refreshPhoneSizesNow() {
        val phone = store.existing()
        _state.update { s -> s.copy(files = s.files.map { it.copy(phoneSize = phone[it.name]?.second) }) }
    }

    private fun refreshPhoneSizes() = viewModelScope.launch(Dispatchers.IO) { refreshPhoneSizesNow() }

    /** Run one device operation in the background, one at a time. */
    private fun need(): Datalogger = logger ?: throw ReplException("Not connected")

    private fun run(busyText: String, block: suspend () -> String) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true, status = busyText, error = null) }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val msg = lock.withLock { block() }
                _state.update { it.copy(busy = false, status = msg, progress = null, progressText = null) }
            } catch (e: Exception) {
                val text = e.message?.trim()?.lines()?.lastOrNull { it.isNotBlank() } ?: e.toString()
                if (logger == null || e is java.io.IOException && e !is ReplException) {
                    dropConnection("Not connected")
                }
                _state.update {
                    it.copy(busy = false, status = "Failed", error = text, progress = null, progressText = null)
                }
            }
        }
    }

    override fun onCleared() {
        keepAlive?.cancel()
        logger?.let { l -> try { l.close() } catch (_: Exception) {} }
        logger = null
    }
}
