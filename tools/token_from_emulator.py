#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/token_from_emulator.py — 从 Android 模拟器/真机提取真实 FCM device-token

前置 (本机已实测通过):
  1) Android 30 google_apis x86_64 镜像 (含 GmsCore, 无需 Play Store)
     openchat AVD:  adb -s emulator-5556
  2) adb root   (google_apis 镜像可 root)
  3) adb install -r wavesome.apk  &&  启动 MainActivity
  4) 等 30~60s, FCM 注册完成后 ACCOUNT_PREFERENCES.xml 出现 pushDeviceToken

用法:
  python tools/token_from_emulator.py --serial emulator-5556
  python tools/token_from_emulator.py --serial emulator-5556 --renew   # pm clear 后重新取 (换新设备身份)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

PKG = "com.wave.wavesome.ai.image.generator"
PREFS = f"/data/data/{PKG}/shared_prefs/ACCOUNT_PREFERENCES.xml"


def sh(serial: str, cmd: str, timeout: int = 60) -> str:
    return subprocess.run(["adb", "-s", serial, "shell", cmd],
                          capture_output=True, text=True, timeout=timeout).stdout


def read_token(serial: str) -> str | None:
    raw = sh(serial, f"cat {PREFS}")
    m = re.search(r'<string name="pushDeviceToken">([^<]*)</string>', raw)
    return m.group(1) if m and m.group(1) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="emulator-5556")
    ap.add_argument("--renew", action="store_true", help="pm clear 后重新注册，得到新的设备身份")
    ap.add_argument("--wait", type=int, default=180)
    a = ap.parse_args()

    sh(a.serial, "root")
    if a.renew:
        sh(a.serial, f"pm clear {PKG}")
        sh(a.serial, f"am start -n {PKG}/com.wave.wavesomeai.ui.main.MainActivity")
        print("已清数据并重启 App，等待新的 FCM token…", file=sys.stderr)

    deadline = time.time() + a.wait
    while time.time() < deadline:
        t = read_token(a.serial)
        if t:
            print(t)
            return 0
        time.sleep(4)
    print("超时：未取到 pushDeviceToken（检查 GmsCore 是否存在 / 网络是否可达）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
