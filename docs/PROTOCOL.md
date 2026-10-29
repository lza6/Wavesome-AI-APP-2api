# Wavesome.AI v1.0.31 协议还原报告（R1）

| 项 | 值 |
|---|---|
| 目标 APK | `Wavesome.AI v1.0.31 [Premium].apk`（35.0 MB，改装包 LiteApks） |
| 包名 | `com.wave.wavesome.ai.image.generator` |
| versionName / versionCode | `1.0.31` / `31` |
| API 版本头 | `api-version: 31`（服务端接受 ≥30） |
| 上游 | `https://ailwapi360.waveabc.xyz/api/` |
| 上游指纹 | Cloudflare + `x-powered-by: PHP/8.3.36`，错误体为 Symfony problem+json（405 时） |
| 图片 CDN | `https://1399418105.rsc.cdn77.org/api/resources/...` |
| Firebase | project `wavesome-ai` / app `1:676955275610:android:11f8fd986389a3dff07363` / apiKey `AIzaSyDTH4p7K3SmKiH-gVvzsN7YHoP1I9k7kfA` |
| 分析时间 | 2026-10-29 / 30 |
| 分析环境 | jadx 1.5.1 + apktool 2.9.3 + Android 30 google_apis x86_64 AVD + frida 16.5.9 |

---

## 0. 结论速览

| 能力 | 结论 | 证据等级 |
|---|---|---|
| 公开端点 `configs/public/system`、`public/ai-samples/{styles,blocks,gallery}`、`public/ai-sketches/list` | **可用，无鉴权**，实测 200 且返回完整数据 | 已验证 |
| 身份机制 = 仅 FCM registration token（header `device-token`），无 Authorization / 无签名 / 无 Cookie | 静态还原 + 黑盒确认 | 已验证 |
| `device/` 的 GET / PUT / DELETE | **服务端不做任何校验**，任意字符串均 200 | 已验证 |
| `service/generate`（文生图） | **不可用**：所有 device-token（含真机 App 自己的合法 FCM token）均返回 `500 Token Error. Please contact support!` | 已验证 |
| `service/sketch`（草图生图） | **服务端开关关闭**：`Sketch generation is disabled` | 已验证 |
| `service/upscale`（放大） | **服务端开关关闭**：`Upscale is disabled` | 已验证 |
| 客户端免费额度限制 | **不存在**（无本地计数门槛；`generatedImagesCounter` 只用于广告频次） | 静态确认 |
| premium 状态 | 客户端自报：`PUT device/ {"premium":"sub"}` 或 `""`；服务端不校验。**自报 premium 不能解锁 generate** | 已验证 |

> 一句话：**这个 App 的抓取面很干净（身份只有 FCM token、公开端点全裸），但唯一的生图端点目前对所有设备都拒绝。** 见第 7 节排查矩阵。

---

## 1. 客户端结构（jadx 还原）

```
ic/b.java          = WaveApi.kt            Retrofit 接口（9 个方法，全部端点）
jc/a.java          = HeaderInterceptor.kt  唯一的鉴权拦截器
gc/g.java          = Hilt 网络模块          baseUrl / 超时 / 拦截器装配
lc/a.java, lc/b.java = AiRepository / UserRepository（空壳，实际调用在 ViewModel 里）
ud/a.java          = SharedPreferences 封装（ACCOUNT_PREFERENCES）
com/wave/wavesomeai/ui/screens/**  = 各页面 ViewModel（直接调 WaveApi）
```

关键证据（`gc/g.java` 内 Hilt 单例）：

```java
x.b bVar = new x.b();                 // Retrofit.Builder
bVar.a("https://ailwapi360.waveabc.xyz/api/");
bVar.f20770d.add(gsonConverterFactory);
bVar.f20771e.add(rxCallAdapterFactory);
// OkHttpClient: connectTimeout=10s, readTimeout=45s, writeTimeout=25s
```

`jc/a.java`（**全部鉴权逻辑只有这三行**）：

```java
aVar.b("api-version", "31");                       // 固定 31
if (countryPref.length() != 0)    aVar.f13890c.a("api-country", countryPref);
if (pushDeviceToken.length() != 0) aVar.f13890c.a("device-token", pushDeviceToken);
```

