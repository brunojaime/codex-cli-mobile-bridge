package com.codex.app_updater

import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

class CodexAppUpdaterPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private companion object {
        const val PREFS_NAME = "codex_app_updater_downloads"
        const val KEY_DOWNLOAD_ID = "download_id"
        const val KEY_DOWNLOAD_URL = "download_url"
        const val KEY_FILE_NAME = "file_name"
        const val KEY_APK_PATH = "apk_path"
        const val DOWNLOAD_TIMEOUT_MS = 30L * 60L * 1000L
        const val POLL_INTERVAL_MS = 500L
    }

    private lateinit var channel: MethodChannel
    private lateinit var context: Context

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "codex_app_updater/installer")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "downloadApk" -> downloadApk(call, result)
            "launchInstaller" -> launchInstaller(call, result)
            else -> result.notImplemented()
        }
    }

    private fun downloadApk(call: MethodCall, result: MethodChannel.Result) {
        val url = call.argument<String>("url")
        val rawFileName = call.argument<String>("fileName") ?: "codex-update.apk"
        if (url.isNullOrBlank()) {
            result.success(
                downloadResult("downloadFailed", message = "Download URL is required."),
            )
            return
        }
        val downloadManager =
            context.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager
        if (downloadManager == null) {
            result.success(
                downloadResult(
                    "unsupported",
                    message = "Android DownloadManager is unavailable.",
                ),
            )
            return
        }
        val downloadsDirectory = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
        if (downloadsDirectory == null) {
            result.success(
                downloadResult(
                    "unsupported",
                    message = "External app downloads directory is unavailable.",
                ),
            )
            return
        }
        val updatesDirectory = File(downloadsDirectory, "codex_app_updates")
        if (!updatesDirectory.exists() && !updatesDirectory.mkdirs()) {
            result.success(
                downloadResult(
                    "downloadFailed",
                    message = "Could not create update download directory.",
                ),
            )
            return
        }
        val safeFileName = rawFileName.replace(Regex("[^A-Za-z0-9._-]"), "_")
        val apkFile = File(updatesDirectory, safeFileName)
        val downloadUri = try {
            Uri.parse(url)
        } catch (_: RuntimeException) {
            result.success(
                downloadResult("downloadFailed", message = "Invalid download URL."),
            )
            return
        }
        val pending = readPendingDownload()
        if (
            pending != null &&
            pending.url == url &&
            pending.fileName == safeFileName &&
            pending.apkPath == apkFile.absolutePath
        ) {
            val state = queryDownload(downloadManager, pending.downloadId)
            when (state.status) {
                DownloadManager.STATUS_SUCCESSFUL -> {
                    if (apkFile.exists() && apkFile.isFile) {
                        result.success(
                            downloadResult(
                                "downloaded",
                                apkPath = apkFile.absolutePath,
                                totalBytes = state.totalBytes,
                            ),
                        )
                        return
                    }
                    clearPendingDownload()
                }
                DownloadManager.STATUS_PENDING,
                DownloadManager.STATUS_RUNNING,
                DownloadManager.STATUS_PAUSED -> {
                    Thread {
                        waitForDownload(downloadManager, pending.downloadId, apkFile, result)
                    }.start()
                    return
                }
                DownloadManager.STATUS_FAILED -> {
                    downloadManager.remove(pending.downloadId)
                    clearPendingDownload()
                }
            }
        } else {
            cleanupPendingDownload(downloadManager)
        }
        if (apkFile.exists()) {
            apkFile.delete()
        }
        val request = try {
            DownloadManager.Request(downloadUri)
                .setTitle(safeFileName)
                .setDescription("Downloading app update")
                .setMimeType("application/vnd.android.package-archive")
                .setAllowedOverMetered(true)
                .setAllowedOverRoaming(true)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationUri(Uri.fromFile(apkFile))
        } catch (error: RuntimeException) {
            result.success(
                downloadResult(
                    "downloadFailed",
                    message = error.message ?: "Could not create download request.",
                ),
            )
            return
        }
        val downloadId = try {
            downloadManager.enqueue(request)
        } catch (error: RuntimeException) {
            result.success(
                downloadResult(
                    "downloadFailed",
                    message = error.message ?: "Could not enqueue APK download.",
                ),
            )
            return
        }
        writePendingDownload(
            PendingDownload(
                downloadId = downloadId,
                url = url,
                fileName = safeFileName,
                apkPath = apkFile.absolutePath,
            ),
        )
        Thread {
            waitForDownload(downloadManager, downloadId, apkFile, result)
        }.start()
    }

    private fun launchInstaller(call: MethodCall, result: MethodChannel.Result) {
        val apkPath = call.argument<String>("apkPath")
        if (apkPath.isNullOrBlank()) {
            result.success(launchResult("fileMissing", "APK path is required."))
            return
        }
        val apkFile = File(apkPath)
        if (!apkFile.exists() || !apkFile.isFile) {
            result.success(launchResult("fileMissing", "APK file does not exist."))
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !context.packageManager.canRequestPackageInstalls()
        ) {
            if (openUnknownAppsSettings()) {
                result.success(
                    launchResult(
                        "unknownSourcesPermissionRequired",
                        "Unknown app install permission is required.",
                    ),
                )
            } else {
                result.success(
                    launchResult(
                        "noActivity",
                        "Unknown app install settings are unavailable.",
                    ),
                )
            }
            return
        }
        val authority = "${context.packageName}.codex_app_updater.fileprovider"
        val apkUri: Uri = try {
            FileProvider.getUriForFile(context, authority, apkFile)
        } catch (error: IllegalArgumentException) {
            result.success(
                launchResult(
                    "invalidUri",
                    error.message ?: "APK file is outside configured FileProvider paths.",
                ),
            )
            return
        } catch (error: SecurityException) {
            result.success(
                launchResult(
                    "securityException",
                    error.message ?: "Android blocked APK URI creation.",
                ),
            )
            return
        }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(apkUri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        val canHandleInstallIntent = context.packageManager.queryIntentActivities(
            intent,
            PackageManager.MATCH_DEFAULT_ONLY,
        ).isNotEmpty()
        if (!canHandleInstallIntent) {
            result.success(launchResult("noActivity", "No Android APK installer found."))
            return
        }
        try {
            context.startActivity(intent)
            result.success(launchResult("installerLaunched"))
        } catch (_: ActivityNotFoundException) {
            result.success(launchResult("noActivity", "No Android APK installer found."))
        } catch (error: SecurityException) {
            result.success(
                launchResult(
                    "securityException",
                    error.message ?: "Android blocked APK installer launch.",
                ),
            )
        } catch (error: IllegalArgumentException) {
            result.success(
                launchResult(
                    "invalidUri",
                    error.message ?: "Invalid APK URI.",
                ),
            )
        } catch (error: RuntimeException) {
            result.success(
                launchResult(
                    "cancelledOrUnknown",
                    error.message ?: "Android installer launch failed.",
                ),
            )
        }
    }

    private fun launchResult(status: String, message: String? = null): Map<String, String> {
        val result = mutableMapOf("status" to status)
        if (!message.isNullOrBlank()) {
            result["message"] = message
        }
        return result
    }

    private fun downloadResult(
        status: String,
        apkPath: String? = null,
        totalBytes: Long? = null,
        message: String? = null,
    ): Map<String, Any> {
        val result = mutableMapOf<String, Any>("status" to status)
        if (!apkPath.isNullOrBlank()) {
            result["apkPath"] = apkPath
        }
        if (totalBytes != null && totalBytes >= 0L) {
            result["totalBytes"] = totalBytes
        }
        if (!message.isNullOrBlank()) {
            result["message"] = message
        }
        return result
    }

    private fun waitForDownload(
        downloadManager: DownloadManager,
        downloadId: Long,
        apkFile: File,
        result: MethodChannel.Result,
    ) {
        val deadline = System.currentTimeMillis() + DOWNLOAD_TIMEOUT_MS
        var lastReason = "Download did not complete."
        while (System.currentTimeMillis() < deadline) {
            val state = try {
                queryDownload(downloadManager, downloadId)
            } catch (error: RuntimeException) {
                complete(
                    result,
                    downloadResult(
                        "downloadFailed",
                        message = error.message ?: "Could not query APK download.",
                    ),
                )
                return
            }
            when (state.status) {
                DownloadManager.STATUS_SUCCESSFUL -> {
                    if (apkFile.exists() && apkFile.isFile) {
                        complete(
                            result,
                            downloadResult(
                                "downloaded",
                                apkPath = apkFile.absolutePath,
                                totalBytes = state.totalBytes,
                            ),
                        )
                    } else {
                        clearPendingDownload()
                        complete(
                            result,
                            downloadResult(
                                "downloadFailed",
                                message = "Downloaded APK is missing from the expected path.",
                            ),
                        )
                    }
                    return
                }
                DownloadManager.STATUS_FAILED -> {
                    downloadManager.remove(downloadId)
                    clearPendingDownload()
                    complete(
                        result,
                        downloadResult(
                            "downloadFailed",
                            message = "DownloadManager failed with reason ${state.reason}.",
                        ),
                    )
                    return
                }
                DownloadManager.STATUS_PAUSED -> {
                    lastReason = "DownloadManager paused with reason ${state.reason}."
                }
            }
            try {
                Thread.sleep(POLL_INTERVAL_MS)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                complete(
                    result,
                    downloadResult(
                        "downloadFailed",
                        message = "Download wait interrupted.",
                    ),
                )
                return
            }
        }
        downloadManager.remove(downloadId)
        clearPendingDownload()
        complete(result, downloadResult("downloadFailed", message = lastReason))
    }

    private fun queryDownload(
        downloadManager: DownloadManager,
        downloadId: Long,
    ): DownloadState {
        val query = DownloadManager.Query().setFilterById(downloadId)
        val cursor = downloadManager.query(query)
        cursor?.use {
            if (it.moveToFirst()) {
                return DownloadState(
                    status = it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)),
                    reason = it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON)),
                    totalBytes = it.getLong(
                        it.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES),
                    ),
                )
            }
        }
        val pendingPath = readPendingDownload()?.apkPath
        if (!pendingPath.isNullOrBlank() && File(pendingPath).exists()) {
            return DownloadState(DownloadManager.STATUS_SUCCESSFUL, 0, File(pendingPath).length())
        }
        return DownloadState(DownloadManager.STATUS_FAILED, DownloadManager.ERROR_UNKNOWN, -1L)
    }

    private fun cleanupPendingDownload(downloadManager: DownloadManager) {
        val pending = readPendingDownload() ?: return
        try {
            downloadManager.remove(pending.downloadId)
        } catch (_: RuntimeException) {
            // DownloadManager may have already dropped the row.
        }
        val apkFile = File(pending.apkPath)
        if (apkFile.exists()) {
            apkFile.delete()
        }
        clearPendingDownload()
    }

    private fun readPendingDownload(): PendingDownload? {
        val prefs = downloadPrefs()
        val downloadId = prefs.getLong(KEY_DOWNLOAD_ID, -1L)
        val url = prefs.getString(KEY_DOWNLOAD_URL, null)
        val fileName = prefs.getString(KEY_FILE_NAME, null)
        val apkPath = prefs.getString(KEY_APK_PATH, null)
        if (downloadId < 0L || url.isNullOrBlank() || fileName.isNullOrBlank() || apkPath.isNullOrBlank()) {
            return null
        }
        return PendingDownload(downloadId, url, fileName, apkPath)
    }

    private fun writePendingDownload(download: PendingDownload) {
        downloadPrefs()
            .edit()
            .putLong(KEY_DOWNLOAD_ID, download.downloadId)
            .putString(KEY_DOWNLOAD_URL, download.url)
            .putString(KEY_FILE_NAME, download.fileName)
            .putString(KEY_APK_PATH, download.apkPath)
            .commit()
    }

    private fun clearPendingDownload() {
        downloadPrefs().edit().clear().commit()
    }

    private fun downloadPrefs(): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private fun complete(result: MethodChannel.Result, value: Map<String, Any>) {
        Handler(Looper.getMainLooper()).post {
            try {
                result.success(value)
            } catch (_: RuntimeException) {
                // Flutter may have recreated the engine while DownloadManager kept running.
            }
        }
    }

    private fun openUnknownAppsSettings(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return true
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${context.packageName}"),
        ).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            context.startActivity(intent)
            return true
        } catch (_: ActivityNotFoundException) {
            val fallback = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            return try {
                context.startActivity(fallback)
                true
            } catch (_: ActivityNotFoundException) {
                false
            }
        } catch (_: SecurityException) {
            return false
        }
    }
}

private data class PendingDownload(
    val downloadId: Long,
    val url: String,
    val fileName: String,
    val apkPath: String,
)

private data class DownloadState(
    val status: Int,
    val reason: Int,
    val totalBytes: Long,
)
