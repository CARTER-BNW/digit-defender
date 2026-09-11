[app]
# Digit Defender - Android packaging (python-for-android via buildozer).
# android/sync.py rewrites `version` from android/VERSION on every sync.
title = Digit Defender
package.name = digitdefender
package.domain = org.johncarter
source.dir = app
source.include_exts = py,png,jpg,jpeg,ttf,otf,txt,json
source.exclude_dirs = tests,saves,__pycache__,docs
source.exclude_patterns = crash.log,config.json*
version = 0.1.1
# pygame = pygame-ce 2.5.8 via the local recipe in p4a-recipes/ (the stock recipe's pygame 2.1.0 cannot build on Python 3.14)
requirements = python3,pygame,numpy,opensimplex
p4a.local_recipes = ./p4a-recipes
orientation = landscape
fullscreen = 1
icon.filename = icon.png
presplash.filename = presplash.png
android.presplash_color = #0C180C
android.archs = arm64-v8a
# target the phone's own Android (16 = API 36): Play Protect on Android 16 refuses to sideload an APK
# targeting API 33 ("built for an older version of Android", INSTALL_FAILED_VERIFICATION_FAILURE)
android.api = 36
android.minapi = 24
# targetSdk 36 turns on predictive back: the Back key then closes the activity without SDL ever
# seeing it. This attribute (appended to <application>) restores the key flow so Back = Escape.
android.extra_manifest_application_arguments = ./manifest_application_args.xml
android.accept_sdk_license = True
android.allow_backup = True
android.no-byte-compile-python = True
android.logcat_filters = *:S python:D
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 0
