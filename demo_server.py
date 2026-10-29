#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_server.py — Wavesome.AI 2API 本地网关 + demo 页 (R1)

设计取舍:
  * 公开端点 (config/styles/blocks/gallery/sketches) 直连真实上游 —— 这部分是「已验证可用」的实链路。
  * /v1/images/generations 走真实上游 service/generate；上游当前返回 500 Token Error，
    网关按 OpenAI 错误格式透出，并把原始报文放进 detail.z_upstream。
  * MOCK=1 时返回真实 Wavesome CDN 样图（不伪造生成能力，仅在 UI/压测中替代不可用的上游出图）。

启动:
    python demo_server.py                # 默认 :8931
    MOCK=1 python demo_server.py         # 出图走 mock（用于 UI 演示 / 并发压测）
    WAVESOME_DEVICE_TOKEN=xxx:APA91... python demo_server.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import statistics
import threading
import time
import uuid
from collections import defaultdict, deque

import requests
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from wavesome import BASE_URL, WaveSome, aspect_ratio_table, new_device_token, read_emulator_token

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
EVID_DIR = os.path.join(HERE, "evidence")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(EVID_DIR, exist_ok=True)

PORT = int(os.environ.get("PORT", "8931"))
MOCK = os.environ.get("MOCK", "0") == "1"
DEVICE_TOKEN = os.environ.get("WAVESOME_DEVICE_TOKEN") or read_emulator_token() or ""
COUNTRY = os.environ.get("WAVESOME_COUNTRY", "")

app = Flask(__name__, static_folder=None)

# ---------------- 指标 ----------------
_lock = threading.Lock()
_metrics = {"count": defaultdict(int), "lat": defaultdict(lambda: deque(maxlen=4000)),
            "errors": defaultdict(int), "started": time.time()}


def record(name: str, elapsed: float, ok: bool):
    with _lock:
        _metrics["count"][name] += 1
        _metrics["lat"][name].append(elapsed * 1000.0)
        if not ok:
            _metrics["errors"][name] += 1


def _pct(values, q):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((len(s) - 1) * q))))
    return round(s[k], 2)


def metrics_snapshot():
    with _lock:
        out = {}
        for name, lat in _metrics["lat"].items():
            vals = list(lat)
            out[name] = {
                "count": _metrics["count"][name],
                "errors": _metrics["errors"][name],
                "p50_ms": _pct(vals, 0.50),
                "p90_ms": _pct(vals, 0.90),
                "p99_ms": _pct(vals, 0.99),
                "mean_ms": round(statistics.fmean(vals), 2) if vals else None,
            }
        return {"uptime_s": round(time.time() - _metrics["started"], 1), "endpoints": out}


client = WaveSome(device_token=DEVICE_TOKEN or None, country=COUNTRY or None)

# ---------------- 尺寸解析 ----------------
_CONFIG_CACHE = {"ts": 0.0, "data": None}


def config_data(force=False):
    if not force and _CONFIG_CACHE["data"] and time.time() - _CONFIG_CACHE["ts"] < 600:
        return _CONFIG_CACHE["data"]
    r = client.system_config()
    if r.ok:
        _CONFIG_CACHE["data"] = r.json()
        _CONFIG_CACHE["ts"] = time.time()
    return _CONFIG_CACHE["data"] or {}


def resolve_size(size: str) -> tuple[int, int, str]:
    """OpenAI 风格 size -> (w,h,aspect)。非法/缺失退化到该比例 1x。"""
    table = aspect_ratio_table(config_data())
    if not table:
        table = {"1:1": {"1x": {"width": 512, "height": 512}}}
    raw = (size or "512x512").lower().replace(" ", "")
    if "x" in raw:
        try:
            w, h = [int(x) for x in raw.split("x", 1)]
        except Exception:
            w = h = 512
    else:
        w = h = 512
    best = min(
        table.items(),
        key=lambda kv: abs((kv[1].get("1x", {}).get("width", 512) / max(1, kv[1].get("1x", {}).get("height", 512)))
                           - (w / max(1, h))),
    )
    ar, scales = best
    # 按请求面积挑选最接近的档位
    target = w * h
    pick = min(scales.items(),
               key=lambda kv: abs(kv[1]["width"] * kv[1]["height"] - target))[1]
    return int(pick["width"]), int(pick["height"]), ar


# ---------------- mock 图 (真实 CDN 样图, 不伪造生成) ----------------
_MOCK_CACHE = {"bytes": None, "ctype": "image/jpeg"}


