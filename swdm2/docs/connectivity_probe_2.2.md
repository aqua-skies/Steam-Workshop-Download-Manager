# D2.2 端点可达性探测 · 双网络环境真实记录

> 时间：2026-10-02 18:36（+08:00） · 执行：arch-20 · 契约：`Swdm2.Steam.Connectivity.EndpointProbe`（D2.2）
> 方法：真实 HTTP 请求（GET + ResponseHeadersRead 轻探，超时 8s），经 D2.1 `SteamHttpClientFactory`（指纹头四件套：UA/Accept/Accept-Language/**承重头**/X-Requested-With）
> 设计对照纪律：以下为**实测事实**，非推测；网络失败≠不可行，可达性以响应状态为准（2xx-5xx=可达，403=Blocked，TLS/TCP/超时=Unreachable；429 归可达）。

## 环境标注

| 环境 | 网络条件 | 出口 |
|---|---|---|
| A | 本机 fake-IP 代理：DNS→198.18.0.124（Clash/Meta TUN 接口），HTTP 代理 `http://127.0.0.1:7897`（ProxyMode=Custom） | 香港 IDC（AS134972，43.243.192.92） |
| B | 直连（ProxyMode=Direct）：api.steampowered.com 本机解析到 fake-IP 198.18.0.9 ，经 TUN 网关 SNI 路由出网 | 同上出口（TUN 层直连，不经 HTTP 代理） |

## 探测结果（n=1，单轮快照）

### 环境 A：fake-IP HTTP 代理（ProxyMode.Custom=http://127.0.0.1:7897）

| 端点 | URL | Reachability | LatencyMs |
|---|---|---|---|
| Api | `https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/` | **ViaProxy** | 704 |
| Store | `https://store.steampowered.com/api/storesearch/?term=swdm&l=schinese&cc=CN` | **ViaProxy** | 1590 |
| Community | `https://steamcommunity.com/` | **ViaProxy** | 649 |

### 环境 B：直连（ProxyMode.Direct）

| 端点 | Reachability | LatencyMs |
|---|---|---|
| Api | **Direct** | 631 |
| Store | **Direct** | 623 |
| Community | **Direct** | 1040 |

## 结论与标注

1. **实测结论**：两环境下三端点均可达（A=ViaProxy，B=Direct），本机当前网络条件下**无 Blocked/Unreachable**。
   - ⚠️ 与先验预期差异（诚实标注）：预判"直连环境因 fake-IP 解析可能不可达"未成立——fake-IP 网关（198.18.0.9）是 TUN 层接口，
     直连请求经 SNI 路由出网，故 Direct 亦可达。这与"直连→失败"假设相反，**以实测为准**（设计对照纪律）。
     B 环境结果仅对**当前机器网络栈**有效，换纯净直连环境（无 TUN）需重测——重测预测为 Real Direct（真实出口 IP）。
2. 403/Blocked 与 429（限流）为**不同层级**：本探测 0 次 403（与 research/steam_429_403_research.md 复测一致：403 本机无法稳定复现，403=IP/边缘层不可控）；
   429 归可达判定（服务端有应答），限流归节流器/熔断器（D2.4）。
3. 代理路径延迟（A）与直连路径（B）同量级（600-1600ms），代理开销不显著——**单轮快照，非统计结论**；
   D2.6 B2 标定任务将做多请求统计（n≥3 × 多档间隔）。
4. 指纹头证据：探测请求经工厂携带 Accept-Language 等四件套（断言见 `EndpointProbeTests.Probe_Request_Carries_Factory_Fingerprint_Headers`，
   loopback stub 真实字节捕获）——1.x 429 学费的 C# 落地。
