package com.vakya.app

import android.app.Application
import android.os.Environment
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Application subclass — initialises Chaquopy Python runtime once,
 * then calls vakya.platform.android.main.init() to get a PipelineBridge.
 */
class VakyaApplication : Application() {

    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()

        // Start Python runtime (must happen before any Python call)
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Initialise the bridge asynchronously — avoids blocking main thread
        appScope.launch {
            VakyaBridge.init(
                configDir  = filesDir.absolutePath,
                modelsDir  = getExternalFilesDir(null)?.absolutePath
                               ?: filesDir.absolutePath,
            )
        }
    }
}
