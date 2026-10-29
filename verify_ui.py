#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_ui.py — 用真实浏览器(Playwright)走一遍 demo 页关键路径, 截图存 evidence/

路径覆盖:
  1. 首页加载 (mode / token 徽章 + 尺寸/风格下拉被真实上游 config/styles 填充)
  2. 上游鉴权矩阵诊断 (真实网络, 11 步)
  3. 公开端点面板 (config)
  4. 文生图请求 (真实上游 -> 预期 502 Token Error, 断言错误结构正确)
  5. 指标面板
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
os.makedirs(EV, exist_ok=True)
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8933"
errors: list[str] = []

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(2500)  # 等 config/styles 拉完
    pg.screenshot(path=os.path.join(EV, "ui_1_home.png"), full_page=True)

    sizes = pg.eval_on_selector_all("#size option", "els => els.map(e => e.textContent)")
    styles = pg.eval_on_selector_all("#style option", "els => els.map(e => e.textContent)")
    print("尺寸下拉:", sizes)
    print("风格下拉前3:", styles[:3], f"(共{len(styles)})")
    assert len(sizes) >= 5, "尺寸下拉未被上游 config 填充"
    assert len(styles) > 20, "风格下拉未被上游 styles 填充"

    # 诊断矩阵
    pg.click("#btnDiag")
    pg.wait_for_timeout(25000)
    rows = pg.eval_on_selector_all("#diagTable tbody tr", "els => els.map(e => e.innerText)")
    print("诊断行数:", len(rows))
    for r in rows:
        print("  ", r.replace("\t", " | ")[:130])
    pg.screenshot(path=os.path.join(EV, "ui_2_diagnose.png"), full_page=True)
    assert len(rows) >= 8, "诊断矩阵行数不足"

    # 公开端点
    pg.click('[data-ep="config"]')
    pg.wait_for_timeout(3000)
    cfg_out = pg.inner_text("#epOut")
    print("config 面板:", cfg_out[:120].replace("\n", " "))
    pg.screenshot(path=os.path.join(EV, "ui_3_endpoints.png"), full_page=True)

    # 文生图
    pg.click("#btnGen")
    pg.wait_for_timeout(6000)
    gen = pg.inner_text("#genOut")
    print("生成响应:", gen[:300].replace("\n", " "))
    pg.screenshot(path=os.path.join(EV, "ui_4_generate.png"), full_page=True)
    j = json.loads(gen)
    assert "error" in j, "生成响应缺少 error 结构"

    # 指标
    pg.click("#btnStats")
    pg.wait_for_timeout(1200)
    stat_rows = pg.eval_on_selector_all("#statTable tbody tr", "els => els.length")
    print("指标端点行数:", stat_rows)
    pg.screenshot(path=os.path.join(EV, "ui_5_stats.png"), full_page=True)

    b.close()

print("\nconsole/page errors:", len(errors))
for e in errors[:10]:
    print("  ", e)
print("OK: UI 路径全部通过")
