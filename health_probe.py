#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
health_probe.py — 上游 service/generate 恢复探测

背景: 2026-10-29/30 起, service/generate 对所有 device-token 返回
      500 {"message":"Token Error. Please contact support!"}(连真机 App 自己也失败)。
      本脚本用于长期探测: 一旦恢复 200 立刻落盘首个成功样本(图片 + 响应头 + 耗时),
      供 new-api 渠道上线前确认格式/水印/额度。

用法:
    python health_probe.py                        # 单次探测, 打印结果并写 history
    python health_probe.py --loop 600             # 每 600s 探一次, 状态变化时高亮
    python health_probe.py --watch                # loop 模式 + 恢复时自动存样本

输出:
    evidence/health_history.jsonl   每次探测一行
    evidence/recovered_<ts>.jpg|png 恢复后的首个成功样本
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from wavesome import WaveSome, read_emulator_token

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
os.makedirs(EV, exist_ok=True)
HIST = os.path.join(EV, "health_history.jsonl")

DEFAULT_STYLE = "89d874da-2dd4-4488-aad6-a1eed5b1c3b3"  # Modern 3D


def token() -> str:
    t = os.environ.get("WAVESOME_DEVICE_TOKEN") or ""
    if not t:
        path = os.path.join(HERE, "probe", "token2.txt")
        if os.path.exists(path):
            t = open(path, encoding="utf-8").read().strip()
    if not t:
        t = read_emulator_token() or ""
    return t


def probe(tok: str) -> dict:
    c = WaveSome(device_token=tok or None)
    r = c.generate("a red fox in snow, oil painting", DEFAULT_STYLE)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": r.ok,
        "status": r.status,
        "content_type": r.content_type,
        "bytes": len(r.body),
        "ms": round(r.elapsed * 1000, 1),
        "error": r.error,
        "sample_uuid": r.sample_uuid,
        "has_token": bool(tok),
    }
    if r.ok and r.content_type.startswith("image/"):
        ext = "png" if "png" in r.content_type else "jpg"
        name = f"recovered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        r.save(os.path.join(EV, name))
        rec["saved"] = name
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="探测间隔秒数 (0=单次)")
    ap.add_argument("--watch", action="store_true", help="循环模式, 恢复时高亮")
    ap.add_argument("--style", default=DEFAULT_STYLE)
    a = ap.parse_args()

    tok = token()
    print(f"# device-token: {'yes' if tok else 'NO (上游必然 Token Error，仍可探测版本/路由是否变化)'}")
    last_ok = None
    while True:
        rec = probe(tok)
        with open(HIST, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        flag = "OK  " if rec["ok"] else "FAIL"
        print(f"[{rec['ts']}] {flag} status={rec['status']} {rec['bytes']}B {rec['ms']}ms "
              f"{('sample=' + rec['sample_uuid']) if rec.get('sample_uuid') else ''} "
              f"{rec['error'] or ''}")
        if rec["ok"] and rec.get("saved"):
            print(f"  ★★ 上游恢复！样本已存 evidence/{rec['saved']}")
        if last_ok is not None and last_ok != rec["ok"]:
            print(f"  ** 状态翻转: {'失效' if not rec['ok'] else '恢复'} **")
        last_ok = rec["ok"]
        if a.loop <= 0:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
