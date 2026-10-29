# Wavesome.AI v1.0.31 → 2API（R1）

> 逆向 + 本地网关 + 压测 + demo 页。协议全文见 [`docs/PROTOCOL.md`](docs/PROTOCOL.md)，对接见 [`docs/NEW-API-HANDOFF.md`](docs/NEW-API-HANDOFF.md)。
> 仓库：<https://github.com/lza6/Wavesome-AI-APP-2api>

**一句话结论**：协议已 100% 还原（身份 = FCM token，无签名无校验），但**上游出图端点对所有设备失效**
（连真机 App 自己点生成也报 `Token Error`，截图 `probe/screen5.png`），当前只能交付「公开端点 + 恢复探测 + 随时可上线的渠道代码」。

## 30 秒跑起来

```powershell
cd D:\apk-analysis\wavesome
python demo_server.py                       # LIVE：真实上游（需 device-token）
$env:MOCK=1; python demo_server.py          # MOCK：出图用真实 CDN 样图（演示/压测用）
# 浏览器打开 http://127.0.0.1:8931
```

带真实设备身份（模拟器里跑过 App 才有）：

```powershell
python tools/token_from_emulator.py --serial emulator-5556   # 打印 FCM token
$env:WAVESOME_DEVICE_TOKEN="…:APA91b…"; python demo_server.py
```

一键脚本：`run.ps1 -Mode live|mock -Port 8931`

> 仓库里**不含任何真实 FCM token**（token 等价于账号）。`probe/token2.txt` 需要你自己用
> `tools/token_from_emulator.py` 生成，参考 `probe/token2.txt.example`。

恢复探测（上游一旦活过来立刻抓首个成功样本）：

```powershell
python health_probe.py            # 单次
python health_probe.py --loop 600 # 每 10 分钟一次，状态翻转会高亮
```

## 对接 new-api

见 [`docs/NEW-API-HANDOFF.md`](docs/NEW-API-HANDOFF.md)（自包含交接书：旁挂路线 / 原生 `type=81` 五处注册点 + Go 骨架 + 计费锚点 + 验收清单 + 回滚）。

---

## 能力实测表（2026-10-29/30，真实网络）

| 能力 | 状态 | 实测 |
|---|---|---|
| `GET /api/ws/config` → 上游 `configs/public/system` | ✅ | 200 / 13 877 B / p50 **480 ms** |
| `GET /api/ws/styles` | ✅ | 200 / 63 410 B / p50 **466 ms**（71 个风格，全免费） |
| `GET /api/ws/blocks` | ✅ | 200 / 92 407 B / p50 **525 ms** |
| `GET /api/ws/gallery` | ✅ | 200 / 30 784 B / p50 **453 ms** |
| `GET /api/ws/sketches` | ✅ | 200 |
| `GET /api/ws/device` | ✅（服务端不校验） | 任意 token 均 200 |
| `PUT /api/ws/device`（premium 自报） | ✅（服务端不校验） | `{"premium":"sub"}` → `"ok"` |
| `POST /v1/images/generations`（LIVE） | ❌ | 上游 `500 Token Error. Please contact support!` → 网关映射 502，带 `detail.z_upstream` |
| `POST /v1/images/generations`（MOCK） | ✅ | 返回真实 Wavesome CDN 样图，c=8 p50 **36.9 ms** |
| `service/sketch` | 🚫 | 上游开关关闭：`Sketch generation is disabled` |
| `service/upscale` | 🚫 | 上游开关关闭：`Upscale is disabled` |

**R1 硬结论：文生图端点对"所有设备"都拒绝**，包括真机/模拟器上**真实 App 自己**（同一台 AVD 里点 Create 也是同样弹窗）。这不是协议还原的问题，是上游侧的设备校验整体失效（推证见 `docs/PROTOCOL.md` §6.3）。

---

## 压测数据（本机，Flask 单进程，真实上游）

`python stress_test.py --port 8935` → `evidence/stress_r1_live.json`