def mock_image() -> tuple[bytes, str]:
    if _MOCK_CACHE["bytes"]:
        return _MOCK_CACHE["bytes"], _MOCK_CACHE["ctype"]
    urls = []
    r = client.styles()
    if r.ok:
        for s in (r.json() or [])[:5]:
            if s.get("preview"):
                urls.append(s["preview"])
    for u in urls:
        try:
            resp = requests.get(u, timeout=30, headers={"User-Agent": "okhttp/4.9.3"})
            ctype = resp.headers.get("Content-Type", "image/jpeg")
            if resp.ok and resp.content and ctype.startswith("image/"):
                _MOCK_CACHE["bytes"] = resp.content
                _MOCK_CACHE["ctype"] = ctype
                return _MOCK_CACHE["bytes"], _MOCK_CACHE["ctype"]
        except Exception:
            continue
    # 兜底: 1x1 PNG
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
    )
    _MOCK_CACHE["bytes"] = png
    _MOCK_CACHE["ctype"] = "image/png"
    return png, "image/png"


# ---------------- 路由 ----------------
@app.get("/")
def index():
    return send_file(os.path.join(HERE, "demo.html"))


@app.get("/files/<path:name>")
def files(name):
    return send_from_directory(OUT_DIR, name)


@app.get("/health")
def health():
    t0 = time.time()
    record("/health", time.time() - t0, True)
    return jsonify({"status": "ok", "mock": MOCK, "device_token": (DEVICE_TOKEN[:18] + "...") if DEVICE_TOKEN else "",
                    "upstream": BASE_URL})


@app.get("/stats")
def stats():
    return jsonify(metrics_snapshot())


@app.get("/v1/models")
def models():
    t0 = time.time()
    data = [{"id": "wavesome-t2i", "object": "model", "owned_by": "wavesome",
             "created": int(_metrics["started"])}]
    record("/v1/models", time.time() - t0, True)
    return jsonify({"object": "list", "data": data})


def _save_image(payload: bytes, ext: str) -> str:
    name = f"{uuid.uuid4().hex[:16]}.{ext}"
    with open(os.path.join(OUT_DIR, name), "wb") as f:
        f.write(payload)
    return name


def _openai_error(status: int, message: str, code: str, extra: dict | None = None):
    body = {"error": {"message": message, "type": "upstream_error", "code": code}}
    if extra:
        body["error"]["detail"] = extra
    return jsonify(body), status


@app.post("/v1/images/generations")
def generations():
    t0 = time.time()
    req = request.get_json(silent=True) or {}
    prompt = (req.get("prompt") or "").strip()
    if not prompt:
        record("/v1/images/generations", time.time() - t0, False)
        return _openai_error(400, "prompt is required", "invalid_request_error")
    n = max(1, min(int(req.get("n") or 1), 4))
    w, h, ar = resolve_size(req.get("size") or "512x512")
    style_uuid = req.get("style_uuid") or os.environ.get("WAVESOME_STYLE_UUID") or ""

    if MOCK:
        img, ctype = mock_image()
        ext = "png" if "png" in ctype else "jpg"
        items = []
        for _ in range(n):
            name = _save_image(img, ext)
            items.append({"url": f"http://127.0.0.1:{PORT}/files/{name}"})
        record("/v1/images/generations", time.time() - t0, True)
        return jsonify({"created": int(time.time()), "data": items,
                        "detail": {"mode": "mock", "note": "mock 使用真实 Wavesome CDN 样图, 非上游生成",
                                   "width": w, "height": h, "aspect_ratio": ar}})

    if not DEVICE_TOKEN:
        record("/v1/images/generations", time.time() - t0, False)
        return _openai_error(503, "未配置 device-token（FCM token）。上游 service/generate 必须携带。",
                             "device_token_missing", {"hint": "见 docs/PROTOCOL.md「身份模型」一节"})

    if not style_uuid:
        r = client.styles()
        if r.ok and r.json():
            style_uuid = r.json()[0]["uuid"]
    r = client.generate(prompt, style_uuid, width=w, height=h, aspect_ratio=ar)
    elapsed = time.time() - t0
    if not r.ok:
        record("/v1/images/generations", elapsed, False)
        return _openai_error(502, r.error or "upstream error", "upstream_token_error" if "Token" in (r.error or "") else "upstream_error",
                             {"status": r.status, "z_upstream": r.error,
                              "device_token_tail": DEVICE_TOKEN[-10:] if DEVICE_TOKEN else ""})
    ext = "png" if "png" in r.content_type else "jpg"
    name = _save_image(r.body, ext)
    record("/v1/images/generations", elapsed, True)
    d = {"mode": "live", "sample_uuid": r.sample_uuid, "width": w, "height": h,
         "aspect_ratio": ar, "style_uuid": style_uuid}
    if req.get("response_format") == "b64_json":
        return jsonify({"created": int(time.time()),
                        "data": [{"b64_json": base64.b64encode(r.body).decode()}], "detail": d})
    return jsonify({"created": int(time.time()),
                    "data": [{"url": f"http://127.0.0.1:{PORT}/files/{name}"}], "detail": d})


