# SWDM 2.0 阶段 2 交付门（D2.7）· 四要素评审

> 版本：0.2.0 · 日期：2026-10-02 · 状态：**进行中**（D2.1-D2.5 已完成，D2.6 标定执行中）
> DAG v2.3 §6 阶段 2：D2.1 HttpClient 工厂 / D2.2 端点探测 / D2.3 Web API 客户端 / D2.4 节流器+熔断器 / D2.5 社区页面回退 / D2.6 重标定 B1+B2 / D2.7 本门

## 一、全量回归（SP-3 沙箱驱动，TEMP+TMP 双重重定向 swdm2/.dtmp）

| 验证 | 结果 |
|---|---|
| `dotnet build Swdm2.sln` | 0 警告 0 错误 |
| CoreTestsDriver | 待最终复跑（当前 72/0） |
| SteamTestsDriver | 待最终复跑（当前 78/0:D2.1 17+D2.2 11+D2.3 21+D2.4 17+D2.5 12) |
| UiTestsDriver | 待最终复跑（当前 5/0:4 脱敏管道+1 AppLaunch 真实进程） |

## 二、阶段 2 交付清单

- **D2.1**(4e2ab4a) Steam/Web: IHttpClientFactory + SteamHttpClientFactory(ProxyMode 三态注入 SocketsHttpHandler)+SteamHttpHeaders 指纹头四件套（1.x 429 学费：Accept-Language 承重头；X-Requested-With 旧结论已 research_2 推翻，仅冗余层）
- **D2.2**(0a18be7) Steam/Connectivity:IEndpointProbe(GET+ResponseHeadersRead 轻探/403→Blocked/网络层→Unreachable/429 归可达）+IConnectivityState 同值不触发
- **D2.3**(9652cb2) Web API: GetPublishedFileDetails(batch itemcount=N 封包）+GetCollectionDetails(递归+sortorder+999↔200 环引用 visited 保护）+storesearch;失败映射 8 类 SteamError;真实在线 3808352517 result:1 验证
- **D2.4**(f13a379) Steam/Resilience: IThrottler 差异 bucket 全程锁+ICircuitBreaker Closed→Open→HalfOpen+ResiliencePipeline 开态 Fail(CircuitOpen) 不抛+假钟 seam
- **D2.5**(43da3f0) Steam/Community:Browse 列表+详情富化+可达门（S4 0 请求）+缓存深拷贝；真实 fixture（React 改版后锚点研究）

## 三、D2.6 重标定结果

> 待补：docs/calibration_1.{csv,json,md} 三件 + 旧值差异说明（1.x:6s/2s/5s/90s)+Options 默认值锁定或标注待定

## 四、讨论组评审（三原则：精简/用户体感/基本功能）

待 D2.6 完成后开：功能删减/改进/添加可行性评估 + 四人一致投票

## 五、版本升级

Directory.Build.props 0.1.0 → 0.2.0 + CHANGELOG.md 条目

## 六、放行条件

- [ ] 全量回归绿
- [ ] D2.6 三件数据落盘+旧值差异
- [ ] 讨论组一致通过
- [ ] 版本号+CHANGELOG
- [ ] 交付=一致通过+连续两轮无异常复测