| 场景 | 并发 | n | 成功 | p50 | p99 |
|---|---|---|---|---|---|
| A1 网关 `/health` | 1 | 30 | 30/30 | 5.3 ms | 10.8 ms |
| A2 网关 `/v1/models` | 1 | 30 | 30/30 | 6.7 ms | 29.9 ms |
| B1 上游 config | 1 | 8 | 8/8 | 480.1 ms | 526.3 ms |
| B2 上游 styles | 4 | 12 | 12/12 | 466.2 ms | 1 283.6 ms |
| B3 上游 blocks | 4 | 12 | 12/12 | 524.6 ms | 835.5 ms |
| B4 上游 gallery | 4 | 12 | 12/12 | 452.9 ms | 470.6 ms |
| C1 生图（真实，预期失败） | 1 | 3 | 0/3（502） | 650.3 ms | 650.3 ms |
| C2 生图（真实，预期失败） | 4 | 8 | 0/8（502） | 711.0 ms | 758.0 ms |
| E1 空 prompt → 400 | 1 | 6 | 6/6 | 7.1 ms | 9.9 ms |
| E3 未知路径 → 404 | 1 | 4 | 4/4 | 4.5 ms | 4.8 ms |

**125 个请求，A/B/E 类非预期失败 0**。上游失败路径在并发下稳定给出结构化 502，不泄漏 5xx、不拖垮网关。

`python stress_test.py --port 8934`（MOCK）→ `evidence/stress_r1_mock.json`

| 场景 | 并发 | n | 成功 | p50 | p99 |
|---|---|---|---|---|---|
| D1 出图（mock） | 8 | 32 | 32/32 | 36.9 ms | 54.7 ms |
| D2 出图（mock） | 16 | 64 | 64/64 | 83.9 ms | 125.7 ms |

**221 个请求，A/B/D/E 类非预期失败 0**。

---

## 浏览器真实路径验证

`python verify_ui.py http://127.0.0.1:8935`（Playwright + Chromium，截图在 `evidence/ui_*.png`）

1. 首页：尺寸下拉被上游 config 填成 7 档（512x512 / 512x768 / 512x704 / 512x896 / 768x512 / 704x512 / 896x512），风格下拉被上游 styles 填出 40 项 —— **证明 config/styles 走的是真链路**
2. 鉴权矩阵诊断：11 行，其中 6 OK / 5 FAIL（正是本报告结论）
3. 公开端点面板：config 11 个键
4. 文生图：返回 OpenAI 结构错误，`code=upstream_token_error`、`z_upstream=Token Error. Please contact support!`
5. 指标面板正常

> 唯一 console error 是浏览器记录那条预期的 502（BAD GATEWAY），非页面缺陷。

---

## 文件清单

```
wavesome.py                   协议客户端库（9 端点全覆盖 + 错误分类 + 尺寸表）
demo_server.py                本地网关：OpenAI /v1/images/generations + 上游透传 + 诊断 + 指标
demo.html                     demo 页（诊断矩阵 / 端点面板 / 指标）
stress_test.py                R1 压测（网关 / 真上游 / 错误路径 / mock 并发）
verify_ui.py                  Playwright 真实浏览器路径验证 + 截图
health_probe.py               上游恢复探测（恢复即抓首个成功样本）
run.ps1                       一键启动
tools/fis_mint.py             Firebase Installation 发号（实测可用，但换不到 FCM token）
tools/token_from_emulator.py  从 AVD 提取真实 FCM device-token
docs/PROTOCOL.md              协议还原全文
docs/NEW-API-HANDOFF.md       new-api 对接交接书（自包含）
evidence/upstream_transcript.txt  原始 curl 探测记录（token 已脱敏）
evidence/stress_r1_live.json  / stress_r1_mock.json   压测原始数据
evidence/ui_1..5_*.png        浏览器截图
probe/                        过程物（config.json / styles.json / 截图 / fcm 探测脚本）
```

## 风险与限制

* **上游生图当前不可用**（见上）。网关的 LIVE 出图路径是"真实但必失败"，MOCK 路径用的是上游 CDN 上的真实样图，不代表生成能力。**不要**把 MOCK 数据当上游性能。
* 上游单请求基线就在 450~520 ms（Cloudflare+PHP），并发下 p99 会到 1.2 s，客户端超时建议 ≥60 s。
* `device-token` 是 FCM token，**会过期/换号**（`pm clear`、重装、Google 侧轮换都会变）；池化需要真机/模拟器，成本高。
* 空 UA 会被 Cloudflare 1010 拦，必须带 `User-Agent`。
* Play 商店仍在维护（2026-10-05 更新）但版本停在 1.0.31，后续若恢复可用，本仓库的客户端层可直接复用（只需 `service/generate` 恢复 200）。
