plugins {
    id("com.android.application") version "8.4.0" apply false
    id("org.jetbrains.kotlin.android") version "2.0.0" apply false
    // Chaquopy embeds CPython 3.11 in the APK
    id("com.chaquo.python") version "15.0.1" apply false
}
