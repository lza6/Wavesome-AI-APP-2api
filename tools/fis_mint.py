#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/fis_mint.py — Firebase Installation (FIS) 发号器

用途: 生成 wavesome-ai 项目的 FID + FIS authToken。
实测结论 (2026-10-29):
  ✅ FIS 注册成功, 且【改装 APK 的证书也能过】—— 该项目未做 Android 证书白名单校验。
  ❌ FCM registration token 无法纯 REST 获取: fcmregistrations.googleapis.com 的
     RegisterRequest 只暴露 `android.package_name` 字段 (其余字段全部 Unknown name),
     真正的 FCM token 由设备侧 GmsCore 通过 MCS 连接签发。
  ❌ FIS authToken / FID 均不能充当上游 device-token (实测上游回 Token Error)。

因此本工具的价值是: 批量拿 FID/authToken (可做安装实例统计、Firebase 侧探测),
不能替代真机取 FCM token。取真 token 见 tools/token_from_emulator.py。
"""
from __future__ import annotations

import argparse
import json

import requests

API_KEY = "AIzaSyDTH4p7K3SmKiH-gVvzsN7YHoP1I9k7kfA"
APP_ID = "1:676955275610:android:11f8fd986389a3dff07363"
PKG = "com.wave.wavesome.ai.image.generator"
# 改装包证书 SHA1 (实测 Firebase 侧不校验, 原版证书未取到也不影响)
CERT_SHA1 = "2412F88AC73778C3D659D47A3112E27898F953B9"
UA = "okhttp/4.9.3"


def mint() -> dict:
    url = "https://firebaseinstallations.googleapis.com/v1/projects/wavesome-ai/installations"
    r = requests.post(
        url,
        json={"appId": APP_ID, "authVersion": "FIS_v2", "sdkVersion": "a:17.1.0"},
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
            "x-goog-api-key": API_KEY,
            "X-Android-Package": PKG,
            "X-Android-Cert": CERT_SHA1,
        },
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    return {"fid": d["fid"], "authToken": d["authToken"]["token"],
            "expiresIn": d["authToken"].get("expiresIn"),
            "refreshToken": d.get("refreshToken")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--count", type=int, default=1)
    ap.add_argument("-o", "--out", default="")
    a = ap.parse_args()
    rows = [mint() for _ in range(a.count)]
    for r in rows:
        print(r["fid"], r["authToken"][:40] + "...")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        print("saved ->", a.out)
