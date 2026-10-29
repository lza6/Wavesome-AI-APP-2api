# 交接书：Wavesome.AI → new-api-Max 渠道接入

> 目标仓库：`new-api-Max`（本机 `C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\公益服务网关\new-api`）
> 本文自包含，执行者不需要读其它会话上下文。协议细节见 [`PROTOCOL.md`](PROTOCOL.md)。

---

## 0. ⚠️ 先看这个：上游当前不可用

`POST service/generate` 对**所有** device-token 返回 `500 {"message":"Token Error. Please contact support!"}`，
包括真机 / 模拟器上**真实 App 自己**点 Create（同一台 AVD 实测同样弹窗）。`service/sketch`、`service/upscale`
是服务端开关关闭（`... is disabled`）。**唯一活着的是公开只读端点。**

所以本交接分两阶段：

| 阶段 | 做什么 | 现在能做吗 |
|---|---|---|
| **P1 旁挂验证**（推荐先做） | 把本仓库 `demo_server.py` 当 OpenAI 兼容渠道接进去，跑通计费/日志/错误映射 | ✅ 现在就能做，出图会返回结构化 502 |
| **P2 原生渠道** | Go 渠道 `type=81` | 代码可以写完，**但不要上线**：出图 100% 失败，只会烧配额 |
| **P3 恢复后** | `health_probe.py` 报 200 后再放开 | 等 |

如果只想接"能用的东西"：**这一单现在没有能用的出图能力**，建议 P2 代码合进分支但渠道禁用（`status=0`）。

---

## 1. 协议速查（5 条）

```
BASE            https://ailwapi360.waveabc.xyz/api/
必需头           api-version: 31      (服务端接受 >=30)
必需头           User-Agent: 任意非空 (空 UA 被 Cloudflare 1010 拦)
身份头           device-token: <FCM registration token>   ← 唯一身份，无 Authorization/无签名
出图            POST service/generate  → 200 时 body 直接是图片字节，响应头 sample-uuid = 图片 ID
```

请求体：

```json
{"prompt":"…","uuid":"<风格UUID>","width":512,"height":512,"aspect_ratio":"1:1","restore_faces":false}
```

* `uuid` 必填，取自 `GET public/ai-samples/styles`（71 个，全免费，全 1:1）。
* `width/height` 取自 `GET configs/public/system` 的 `ai.aspect_ratios[*].scales[1x|2x|4x]`：
  1:1→512/1024/2048，9:16→512×896 / 1024×1792 / 2048×3548，16:9→896×512 …（7 种比例）。
* `aspect_ratio` 必传非空，Kotlin 侧有 `g.f()` 断言。

错误码（实测）：

| 条件 | HTTP | body |
|---|---|---|
| 缺/低 `api-version` | 500 | `{"message":"Version Error. Please contact support!"}` |
| `uuid` 空/非法 | 500 | `{"message":"UUID Error"}` |
| token 校验失败 | 500 | `{"message":"Token Error. Please contact support!"}` |
| sketch / upscale 关闭 | **200** | 裸文本 `Sketch generation is disabled` / `Upscale is disabled` |

> 注意第 4 行：**上游会用 HTTP 200 表达失败**。渠道里必须按 body 文本二次判定，不能只看状态码。

---

## 2. 路线 A：零 Go 代码旁挂（30 分钟，先跑通）

本仓库的 `demo_server.py` 本身就是 OpenAI 兼容的 `/v1/images/generations`。

```powershell
cd D:\apk-analysis\wavesome
$env:PORT="8935"
$env:WAVESOME_DEVICE_TOKEN=(Get-Content .\probe\token2.txt -Raw).Trim()   # 没有就留空 -> 出图返回 503
python demo_server.py
# 自检
curl -X POST http://127.0.0.1:8935/v1/images/generations -H "Content-Type: application/json" `
     -d '{"prompt":"a red fox in snow","size":"512x512"}'
```

new-api 侧（管理面板）：

| 字段 | 值 |
|---|---|
| 类型 | `OpenAI`(1) |
| 代理/Base URL | `http://127.0.0.1:8935` |
| 密钥 | 随便填（网关不校验） |
| 模型 | `wavesome-t2i`（`/v1/models` 会返回） |

这样就能立刻验证：计费扣费、日志记录、错误透传、前端图片渲染。
**出图会成功**（因为 `/v1/images/generations` 在 `MOCK=0` 时返回的是结构化 502；`MOCK=1` 才出图）。
所以：**旁挂接进去只用于验证管线，不要按出图计费**。

---

## 3. 路线 B：原生渠道 `type = 81`

