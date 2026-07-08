[app]
# (str) Title of your application
title = Trust Chat

# (str) Version number
version = 0.1

# (str) Package name
package.name = trustchat

# (str) Package domain (needed for android/ios packaging)
package.domain = org.trustchat

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (list) List of inclusions using pattern matching
source.include_patterns = network.py

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = hostpython3==3.11,python3==3.11,kivy==2.3.0

# (str) Supported orientation (one of landscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Presplash background color (for loading screen)
presplash.color = #2196F3

# (str) Icon of the application
# icon.filename = icon.png

# ========== Android ==========

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# (int) Target Android API
android.api = 33

# (int) Minimum API required
android.minapi = 21

# (int) NDK API
android.ndk_api = 21

# (str) The Android arch to build for
android.arch = armeabi-v7a,arm64-v8a

# (str) python-for-android branch to use
p4a.branch = develop

# (str) NDK version to use
android.ndk = 25c

# (bool) Use the Google Play Store (not needed for direct APK distribution)
android.allow_backup = True

# ========== iOS ==========
# (not used, just keeping defaults)
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

# ========== Buildozer ==========

# (str) Path to buildozer log file
log_level = 2

# (int) Display a warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