# ---------------- 公开端点透传 (真实上游) ----------------
@app.get("/api/ws/config")
def ws_config():
    t0 = time.time()
    r = client.system_config()
    record("/api/ws/config", time.time() - t0, r.ok)
    return Response(r.body, status=r.status, content_type="application/json")


@app.get("/api/ws/styles")
def ws_styles():
    t0 = time.time()
    r = client.styles()
    record("/api/ws/styles", time.time() - t0, r.ok)
    return Response(r.body, status=r.status, content_type="application/json")


@app.get("/api/ws/blocks")
def ws_blocks():
    t0 = time.time()
    r = client.blocks(int(request.args.get("quantity", 6)))
    record("/api/ws/blocks", time.time() - t0, r.ok)
    return Response(r.body, status=r.status, content_type="application/json")


@app.get("/api/ws/gallery")
def ws_gallery():
    t0 = time.time()
    r = client.gallery(request.args.get("code", "daily"), int(request.args.get("page", 0)))
    record("/api/ws/gallery", time.time() - t0, r.ok)
    return Response(r.body, status=r.status, content_type="application/json")


@app.get("/api/ws/sketches")
def ws_sketches():
    t0 = time.time()
    r = client.sketches()
    record("/api/ws/sketches", time.time() - t0, r.ok)
    return Response(r.body, status=r.status, content_type="application/json")


@app.get("/api/ws/device")
def ws_device():
    t0 = time.time()
    r = client.device_get() if DEVICE_TOKEN else None
    if r is None:
        r = WaveSome(device_token=new_device_token()).device_get()
    record("/api/ws/device", time.time() - t0, r.ok)
    return jsonify({"status": r.status, "body": r.json(), "elapsed_ms": round(r.elapsed * 1000, 1)})


@app.get("/api/ws/diagnose")
def ws_diagnose():
    """跑一遍真实上游的鉴权矩阵, 结果直接渲染到 demo 页。"""
    out = []

    def step(name, fn):
        t0 = time.time()
        try:
            r = fn()
            ok, status, msg = r.ok, r.status, (r.error or ("%d bytes" % len(r.body)))
        except Exception as exc:
            ok, status, msg = False, 0, str(exc)
        out.append({"step": name, "ok": ok, "status": status, "message": msg,
                    "ms": round((time.time() - t0) * 1000, 1)})

    step("GET configs/public/system（无鉴权）", lambda: client.system_config())
    step("GET public/ai-samples/styles", lambda: client.styles())
    step("GET public/ai-samples/blocks?quantity=3", lambda: client.blocks(3))
    step("GET public/ai-samples/gallery/daily", lambda: client.gallery("daily"))
    step("GET device/（无校验，任意 token 均 200）", lambda: WaveSome(device_token=new_device_token()).device_get())
    step("PUT device/ premium=sub（无校验）", lambda: client.device_set_premium("sub"))
    step("POST service/generate（无 token）", lambda: WaveSome().generate("a fox", "89d874da-2dd4-4488-aad6-a1eed5b1c3b3"))
    step("POST service/generate（假 token）",
         lambda: WaveSome(device_token=new_device_token()).generate("a fox", "89d874da-2dd4-4488-aad6-a1eed5b1c3b3"))
    if DEVICE_TOKEN:
        step("POST service/generate（真实 FCM token）",
             lambda: client.generate("a fox", "89d874da-2dd4-4488-aad6-a1eed5b1c3b3"))
    step("POST service/sketch", lambda: client.sketch("a fox", "89d874da-2dd4-4488-aad6-a1eed5b1c3b3", "iVBORw0KGgo="))
    step("POST service/upscale", lambda: client.upscale("89d874da-2dd4-4488-aad6-a1eed5b1c3b3", 2))
    return jsonify({"device_token_configured": bool(DEVICE_TOKEN), "mock": MOCK, "steps": out})


if __name__ == "__main__":
    print(f"[demo] http://127.0.0.1:{PORT}  mock={MOCK} token={'yes' if DEVICE_TOKEN else 'no'}")
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False)