### 3.1 五个注册点（照 `aivg` 抄，一处都别漏）

| 文件 | 改动 |
|---|---|
| `constant/channel.go` | `ChannelTypeWavesome = 81`（当前最大是 80 SnapClip）；名称映射表加 `ChannelTypeWavesome: "Wavesome"` |
| `constant/api_type.go` | iota 块末尾加 `APITypeWavesome` |
| `common/api_type.go` | `case constant.ChannelTypeWavesome: apiType = constant.APITypeWavesome` |
| `relay/relay_adaptor.go` | `import ".../relay/channel/wavesome"`；`case constant.APITypeWavesome: return &wavesome.Adaptor{}` |
| `constant/twoapi_channel.go` | `TwoAPIChannelTypes` 追加 `ChannelTypeWavesome, // 81` |

> `TwoAPIChannelTypes` 是单一事实来源（计费判定 / 出站压缩豁免 / 管理面板都引用它），漏了会出现"Duck/AIVM 漏计费"同类问题。

### 3.2 新包 `relay/channel/wavesome/`

`constants.go`：

```go
package wavesome

const (
    ChannelName   = "Wavesome"
    BaseURL       = "https://ailwapi360.waveabc.xyz/api/"
    APIVersion    = "31"
    DefaultUA     = "okhttp/4.9.3"
    DefaultStyle  = "89d874da-2dd4-4488-aad6-a1eed5b1c3b3" // "Modern 3D"
)

var ModelList = []string{"wavesome-t2i"}
```

`dto.go`：

```go
type generateRequest struct {
    Prompt       string `json:"prompt"`
    StyleUUID    string `json:"uuid"`
    Width        int    `json:"width"`
    Height       int    `json:"height"`
    AspectRatio  string `json:"aspect_ratio"`
    RestoreFaces bool   `json:"restore_faces"`
}
```

`adaptor.go` 骨架（Adaptor 接口见 `relay/channel/adapter.go`）：

```go
func (a *Adaptor) Init(info *relaycommon.RelayInfo) {}

func (a *Adaptor) GetRequestURL(info *relaycommon.RelayInfo) (string, error) {
    return BaseURL + "service/generate", nil
}

func (a *Adaptor) SetupRequestHeader(c *gin.Context, req *http.Header, info *relaycommon.RelayInfo) error {
    req.Set("Content-Type", "application/json")
    req.Set("api-version", APIVersion)
    req.Set("User-Agent", DefaultUA)     // 必须：空 UA 会被 Cloudflare 1010 拦
    // 身份：从渠道 Key 里取 device-token；号池轮换见 §4
    if info.ChannelSetting != nil && info.ChannelSetting.Key != "" {
        req.Set("device-token", info.ChannelSetting.Key)
    }
    return nil
}

func (a *Adaptor) ConvertImageRequest(c *gin.Context, info *relaycommon.RelayInfo, r dto.ImageRequest) (any, error) {
    w, h, ar := resolveSize(r.Size)      // 用 configs/public/system 的比例表，缺省 512x512/1:1
    style := DefaultStyle
    if s, ok := info.ChannelSetting.OtherInfo["style_uuid"]; ok && s != "" { style = s }
    return &generateRequest{Prompt: r.Prompt, StyleUUID: style,
        Width: w, Height: h, AspectRatio: ar, RestoreFaces: false}, nil
}

func (a *Adaptor) DoRequest(c *gin.Context, info *relaycommon.RelayInfo, body io.Reader) (any, error) {
    return channel.DoApiRequest(a, c, body, info)   // 与其它渠道同构
}

// DoResponse：上游成功时是二进制图片，不是 JSON，必须绕过通用 JSON 解析
func (a *Adaptor) DoResponse(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo) (any, *types.NewAPIError) {
    ct := resp.Header.Get("Content-Type")
    if resp.StatusCode == http.StatusOK && strings.HasPrefix(ct, "image/") {
        raw, _ := io.ReadAll(resp.Body)                      // 就是图片字节
        sampleUUID := resp.Header.Get("sample-uuid")
        b64 := base64.StdEncoding.EncodeToString(raw)
        c.JSON(http.StatusOK, gin.H{"created": time.Now().Unix(),
            "data": []gin.H{{"b64_json": b64}},
            "z_upstream": gin.H{"sample_uuid": sampleUUID}})
        return &dto.Usage{PromptTokens: 0, CompletionTokens: 0, TotalTokens: 1}, nil  // 按张计费
    }
    // 上游用 200 表达"功能关闭"
    raw, _ := io.ReadAll(resp.Body)
    msg := strings.TrimSpace(string(raw))
    switch {
    case strings.Contains(msg, "Token Error"):
        return nil, types.NewErrorWithStatusCode(errors.New(msg),
            types.ErrorCodeChannelInvalidKey, http.StatusBadGateway) // Token Error 属于渠道凭证失效
    case strings.Contains(msg, "UUID Error"):
        return nil, types.NewErrorWithStatusCode(errors.New(msg),
            types.ErrorCodeInvalidRequest, http.StatusBadRequest)
    case strings.Contains(msg, "disabled"):
        return nil, types.NewErrorWithStatusCode(errors.New(msg),
            types.ErrorCodeChannelNoAvailable, http.StatusServiceUnavailable)
    }
    return nil, types.NewErrorWithStatusCode(errors.New(msg), types.ErrorCodeBadResponse, http.StatusBadGateway)
}
```