`pushDeviceToken` 的写入位置 = `push/WaveMessagingService.java#e(String token)`（FCM `onNewToken` 回调）：
**即 `device-token` 头就是 FCM registration token**，App 侧也把它当作"用户 ID"（关于页可复制到剪贴板，剪贴板 label 为 `wavesome_user_id`）。

---

## 2. 端点矩阵（全部 9 个）

| # | 方法 | 路径 | 请求体 | 成功响应 | 实网结果 |
|---|---|---|---|---|---|
| 1 | GET | `configs/public/system` | – | 13.9 KB JSON（11 个键） | **200 可用** |
| 2 | GET | `public/ai-samples/styles` | – | 71 条风格（63.4 KB） | **200 可用** |
| 3 | GET | `public/ai-samples/blocks?quantity=N` | – | 精选区块（92 KB/3 块） | **200 可用** |
| 4 | GET | `public/ai-samples/gallery/{code}?page=N` | – | 样例列表 | **200 可用** |
| 5 | GET | `public/ai-sketches/list` | – | 草图模板列表 | **200 可用** |
| 6 | GET | `device/` | – | 回显头部里的 token（字符串） | **200，不校验** |
| 7 | PUT | `device/` | `{"premium":"sub"｜""}` | `"ok"` | **200，不校验** |
| 8 | DELETE | `device/` | – | `"ok"` | **200，不校验** |
| 9 | POST | `service/generate` | 见 2.1 | 原始图片字节 + 响应头 `sample-uuid` | **500 Token Error** |
| 10 | POST | `service/sketch` | 见 2.2 | 原始图片字节 | **200 但 `Sketch generation is disabled`** |
| 11 | POST | `service/upscale` | `{"uuid":"<图片uuid>","scale":2}` | 原始图片字节 | **200 但 `Upscale is disabled`** |

`OPTIONS` 探测结果：`device/` → `allow: GET, PUT, DELETE`；`service/*` → `allow: POST`；`configs/public/system` → `allow: GET`。

### 2.1 `POST service/generate` 请求体（`GenerateImageBody`）

```json
{
  "prompt":        "string",     // 必填，自由文本；服务端有 profanity 过滤（error_type=prompt）
  "uuid":          "string",     // 必填，风格 UUID（来自 /public/ai-samples/styles 的 uuid）
  "width":         512,          // 必填，来自 config 的 ai.aspect_ratios[*].scales[1x|2x|4x]
  "height":        512,
  "aspect_ratio":  "1:1",        // 必填，非空（Kotlin g.f 断言）
  "restore_faces": false         // "Enhance" 开关，UI 里对免费用户锁定
}
```

响应：
* 成功 → **HTTP 200，body 直接是图片字节**（客户端把 `inputStream` 落盘，文件名取自响应头 **`sample-uuid`**），同时把 `{prompt, scale, aspectRatio}` 写成同目录 `config.json`。
* 失败 → HTTP 500 + `{"message":"..."}`；另一种业务失败（客户端解析的）是 `{"success":false,"error":true,"error_type":"prompt","message":"..."}`（`GenerateImageError`）。

### 2.2 `POST service/sketch` 额外字段

`sketch`: base64 草图（`GenerateImageFromSketchBody.sketch`），其余字段同 generate。

---

## 3. 服务端错误码（实测）

| 触发条件 | HTTP | 响应体 | 说明 |
|---|---|---|---|
| 缺/低 `api-version` | 500 | `{"message":"Version Error. Please contact support!"}` | `28`、`29` 被拒；`30`~`36` 通过 |
| `uuid` 为 null / 非法 | 500 | `{"message":"UUID Error"}` | 校验顺序：version → uuid → token |
| `device-token` 校验失败 | 500 | `{"message":"Token Error. Please contact support!"}` | **当前所有 token 均落这里** |
| sketch 关闭 | 200 | `Sketch generation is disabled`（裸文本） | 服务端开关 |
| upscale 关闭 | 200 | `Upscale is disabled`（裸文本） | 服务端开关 |
| 未知路由 | 404 / 302 | Symfony problem+json | 框架层 |

注意校验顺序很关键：先 version、再 uuid、最后 token —— 所以只要 `uuid` 合法就必然打到 token 校验，这也是我们能确定"token 是最后一关"的方式。

