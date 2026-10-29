#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wavesome.py — Wavesome.AI v1.0.31 (com.wave.wavesome.ai.image.generator) 协议客户端

协议来源: jadx 静态还原 + 实网黑盒验证 (详见 docs/PROTOCOL.md)

身份模型: 唯一身份 = FCM registration token, 通过 header `device-token` 传递。
          服务端无其它鉴权 (无 Authorization / 无签名 / 无 cookie)。

⚠️ 当前实测状态 (2026-10-29):
    service/generate 对所有 device-token 返回 HTTP 500 {"message":"Token Error. Please contact support!"}
    —— 包括真机/模拟器上真实 App 自身生成的合法 FCM token (已知 App 与未知 App 均失败)。
    service/sketch -> "Sketch generation is disabled"  (服务端开关关闭)
    service/upscale -> "Upscale is disabled"           (服务端开关关闭)
    公开端点 (configs/styles/blocks/gallery/sketches) 全部正常可用。
"""
from __future__ import annotations

import json
import os
import random
import time
import uuid as uuidlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://ailwapi360.waveabc.xyz/api/"
API_VERSION = "31"                      # 服务端接受 >=30 (实测 28/29 -> Version Error, 30~36 通过)
DEFAULT_UA = "okhttp/4.9.3"             # 必须带 UA: 空 UA 会被 Cloudflare 以 1010 拦截

# 服务端错误文案 (已实测)
ERR_VERSION = "Version Error"           # api-version 缺失/过低
ERR_UUID = "UUID Error"                 # uuid(风格) 字段非法或缺失
ERR_TOKEN = "Token Error"               # device-token 校验失败 (当前所有 token 都失败)
ERR_SKETCH_OFF = "Sketch generation is disabled"
ERR_UPSCALE_OFF = "Upscale is disabled"


@dataclass
class WaveResponse:
    """统一的返回结构: 成功是原始图片字节, 失败是服务端 JSON。"""
    ok: bool
    status: int
    content_type: str
    body: bytes
    headers: Dict[str, str]
    elapsed: float
    error: Optional[str] = None

    @property
    def sample_uuid(self) -> Optional[str]:
        return self.headers.get("sample-uuid")

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except Exception:
            return None

    def save(self, path: str) -> str:
        with open(path, "wb") as f:
            f.write(self.body)
        return path


class WaveSomeError(Exception):
    pass


class WaveSome:
    def __init__(
        self,
        device_token: Optional[str] = None,
        country: Optional[str] = None,
        timeout: float = 120.0,
        ua: str = DEFAULT_UA,
        session: Optional[requests.Session] = None,
    ):
        self.device_token = device_token or os.environ.get("WAVESOME_DEVICE_TOKEN")
        self.country = country or os.environ.get("WAVESOME_COUNTRY") or ""
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": ua, "api-version": API_VERSION})
        if self.country:
            self.session.headers["api-country"] = self.country
        if self.device_token:
            self.session.headers["device-token"] = self.device_token

    # ---------------- 内部 ----------------
    def _call(self, method: str, path: str, payload: Optional[dict] = None) -> WaveResponse:
        url = BASE_URL + path.lstrip("/")
        t0 = time.time()
        try:
            r = self.session.request(
                method,
                url,
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except Exception as exc:  # 网络层
            return WaveResponse(False, 0, "", b"", {}, time.time() - t0, error=str(exc))
        elapsed = time.time() - t0
        body = r.content or b""
        ctype = r.headers.get("Content-Type", "")
        error = None
        ok = 200 <= r.status_code < 300
        if ok and not ctype.startswith("image/") and len(body) < 300:
            # 服务端有些开关/错误是裸文本（非 JSON 字符串），例如
            #   "Sketch generation is disabled" / "Upscale is disabled" / "Token Error. ..."
            txt = body.decode("utf-8", "replace").strip().strip('"')
            if "disabled" in txt or "Error." in txt:
                ok = False
                error = txt
        if ok and "json" in ctype:
            # 服务端在 200 里也可能回错误文本 (如 "Sketch generation is disabled")
            j = None
            try:
                j = json.loads(body.decode("utf-8", "replace"))
            except Exception:
                pass
            if isinstance(j, dict) and (j.get("success") is False or "message" in j):
                ok = False
                error = j.get("message") or j.get("error")
            elif isinstance(j, str) and ("disabled" in j or "Error" in j):
                ok = False
                error = j
            elif j is None:
                # 服务端有些开关类是裸文本（非 JSON 字符串），例如 "Sketch generation is disabled"
                txt = body[:200].decode("utf-8", "replace").strip()
                if "disabled" in txt or "Error." in txt:
                    ok = False
                    error = txt
        elif not ok and "json" in ctype:
            try:
                error = json.loads(body.decode("utf-8", "replace")).get("message")
            except Exception:
                error = body[:200].decode("utf-8", "replace")
        return WaveResponse(ok, r.status_code, ctype, body, dict(r.headers), elapsed, error)

    # ---------------- 公开端点 (无需 device-token, 实网已验证) ----------------
    def system_config(self) -> WaveResponse:
        return self._call("GET", "configs/public/system")

    def styles(self) -> WaveResponse:
        return self._call("GET", "public/ai-samples/styles")

    def blocks(self, quantity: int = 10) -> WaveResponse:
        return self._call("GET", f"public/ai-samples/blocks?quantity={int(quantity)}")

    def gallery(self, code: str, page: int = 0) -> WaveResponse:
        return self._call("GET", f"public/ai-samples/gallery/{code}?page={int(page)}")

    def sketches(self) -> WaveResponse:
        return self._call("GET", "public/ai-sketches/list")

    # ---------------- 设备端点 (服务端不做校验, 任意 token 均 200) ----------------
    def device_get(self) -> WaveResponse:
        return self._call("GET", "device/")

    def device_set_premium(self, premium: str = "sub") -> WaveResponse:
        """premium 取值: App 实际只上报 'sub' (订阅激活) 或 '' (未订阅)。"""
        return self._call("PUT", "device/", {"premium": premium})

    def device_delete(self) -> WaveResponse:
        return self._call("DELETE", "device/")

    # ---------------- 付费服务端点 (需 device-token) ----------------
    def generate(
        self,
        prompt: str,
        style_uuid: str,
        width: int = 512,
        height: int = 512,
        aspect_ratio: str = "1:1",
        restore_faces: bool = False,
    ) -> WaveResponse:
        """POST service/generate — 成功返回原始图片字节 (image/jpeg|png) + header sample-uuid。"""
        return self._call(
            "POST",
            "service/generate",
            {
                "prompt": prompt,
                "uuid": style_uuid,
                "width": int(width),
                "height": int(height),
                "aspect_ratio": aspect_ratio,
                "restore_faces": bool(restore_faces),
            },
        )

    def sketch(
        self,
        prompt: str,
        style_uuid: str,
        sketch_base64: str,
        width: int = 512,
        height: int = 512,
        aspect_ratio: str = "1:1",
        restore_faces: bool = False,
    ) -> WaveResponse:
        return self._call(
            "POST",
            "service/sketch",
            {
                "prompt": prompt,
                "uuid": style_uuid,
                "width": int(width),
                "height": int(height),
                "aspect_ratio": aspect_ratio,
                "restore_faces": bool(restore_faces),
                "sketch": sketch_base64,
            },
        )

    def upscale(self, image_uuid: str, scale: int = 2) -> WaveResponse:
        return self._call("POST", "service/upscale", {"uuid": image_uuid, "scale": int(scale)})


# ---------------- 便捷工具 ----------------

def aspect_ratio_table(config: dict) -> Dict[str, Dict[str, dict]]:
    """从线上 config 抽出可用尺寸表: {"1:1": {"1x": {...}, "2x": {...}, "4x": {...}}}"""
    out: Dict[str, Dict[str, dict]] = {}
    for item in config.get("ai.aspect_ratios") or []:
        out[item["name"]] = item.get("scales") or {}
    return out


def pick_prompt(config: dict) -> str:
    labels = config.get("ai.labels") or []
    return random.choice(labels) if labels else "a red fox in snow, oil painting"


def read_emulator_token(serial: str = "emulator-5556",
                        pkg: str = "com.wave.wavesome.ai.image.generator") -> Optional[str]:
    """从已安装 App 的 shared_prefs 读取真实 FCM token (需要 adb root)。"""
    import re
    import subprocess
    path = f"/data/data/{pkg}/shared_prefs/ACCOUNT_PREFERENCES.xml"
    try:
        raw = subprocess.run(["adb", "-s", serial, "shell", f"cat {path}"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    m = re.search(r'<string name="pushDeviceToken">([^<]*)</string>', raw)
    return m.group(1) if m and m.group(1) else None


def new_device_token() -> str:
    """仅用于压测占位: 上游会拒绝 (Token Error), 但足以验证错误路径稳定性。"""
    return f"{uuidlib.uuid4().hex[:22]}:APA91b{uuidlib.uuid4().hex}"


if __name__ == "__main__":
    c = WaveSome()
    for name, fn in [("config", c.system_config), ("styles", c.styles), ("blocks", lambda: c.blocks(3)),
                     ("sketches", c.sketches)]:
        r = fn()
        print(f"{name:9s} ok={r.ok} status={r.status} {r.elapsed*1000:6.0f}ms bytes={len(r.body)}")