`adaptor_test.go`：至少覆盖 4 个分支 —— 200+image/*、`Token Error`、`UUID Error`、`200+disabled`。
注意 `DoResponse` 必须处理"HTTP 200 + 文本"，否则会被通用 JSON 解析误判成功。

### 3.3 计费锚点

* 上游出图 = **HTTP 200 + 图片字节**，一张一图，无 token 计费 → `Usage.TotalTokens = 1`，按"次"计费。
* 现在上游 100% 失败，**必须**让失败不扣费：错误路径返回 `nil, NewAPIError`（上面已如此）。
* 若以后拿到真实额度数据（每日上限），在 `EstimateBilling` 里按张数前置扣费。

---

## 4. device-token 号池

* `device-token` 是 **FCM registration token**，会过期/轮换（`pm clear`、重装、Google 侧轮换都会变）。
* 造新 token 的唯一低成本方式：**同一个模拟器反复 `pm clear` + 重跑 App**（每次 = 新设备身份）：

```powershell
python tools/token_from_emulator.py --serial emulator-5556 --renew   # 打印新 token
# 循环 N 次 -> 写进 probe/tokens.json -> 渠道 Key 用第一个，OtherInfo 存池
```

* 渠道配置建议：`Key = <当前 token>`，`OtherInfo = {"style_uuid":"<默认风格>","tokens":["t1","t2",...]}`，
  遇到 `Token Error` 就 `Token Error → 换下一个 token 重试一次`（注意：**当前换成任何 token 都失败**，此逻辑是给恢复后准备的）。

---

## 5. 已知坑（都踩过）

| 现象 | 真实原因 | 修法 |
|---|---|---|
| 403 `error code: 1010` | 空/可疑 UA 被 Cloudflare 拦 | 显式 `User-Agent: okhttp/4.9.3` |
| `Version Error` | `api-version` 缺失或 <30 | 固定 `31` |
| `UUID Error` | `uuid` 为 null 或不是风格 UUID | 从 `/public/ai-samples/styles` 取 |
| `Token Error`（所有 token） | 上游设备校验整体失效（见 §0） | 无解，等恢复；不要以为是自己写错 |
| 上游 p50 ~450–520 ms，p99 1.2 s+ | Cloudflare + PHP 8.3 基线就这么慢 | 渠道超时 ≥60 s，客户端并发建议 ≤8 |
| 200 但没图 | 上游用 200 + 文本表达"功能关闭" | `DoResponse` 里二次文本判定 |

---

## 6. 验收清单（P2 代码合入前逐条过）

- [ ] `go build ./...` 通过；`go test ./relay/channel/wavesome/ -run Test -v` 4 个分支全绿
- [ ] `constant.TwoAPIChannelTypes` 含 81（计费/面板都读它）
- [ ] 管理面板能建 `type=81` 渠道，名称显示 `Wavesome`
- [ ] 用 `curl /v1/images/generations` 打本渠道：返回结构化 502 + `Token Error`，**且不扣费**
- [ ] 渠道 `status=0`（禁用）后再合入，避免有人误用
- [ ] 回滚方案：只删 `relay/channel/wavesome/` + 回退 5 个注册点，无 DB migration

## 7. 附录：一条命令复现"上游必失败"

```bash
TOK=$(cat probe/token2.txt)
curl -s -X POST https://ailwapi360.waveabc.xyz/api/service/generate \
  -H "api-version: 31" -H "device-token: $TOK" -H "User-Agent: okhttp/4.9.3" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a fox","uuid":"89d874da-2dd4-4488-aad6-a1eed5b1c3b3","width":512,"height":512,"aspect_ratio":"1:1","restore_faces":false}' \
  -w '\n[%{http_code} %{time_total}s]\n'
# 期望: {"message":"Token Error. Please contact support!"}  [500 ~0.6-1.8s]
```
