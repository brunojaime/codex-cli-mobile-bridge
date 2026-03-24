package com.example.codex_mobile_frontend

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var audioFocusRequest: AudioFocusRequest? = null
    private var audioFocusChangeListener: AudioManager.OnAudioFocusChangeListener? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "codex_mobile_frontend/audio_focus",
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "requestTransientRecordingFocus" -> {
                    requestTransientRecordingFocus()
                    result.success(null)
                }
                "releaseRecordingFocus" -> {
                    releaseRecordingFocus()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onDestroy() {
        releaseRecordingFocus()
        super.onDestroy()
    }

    private fun requestTransientRecordingFocus() {
        val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        releaseRecordingFocus()

        val focusChangeListener = AudioManager.OnAudioFocusChangeListener {}
        audioFocusChangeListener = focusChangeListener

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val audioAttributes =
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()

            val focusRequest =
                AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                    .setAudioAttributes(audioAttributes)
                    .setWillPauseWhenDucked(true)
                    .setAcceptsDelayedFocusGain(false)
                    .setOnAudioFocusChangeListener(focusChangeListener)
                    .build()

            audioFocusRequest = focusRequest
            audioManager.requestAudioFocus(focusRequest)
            return
        }

        @Suppress("DEPRECATION")
        audioManager.requestAudioFocus(
            focusChangeListener,
            AudioManager.STREAM_MUSIC,
            AudioManager.AUDIOFOCUS_GAIN_TRANSIENT,
        )
    }

    private fun releaseRecordingFocus() {
        val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            audioFocusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
            audioFocusRequest = null
        } else {
            @Suppress("DEPRECATION")
            audioFocusChangeListener?.let { audioManager.abandonAudioFocus(it) }
        }

        audioFocusChangeListener = null
    }
}
