package org.ecophysio.datalogger

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.math.abs

private const val ACTION_USB_PERMISSION = "org.ecophysio.datalogger.USB_PERMISSION"

class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()

    /** False after the user pressed Disconnect, so the Pico resetting itself does not reconnect us. */
    private var autoConnect = true

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val dev = IntentCompat.getParcelableExtra(intent, UsbManager.EXTRA_DEVICE, UsbDevice::class.java)
            when (intent.action) {
                ACTION_USB_PERMISSION ->
                    if (dev != null && intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) vm.connect(dev)
                UsbManager.ACTION_USB_DEVICE_ATTACHED -> if (autoConnect) tryConnect()
                UsbManager.ACTION_USB_DEVICE_DETACHED -> dev?.let(vm::onDetached)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        ContextCompat.registerReceiver(
            this, usbReceiver, IntentFilter(ACTION_USB_PERMISSION), ContextCompat.RECEIVER_NOT_EXPORTED
        )
        ContextCompat.registerReceiver(
            this, usbReceiver,
            IntentFilter().apply {
                addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED)
                addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
            },
            ContextCompat.RECEIVER_EXPORTED,
        )
        setContent {
            val dark = isSystemInDarkTheme()
            MaterialTheme(colorScheme = if (dark) darkColorScheme() else lightColorScheme()) {
                Surface(Modifier.fillMaxSize()) {
                    Screen(
                        vm,
                        onConnect = { autoConnect = true; tryConnect() },
                        onDisconnect = { restart -> autoConnect = false; vm.disconnect(restart) },
                    )
                }
            }
        }
        if (savedInstanceState == null) tryConnect()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == UsbManager.ACTION_USB_DEVICE_ATTACHED && autoConnect) tryConnect()
    }

    override fun onDestroy() {
        unregisterReceiver(usbReceiver)
        super.onDestroy()
    }

    private fun tryConnect() {
        if (vm.state.value.connected) return
        val dev = vm.findPico() ?: return
        if (vm.hasPermission(dev)) {
            vm.connect(dev)
        } else {
            val flags = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
            val pi = PendingIntent.getBroadcast(
                this, 0, Intent(ACTION_USB_PERMISSION).setPackage(packageName), flags
            )
            getSystemService(UsbManager::class.java).requestPermission(dev, pi)
        }
    }
}

private val timeFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