---

## 4. 配置面（`configs/public/system`，实测 11 键）

| 键 | 内容 |
|---|---|
| `ai.aspect_ratios` | 7 种比例 × `1x/2x/4x` 尺寸（1:1→512/1024/2048；9:16→512×896/1024×1792/2048×3548 …） |
| `ai.aspect_ratios_xl` | 另一套更大尺寸（1:1→1024/2048；2:3→832×1216…），疑似 premium 4x 通道 |
| `ai.labels` / `ai.first_open_labeles` | 36 / 8 条推荐 prompt |
| `profanity_words_list` | 375 条敏感词 |
| `ai.style` / `ai.style_images_count` | `{images_count: 6}` / `"6"` |
| `app.page_size` | `"10"` |
| `app.image2video` | **未上线功能**：`{"durations":[5,10],"module":"video_mod3","uuid":"4e53c68e-…","price":30,"price_pro":…}` |
| `app.input_modes` | 图生图模式配置（`image_bust`，含 img1/img2 模板图 URL） |
| `onboarding_list` | 引导页视频（CDN 上的 mp4） |

> `app.image2video` 说明上游规划过"图生视频"，但 v1.0.31 客户端**没有任何**对应的 API 方法（`ic/b` 只有 9 个），说明该功能在 v32+ 才有。

## 5. 风格库（实测）

* 71 个风格，**全部 `premium: 0`**（免费）；全部 `aspect_ratio: "1:1"`、`extra-mod_ver: 1`。
* 字段：`uuid / title / label / badge / date / preview(_portrait|_landscape) / image / sketch_preview / sketch_image / images[] / aspect_ratio / premium / gender / tags / extra-sd_mode / extra-mod_ver`。
* 前几个：Modern 3D、Impressionism、Christmas、Dark Mood、Photo Real、Stunning、Cyberpunk、Cute、no style（`title == "no style"` 是默认无风格，客户端默认选中它）。

---

## 6. 身份模型深挖（这是本项目最关键的一节）

### 6.1 结论
服务端没有任何账号体系，**唯一身份就是 FCM registration token**。因此"能不能生成"等价于"能不能拿到一个服务端认可的 FCM token"。

### 6.2 已做过的尝试（全部失败）

| 尝试 | 结果 |
|---|---|
| 纯 REST 走 Firebase Installation（FIS）发号：`POST firebaseinstallations.googleapis.com/v1/projects/wavesome-ai/installations`（带 `x-goog-api-key` + `X-Android-Package` + `X-Android-Cert`） | **成功**，返回 `fid` + `authToken`（JWT, 7 天）。**改装包的证书也能过**，说明该项目没开 Android 证书白名单 |
| 用 FIS authToken 继续调 `fcmregistrations.googleapis.com/v1/projects/wavesome-ai/registrations` 换 FCM token | **失败**：`RegisterRequest` 只认 `android.package_name` 一个字段，其余全部 `Unknown name`；该 REST 面不签发 Android token（真 token 由 GmsCore 走 MCS 连接签发）。公开 discovery 文档里也没有这个资源 |
| 把 FIS authToken / FID 直接当 `device-token` 用 | 上游 `Token Error` |
| **Android 30 google_apis AVD（root）+ 装原包 + 等 FCM 注册完成**，从 `ACCOUNT_PREFERENCES.xml` 取出真实 `pushDeviceToken` | 拿得到真 token（`…:APA91b…`），但上游 **仍然 `Token Error`** |
| **同一个 AVD 里用真实 App 自己点 Create 生成** | **App 自己也弹 `Token Error. Please contact support!`** ← 决定性证据 |
| `pm clear` 换全新设备身份（新 FCM token）后直接打 API | 依旧 `Token Error` |
| 自报 premium：`PUT device/ {"premium":"sub"}` 后再生成（"sub" 是 App 里唯一的 premium 词汇） | 依旧 `Token Error` |
| `api-country` 遍历 US/DE/BR/IN/ID/PH/VN/RU/TR/MX | 全部 `Token Error`（该头不影响） |
| `api-version` 30~36、`width/height` 512/1024/2048、`restore_faces` true/false | 全部 `Token Error`（参数不影响） |
| 兄弟域名枚举（DoH）：`ailwapi350/340/300/200/100/2/1/ailwapi` … | 只有 `ailwapi360` 存在 |
| 隐藏注册路由枚举（`device/register`、`device/token`、`auth/device`、`service/register` …） | 全部 404/302，不存在 |

