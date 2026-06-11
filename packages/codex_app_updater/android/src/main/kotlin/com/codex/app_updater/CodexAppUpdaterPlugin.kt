package com.codex.app_updater

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
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