@Composable
private fun Screen(vm: MainViewModel, onConnect: () -> Unit, onDisconnect: (Boolean) -> Unit) {
    val s by vm.state.collectAsStateWithLifecycle()
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            vm.getApplication<android.app.Application>().contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            vm.setFolder(uri)
        }
    }
    var now by remember { mutableStateOf(LocalDateTime.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = LocalDateTime.now()
            delay(1000L - System.currentTimeMillis() % 1000L)
        }
    }

    LazyColumn(
        Modifier.fillMaxSize().safeDrawingPadding().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Spacer(Modifier.height(8.dp))
            Text("Datalogger", style = MaterialTheme.typography.headlineMedium)
            Text(s.status, style = MaterialTheme.typography.bodyMedium)
            if (s.busy) {
                Spacer(Modifier.height(6.dp))
                val p = s.progress
                if (p != null) LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth())
                else LinearProgressIndicator(Modifier.fillMaxWidth())
                s.progressText?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        }

        s.error?.let { err ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Column(Modifier.padding(12.dp)) {
                        Text(err, color = MaterialTheme.colorScheme.onErrorContainer)
                        TextButton(onClick = vm::dismissError) { Text("OK") }
                    }
                }
            }
        }

        item {
            Section("Connection") {
                if (s.connected) {
                    Text("Connected to " + s.deviceName.ifEmpty { "datalogger" }, fontWeight = FontWeight.SemiBold)
                    Text(
                        "While connected the logger is paused. When you are done, tap Disconnect and unplug: " +
                            "it restarts by itself and resumes logging.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onDisconnect(true) }, enabled = !s.busy) { Text("Disconnect") }
                    }
                } else {
                    Text(
                        "Connect the Pico's USB port to the phone with an OTG adapter. " +
                            "Tick \"always open\" in Android's prompt to skip it next time.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Button(onClick = onConnect, enabled = !s.busy) { Text("Connect") }
                }
            }
        }

        if (s.connected) {
            item {
                Section("Clock and battery") {
                    val info = s.info
                    val devTime = s.clockOffset?.let { now.plusSeconds(it) }
                    InfoRow("Datalogger", devTime?.format(timeFmt) ?: info?.timeError ?: "-")
                    InfoRow("Phone", now.format(timeFmt))
                    s.clockOffset?.let { off ->
                        val txt = when {
                            off == 0L -> "in sync"
                            abs(off) < 120 -> "%+d s".format(off)
                            abs(off) < 7200 -> "%+.1f min".format(off / 60.0)
                            else -> "%+.1f h".format(off / 3600.0)
                        }
                        InfoRow("Difference", txt, warn = abs(off) > 5)
                    }
                    InfoRow("Battery", info?.battery?.let { "%.2f V".format(it) } ?: info?.batteryError ?: "-")
                    info?.internalTemp?.let { InfoRow("Pico temp.", "%.1f °C".format(it)) }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = vm::refreshInfo, enabled = !s.busy) { Text("Refresh") }
                        OutlinedButton(onClick = vm::setClock, enabled = !s.busy) { Text("Set to phone time") }
                    }
                }
            }

            item {
                Section("SD card") {
                    InfoRow("Save to", s.folder ?: "no folder chosen", warn = s.folder == null)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { pickFolder.launch(null) }) { Text("Choose folder") }
                        OutlinedButton(onClick = vm::listFiles, enabled = !s.busy) { Text("Refresh list") }
                    }
                    val toGet = s.files.count { !it.upToDate }
                    Button(
                        onClick = vm::downloadNew, enabled = !s.busy && s.files.isNotEmpty(),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text(if (toGet == 0) "Phone copy is up to date" else "Download new & changed ($toGet)") }
                    if (s.selected.isNotEmpty()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = vm::downloadSelected, enabled = !s.busy) {
                                Text("Download selected (${s.selected.size})")
                            }
                            TextButton(onClick = vm::selectNone) { Text("Clear") }
                        }
                    }
                    Text(
                        "${s.files.size} file(s), ${fmtSize(s.files.sumOf { it.size })}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }

            items(s.files, key = { it.name }) { f ->
                Row(
                    Modifier.fillMaxWidth().clickable { vm.toggle(f.name) },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = f.name in s.selected, onCheckedChange = { vm.toggle(f.name) })
                    Column(Modifier.weight(1f)) {
                        Text(f.name, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodyMedium)
                        Text(fmtSize(f.size), style = MaterialTheme.typography.bodySmall)
                    }
                    val (label, color) = when {
                        f.upToDate -> "on phone" to MaterialTheme.colorScheme.primary
                        f.phoneSize == null -> "new" to MaterialTheme.colorScheme.tertiary
                        else -> "changed" to MaterialTheme.colorScheme.tertiary
                    }
                    Text(label, color = color, style = MaterialTheme.typography.labelMedium)
                    Spacer(Modifier.width(8.dp))
                }
                HorizontalDivider()
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String, warn: Boolean = false) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.width(110.dp), style = MaterialTheme.typography.bodyMedium)
        Text(
            value,
            fontFamily = FontFamily.Monospace,
            color = if (warn) MaterialTheme.colorScheme.error else Color.Unspecified,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

private fun fmtSize(b: Long) = when {
    b < 1024 -> "$b B"
    b < 1024 * 1024 -> "%.1f KB".format(b / 1024.0)
    else -> "%.2f MB".format(b / 1048576.0)
}
