package org.ecophysio.datalogger

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.webkit.MimeTypeMap
import java.io.File
import java.io.IOException

/** Saves files into a folder the user picked (Storage Access Framework). */
class FolderStore(private val context: Context) {

    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var treeUri: Uri?
        get() = prefs.getString("tree", null)?.let(Uri::parse)
        set(v) = prefs.edit().putString("tree", v?.toString()).apply()

    fun displayName(): String? {
        val tree = treeUri ?: return null
        val id = DocumentsContract.getTreeDocumentId(tree)
        // e.g. "primary:Download/datalogger" -> "Download/datalogger"
        return id.substringAfter(':', id).ifEmpty { "Internal storage" }
    }

    private fun parentDoc(tree: Uri) =
        DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))

    /** name -> (document uri, size) of the files already in the folder. */
    fun existing(): Map<String, Pair<Uri, Long>> {
        val tree = treeUri ?: return emptyMap()
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        val out = HashMap<String, Pair<Uri, Long>>()
        try {
            context.contentResolver.query(
                children,
                arrayOf(
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                    DocumentsContract.Document.COLUMN_SIZE,
                    DocumentsContract.Document.COLUMN_MIME_TYPE,
                ),
                null, null, null
            )?.use { c ->
                while (c.moveToNext()) {
                    if (c.getString(3) == DocumentsContract.Document.MIME_TYPE_DIR) continue
                    val uri = DocumentsContract.buildDocumentUriUsingTree(tree, c.getString(0))
                    out[c.getString(1)] = uri to (if (c.isNull(2)) -1L else c.getLong(2))
                }
            }
        } catch (_: Exception) {
            // folder deleted or permission revoked
        }
        return out
    }

    fun save(name: String, src: File, existing: Map<String, Pair<Uri, Long>>) {
        val tree = treeUri ?: throw IOException("No destination folder chosen")
        val resolver = context.contentResolver
        val target = existing[name]?.first ?: run {
            val ext = name.substringAfterLast('.', "").lowercase()
            val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "application/octet-stream"
            DocumentsContract.createDocument(resolver, parentDoc(tree), mime, name)
                ?: throw IOException("Could not create $name")
        }
        resolver.openOutputStream(target, "wt")?.use { out ->
            src.inputStream().use { it.copyTo(out) }
        } ?: throw IOException("Could not write $name")
    }
}