### 6.3 根因判断

`合理推断`（有间接证据，非 100% 确定）：**服务端 token 校验所依赖的外部能力已失效**，导致所有设备一次性全灭。依据：

1. 真机真 App 真 token 也失败 → 不是我们复制协议的问题；
2. 校验耗时 ≈ 普通接口耗时（p50 650 ms vs 普通接口 450~520 ms，同一 Cloudflare+PHP 基线），说明是本地查表/短调用，而非重活；
3. 同类项目（`AI Chat` 系列等）的经验：这类 App 用**FCM legacy server key** 去做 token 有效性校验，而 Google 已于 2024-06 彻底停用 legacy server key —— 一旦停用，这类校验对所有人返回失败；
4. Play 商店该 App 仍在维护（2026-10-05 更新，版本仍是 1.0.31），但最新评论已在抱怨"现在不能免费用文生图了"，与"生成链路对免费用户整体崩掉"的现象一致。

反方向可能（未能排除）：服务端维护了一份**私有设备白名单**，只对某些设备放行；由于 App 自身没有注册接口，这种白名单只能人工导入，无法自助获取。

---

## 7. 客户端行为/计费面（与"能否白嫖"相关的旁证）

* **无本地免费额度**：`generatedImagesCounter` 唯一用途是广告频次（`v3/e.java` 里 `counter % 3 == 1` 决定是否插广告）；`hasPremium` 只决定是否递减某个广告奖励计数。
* premium 判定 = **Adapty SDK**（`accessLevels.get("premium").isActive()`），拿到后 `PUT device/ {"premium":"sub"}` 上报服务端（服务端不校验，可伪造）。
* 广告/统计 SDK：AdMob、Pangle（穿山甲海外）、Unity Ads、Facebook、Singular、Adapty、Firebase(Crashlytics/Analytics/Config/Messaging)。
* 无签名校验、无 App Check、无 Play Integrity（`jc/a` 只有三个头即可说明）。
* 改装包带 `ApkSignatureKillerEx`（`bin/mt/signature/KillerApplication`），但**没配置** `assets/SignatureKiller/origin.apk`，所以签名杀手实际未生效（本 App 也不需要）。

---

## 8. 复现步骤（自包含）

```powershell
# 1) 静态
apktool d -f wavesome.apk -o apktool_out
jadx -d jadx_out --no-res wavesome.apk
# 关键文件： gc/g.java（baseUrl）  jc/a.java（鉴权头）  ic/b.java（端点）  ud/a.java（prefs 键）

# 2) 公开端点（无需任何凭据）
curl -H "api-version: 31" https://ailwapi360.waveabc.xyz/api/configs/public/system

# 3) 拿真机 token（需 Android 30 google_apis 镜像 + adb root）
adb -s emulator-5556 install -r wavesome.apk
adb -s emulator-5556 shell am start -n com.wave.wavesome.ai.image.generator/com.wave.wavesomeai.ui.main.MainActivity
python tools/token_from_emulator.py --serial emulator-5556

# 4) 生图（当前必然失败，用于复现 Token Error）
python -c "from wavesome import WaveSome;print(WaveSome(device_token=open('probe/token2.txt').read().strip()).generate('a fox','89d874da-2dd4-4488-aad6-a1eed5b1c3b3').error)"
```

---

## 9. 剩余风险 / 待验证

| 项 | 状态 |
|---|---|
| `service/generate` 成功响应体到底是什么格式（JPEG/PNG/WEBP）、是否带水印、单张耗时 | **待验证**（拿不到成功样本） |
| 每日/每设备额度、并发上限 | **待验证**（同上） |
| 上游是否存在 IP/地区限制（当前出口意大利 Milan） | 待验证；换出口再测才有意义 |
| 服务端是否会恢复（若根因是 legacy FCM key，基本不会） | 待验证（可长期探测） |
| `app.image2video` / `app.input_modes` 对应的 v32+ 协议 | 未知（v1.0.31 客户端无实现） |
