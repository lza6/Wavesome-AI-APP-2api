#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stress_test.py — Wavesome 2API 本地网关 R1 压测

覆盖:
  A. 网关自身开销        /health、/v1/models
  B. 真实上游公共端点    /api/ws/{config,styles,blocks,gallery}   (实链路, 有真实上游 RTT)
  C. 真实上游生成错误路径 /v1/images/generations                  (上游 500 Token Error 的稳定性)
  D. mock 出图并发        /v1/images/generations                  (仅 MOCK=1 时)
  E. 错误路径           空 prompt / 未配置 token

用法: python stress_test.py [--port 8931] [--out evidence/stress_r1.json]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def one(url, method="GET", payload=None, timeout=180):
    t0 = time.time()
    try:
        r = requests.request(method, url, json=payload, timeout=timeout)
        return {"ms": (time.time() - t0) * 1000, "status": r.status_code,
                "len": len(r.content or b""), "err": None,
                "body": r.text[:400]}
    except Exception as exc:
        return {"ms": (time.time() - t0) * 1000, "status": 0, "len": 0, "err": str(exc), "body": ""}


def scenario(name, base, path, method="GET", payload=None, concurrency=1, total=20,
             expect_ok=(200,), timeout=180):
    url = base + path
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(one, url, method, payload, timeout) for _ in range(total)]
        results = [f.result() for f in futs]
    lat = [r["ms"] for r in results]
    wall = max(lat) / 1000 if lat else 0
    ok = sum(1 for r in results if r["status"] in expect_ok)
    codes = Counter(r["status"] for r in results)
    errs = Counter((r["err"] or r["body"][:80]) for r in results if r["status"] not in expect_ok)
    out = {
        "scenario": name, "path": path, "method": method,
        "concurrency": concurrency, "n": total,
        "ok": ok, "fail": total - ok,
        "rps_serial_sum": round(total / wall, 2) if wall else None,
        "p50_ms": round(statistics.median(lat), 1),
        "p90_ms": round(sorted(lat)[max(0, int(0.9 * len(lat)) - 1)], 1),
        "p99_ms": round(sorted(lat)[max(0, int(0.99 * len(lat)) - 1)], 1),
        "max_ms": round(max(lat), 1),
        "mean_ms": round(statistics.fmean(lat), 1),
        "status_codes": dict(codes),
        "sample_errors": dict(list(errs.items())[:3]),
    }
    print(f"[{name:34s}] c={concurrency:<2d} n={total:<3d} ok={ok:<3d} "
          f"p50={out['p50_ms']:>8.1f}ms p99={out['p99_ms']:>8.1f}ms codes={dict(codes)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8931")))
    ap.add_argument("--out", default=os.path.join(HERE, "evidence", "stress_r1.json"))
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    h = requests.get(base + "/health", timeout=10).json()
    mock = bool(h.get("mock"))
    has_token = bool(h.get("device_token"))
    print(f"# target={base} mock={mock} device_token={'yes' if has_token else 'no'}\n")

    res = {"meta": {"base": base, "mock": mock, "device_token": has_token,
                    "started": time.strftime("%Y-%m-%d %H:%M:%S")}, "scenarios": []}
    S = res["scenarios"]

    # A. 网关自身
    S.append(scenario("A1 网关 /health", base, "/health", total=30))
    S.append(scenario("A2 网关 /v1/models", base, "/v1/models", total=30))

    # B. 真实上游公共端点
    S.append(scenario("B1 上游 config", base, "/api/ws/config", total=8))
    S.append(scenario("B2 上游 styles", base, "/api/ws/styles", concurrency=4, total=12))
    S.append(scenario("B3 上游 blocks", base, "/api/ws/blocks", concurrency=4, total=12))
    S.append(scenario("B4 上游 gallery", base, "/api/ws/gallery", concurrency=4, total=12))

    # C. 真实上游生成（当前预期失败）
    gen = {"prompt": "a red fox in snow, oil painting", "size": "512x512", "n": 1,
           "style_uuid": "89d874da-2dd4-4488-aad6-a1eed5b1c3b3"}
    S.append(scenario("C1 上游生成(串行,真实)", base, "/v1/images/generations", "POST", gen,
                      concurrency=1, total=3, expect_ok=(200,)))
    S.append(scenario("C2 上游生成(并发4,真实)", base, "/v1/images/generations", "POST", gen,
                      concurrency=4, total=8, expect_ok=(200,)))

    # D. mock 出图并发
    if mock:
        S.append(scenario("D1 出图 mock c=8", base, "/v1/images/generations", "POST", gen,
                          concurrency=8, total=32, expect_ok=(200,)))
        S.append(scenario("D2 出图 mock c=16", base, "/v1/images/generations", "POST", gen,
                          concurrency=16, total=64, expect_ok=(200,)))

    # E. 错误路径
    S.append(scenario("E1 空 prompt -> 400", base, "/v1/images/generations", "POST",
                      {"prompt": ""}, total=6, expect_ok=(400,)))
    if not has_token:
        S.append(scenario("E2 无 token -> 503", base, "/v1/images/generations", "POST", gen,
                          total=4, expect_ok=(503,)))
    S.append(scenario("E3 未知路径实例(404 由 Flask 抛)", base, "/nope", total=4, expect_ok=(404,)))

    st = requests.get(base + "/stats", timeout=10).json()
    res["gateway_stats"] = st
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"\n# saved -> {args.out}")
    tot = sum(s["n"] for s in S)
    bad = sum(s["fail"] for s in S if s["scenario"].startswith(("A", "B", "D", "E")))
    print(f"# 总请求 {tot}，A/B/D/E 类非预期失败 {bad}")


if __name__ == "__main__":
    main()
