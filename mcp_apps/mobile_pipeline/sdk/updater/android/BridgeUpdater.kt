package com.nienfos.updater

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.ClipData
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.provider.Settings
import androidx.core.content.FileProvider
import com.facebook.react.ReactPackage
import com.facebook.react.bridge.*
import com.facebook.react.uimanager.ViewManager
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors

/** Preview-only, user-confirmed updater. Android verifies the signature again at install. */
@android.annotation.TargetApi(28)
class BridgeUpdater(private val ctx: ReactApplicationContext) : ReactContextBaseJavaModule(ctx) {
  private val executor = Executors.newSingleThreadExecutor()
  private val prefs get() = ctx.getSharedPreferences("bridge_updater", Context.MODE_PRIVATE)
  private val manager get() = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
  private val directory get() = File(ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "bridge_updates").apply { mkdirs() }
  override fun getName() = "BridgeUpdater"
  override fun getConstants(): Map<String, Any> {
    val info = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
    return mapOf("version" to (info.versionName ?: ""), "build" to (if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()).toDouble(), "packageId" to ctx.packageName)
  }
  private fun run(promise: Promise, block: () -> Any?) {
    executor.execute { try { promise.resolve(block()) } catch (e: Exception) { promise.reject("UPDATE_FAILED", e.message ?: "Update failed") } }
  }
  private fun apk(hash: String): File {
    require(hash.matches(Regex("[a-f0-9]{64}"))) { "Invalid checksum" }
    return File(directory, "$hash.apk")
  }
  @ReactMethod fun download(url: String, hash: String, size: Double, promise: Promise) = run(promise) {
    require(android.os.Build.VERSION.SDK_INT >= 28) { "Android 9 or newer required" }
    val uri = Uri.parse(url)
    require(uri.scheme == "https" && uri.host == BRIDGE_HOST && uri.userInfo == null &&
      uri.port in listOf(-1, 443) && uri.path?.startsWith("/app-updates/$SOURCE_APP/apk/") == true) { "Untrusted URL" }
    require(size > 0 && size <= 500_000_000 && size == size.toLong().toDouble()) { "Invalid size" }
    val file = apk(hash)
    var id = prefs.getLong("downloadId", -1)
    val same = prefs.getString("hash", "") == hash && prefs.getString("url", "") == url
    if (!same || id == -1L || query(id) == null || query(id)?.first == DownloadManager.STATUS_FAILED) {
      if (id != -1L) manager.remove(id)
      directory.listFiles()?.forEach { it.delete() }
      id = manager.enqueue(DownloadManager.Request(uri)
        .setTitle("Actualización de la aplicación")
        .setDescription("Descargando desde Codex Bridge")
        .setMimeType("application/vnd.android.package-archive")
        .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
        .setAllowedOverRoaming(false)
        .setDestinationUri(Uri.fromFile(file)))
      prefs.edit().putLong("downloadId", id).putString("hash", hash).putString("url", url).apply()
    }
    val started = android.os.SystemClock.elapsedRealtime()
    while (true) {
      val state = query(id) ?: error("Download unavailable; retry")
      if (state.first == DownloadManager.STATUS_FAILED) error("Download failed; retry")
      if (state.first == DownloadManager.STATUS_SUCCESSFUL) break
      if (android.os.SystemClock.elapsedRealtime() - started > 30 * 60 * 1000) error("Download timed out; retry")
      Thread.sleep(750)
    }
    try { verify(file, hash, size.toLong()) } catch (e: Exception) { manager.remove(id); prefs.edit().clear().apply(); file.delete(); throw e }
    "ready"
  }
  private fun query(id: Long): Pair<Int, Long>? {
    manager.query(DownloadManager.Query().setFilterById(id)).use { c ->
      if (!c.moveToFirst()) return null
      return Pair(c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS)), c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR)))
    }
  }
  @Suppress("DEPRECATION")
  private fun verify(file: File, hash: String, size: Long) {
    require(file.isFile && file.length() == size) { "APK size mismatch" }
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input -> val buffer = ByteArray(65536); var n = input.read(buffer); while(n >= 0) { if(n > 0) digest.update(buffer, 0, n); n = input.read(buffer) } }
    require(digest.digest().joinToString("") { "%02x".format(it) } == hash) { "APK checksum mismatch" }
    val pm = ctx.packageManager
    val candidate = pm.getPackageArchiveInfo(file.path, PackageManager.GET_SIGNING_CERTIFICATES) ?: error("Invalid APK")
    val installed = pm.getPackageInfo(ctx.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
    require(candidate.packageName == ctx.packageName && candidate.longVersionCode > installed.longVersionCode) { "Wrong package or downgrade" }
    val expected = installed.signingInfo?.apkContentsSigners?.map { it.toCharsString() }?.toSet()
    val actual = candidate.signingInfo?.apkContentsSigners?.map { it.toCharsString() }?.toSet()
    require(!expected.isNullOrEmpty() && actual == expected) { "APK signature mismatch" }
  }
  @ReactMethod fun install(hash: String, size: Double, promise: Promise) {
    executor.execute {
      try {
        require(android.os.Build.VERSION.SDK_INT >= 28) { "Android 9 or newer required" }
        val file = apk(hash)
        verify(file, hash, size.toLong())
        val activity = ctx.currentActivity ?: error("Return to the app to install")
        activity.runOnUiThread {
          try {
            if (!ctx.packageManager.canRequestPackageInstalls()) {
              activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")))
              promise.resolve("permission")
            } else {
              val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.bridge.updates", file)
              val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
              intent.clipData = ClipData.newRawUri("APK", uri)
              activity.startActivity(intent)
              promise.resolve("installer")
            }
          } catch (e: Exception) { promise.reject("INSTALL_FAILED", e.message) }
        }
      } catch (e: Exception) { promise.reject("INSTALL_FAILED", e.message) }
    }
  }
  companion object {
    private const val BRIDGE_HOST = "__BRIDGE_HOST__"
    private const val SOURCE_APP = "__SOURCE_APP__"
  }
}
class BridgeUpdaterPackage : ReactPackage {
  override fun createNativeModules(ctx: ReactApplicationContext): List<NativeModule> = listOf(BridgeUpdater(ctx))
  override fun createViewManagers(ctx: ReactApplicationContext): List<ViewManager<*, *>> = emptyList()
}
