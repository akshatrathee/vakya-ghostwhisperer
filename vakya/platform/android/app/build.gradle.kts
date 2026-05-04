plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.vakya.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.vakya.app"
        minSdk = 26          // Android 8.0 — required for foreground service audio
        targetSdk = 35
        versionCode = 6      // Sprint 6
        versionName = "0.6.0"

        ndk {
            // Chaquopy supports armeabi-v7a, arm64-v8a, x86, x86_64
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    buildFeatures {
        viewBinding = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// ---------------------------------------------------------------------------
// Chaquopy — Python 3.11 embedded runtime
// ---------------------------------------------------------------------------
chaquopy {
    defaultConfig {
        version = "3.11"

        // Vakya Python package lives in the repo; add it to sys.path.
        // Adjust relative path if the APK is built from a different cwd.
        extractPackages("vakya")

        pip {
            // Core inference stack — CPU-only wheels for ARM64
            install("numpy>=1.24")
            install("soundfile>=0.12")
            install("moonshine-onnx>=0.2.0")     // primary STT, ~58MB
            install("onnxruntime>=1.17")          // Moonshine + Kokoro runtime
            install("pyyaml>=6.0")
            install("pyperclip>=1.8")
            // llama-cpp-python: only loaded when enhanced_cleanup=True
            // install("llama-cpp-python")        // opt-in at runtime via importlib
        }
    }

    sourceSets {
        getByName("main") {
            // Python source root: repo vakya/ package + platform/android/
            srcDir("../../../../")               // exposes vakya/ as a package
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    // BottomSheetDialog for recording UI
    implementation("com.google.android.material:material:1.12.0")
    // Gson for JSON deserialisation of PipelineBridge responses
    implementation("com.google.code.gson:gson:2.11.0")
    // Coroutines for launching background transcription
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
