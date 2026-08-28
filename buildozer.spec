[app]
title = PilotVision Mobile
package.name = pilotvisionmobile
package.domain = org.pilotvision
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1.0

requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.1,pymavlink
orientation = portrait
fullscreen = 0

# Real Android permissions this app actually needs: network (UDP/TCP
# MAVLink) and USB/serial (for a wired telemetry radio or direct USB
# connection to a flight controller).
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE

android.api = 33
android.minapi = 23
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
