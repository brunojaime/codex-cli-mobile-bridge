package com.codex.app_updater

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

class CodexAppUpdaterPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
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
            "launchInstaller" -> launchInstaller(call, result)
            else -> result.notImplemented()
        }
    }

    private fun launchInstaller(call: MethodCall, result: MethodChannel.Result) {
        val apkPath = call.argument<String>("apkPath")
        if (apkPath.isNullOrBlank()) {
            result.error("invalidPath", "APK path is required.", null)
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !context.packageManager.canRequestPackageInstalls()
        ) {
            if (openUnknownAppsSettings()) {
                result.success("permissionRequired")
            } else {
                result.error(
                    "installerUnavailable",
                    "Unknown app install settings are unavailable.",
                    null,
                )
            }
            return
        }
        val apkFile = File(apkPath)
        if (!apkFile.exists()) {
            result.error("invalidPath", "APK file does not exist.", null)
            return
        }
        val authority = "${context.packageName}.codex_app_updater.fileprovider"
        val apkUri: Uri = FileProvider.getUriForFile(context, authority, apkFile)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(apkUri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            context.startActivity(intent)
            result.success("launched")
        } catch (_: ActivityNotFoundException) {
            result.error("installerUnavailable", "No Android APK installer found.", null)
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
        }
    }
}
