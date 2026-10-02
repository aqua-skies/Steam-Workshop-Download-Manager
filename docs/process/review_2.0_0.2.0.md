# SWDM 2.0 阶段 2 交付门（D2.7）· 四要素评审

> 版本：0.2.0 · 日期：2026-10-02 22:40 · 状态：**已关门（4/4 一致通过）**
> DAG v2.3 §6 阶段 2：D2.1-D2.6 全完成 · 提交链 4e2ab4a→0a18be7→9652cb2→f13a379→43da3f0→dbee9af→9a81799→ab803fb

## 一、全量回归（SP-3 沙箱驱动，TEMP+TMP 双重重定向 swdm2/.dtmp,captain 独立复跑+成员独立复现）

| 验证 | 结果 |
|---|---|
| `dotnet build Swdm2.sln` 增量 | 0 警告 0 错误 |
| `dotnet clean && build -warnaserror` **clean 口径** | **0 警告 0 错误**(D2.7 门新增；暴露并修复 xUnit2002 增量假阴性——visual-20 发现） |
| CoreTestsDriver | **72/0** ×2 轮（63 [Fact]+9 [Theory] 行） |
| SteamTestsDriver | **78/0** ×2 轮（D2.1 17+D2.2 11+D2.3 21+D2.4 17+D2.5 12;ONLINE 沙箱阻断诚实标注，captain 代理直连补验 result:1) |
| UiTestsDriver | **5/0** ×2 轮（4 脱敏管道+1 AppLaunch 真实进程） |
| **合计** | **155/0 连续两轮无异常**（第二轮=clean build 后全复跑） |

## 二、阶段 2 交付清单（commit 链）

- **D2.1**(t15,4e2ab4a) Steam/Web:IHttpClientFactory+SteamHttpClientFactory(ProxyMode 三态显式接管：Direct 禁代理/SystemProxy/Custom 显式 WebProxy+URL 校验→InvalidConfiguration)+SteamHttpHeaders 指纹头四件套（Accept-Language 承重头；X-Requested-With 旧结论 research_2 复测推翻标注）+MaxConnectionsPerServer 参数化
- **D2.2**(t16,0a18be7) Steam/Connectivity:IEndpointProbe(GET+ResponseHeadersRead 轻探/403→Blocked/网络层→Unreachable/429 归可达）+IConnectivityState 同值不触发；双网络环境真实探测 docs/connectivity_probe_2.2.md（诚实标注"直连不可达"预判未成立=fake-IP TUN 网关）
- **D2.3**(t17,9652cb2) Web API: GetPublishedFileDetails(batch 封包）+GetCollectionDetails(递归+sortorder+999↔200 环引用 visited)+storesearch;8 类 SteamError 映射；IConnectivityGate 门（Api 不可达 0 请求）；在线验证 3808352517 result:1
- **D2.4**(t18,f13a379) Steam/Resilience: IThrottler 差异 bucket 全程锁+ICircuitBreaker Closed→Open→HalfOpen+ResiliencePipeline 开态 Fail(CircuitOpen) 不抛+假钟 seam；客户端集成 api/store bucket
- **D2.5**(t19,43da3f0) Steam/Community:Browse+详情富化+可达门（S4 0 请求）+缓存深拷贝；CommunityHtmlParser 稳定锚（React 改版研究：browse 混淆类→filedetails/?id=N+img src/alt;detail 旧类稳；AppId 锚 myworkshopfiles/?appid=N);真实 fixture 内嵌（browse 679KB/30 物品；detail 109KB)
- **D2.6**(t20,ab803fb) 重标定：CalibBench 86 分钟/436 条（calibration_1.{csv,json,md})
  - B1:24/24 停等后全 200=**解除机制=头指纹非等待时长**（1.x 退避假设复验推翻，参数防御保留 5000/90000)
  - B2:0.5s×20 零失败→**ThrottleMs 6000/2000→1000/1000** 落地（appsettings/Throttler/Options 文档三同步+测试断言同改）
  - 新机制：**限流=会话累计天花板 ~117 请求非间隔维度**(qa-20 独立复核修正逐轮表述：1s+ 通过/失败按累计预算跨轮移动；8s 轮内部分恢复=时间恢复机制直接证据）→熔断器恰为兜底（120s≈20 次预算）
  - 误诊撤回：20:21"IP 限流"实为用户关闭代理软件（先查本地再归因远端）

## 三、讨论组评审（三原则：精简/用户体感/基本功能）

- **arch-20 赞成**（22:25):精简=纯基础设施零膨胀+D2.6 删减过保守参数方向一致；体感=节流 6 倍缩短+退避旧范式推翻；基本功能=155/0 全绿（D2.1/D2.2/D2.4 代码级核验）。保留记录：api/store bucket 未覆盖（非 429 敏感路径，0.3/D4 覆盖，不阻碍）
- **qa-20 赞成**（22:29):独立复核 436 条 csv(B1 24/24 验证成立；B2 总数与报告一致并修正逐轮模式表述三处——强化核心结论）；支持 ThrottleMs 1000/1000（0.5s 零失败含 2 倍余量）；记录项同 arch-20
- **visual-20 赞成→无条件**（22:35):条件项 xUnit2002(CommunitySourceTests.cs:47 值类型 tuple Assert.NotNull——**增量构建 Roslyn 分析器缓存掩盖=增量假阴性**，D1.5r 假绿同族）已修复（captain 域代码）+clean build -warnaserror 0-0 复验；流程采纳：门 checklist 增 clean build 口径；独立复现 155/0
- **captain 赞成**：四要素齐备（回归连续两轮/评审 4/4/版本 0.2.0/记录链），误诊与推翻均有诚实记录

**4/4 一致通过，关门。**

## 四、版本升级

- Directory.Build.props: `0.1.0` → **`0.2.0`**（单一事实源，build 输出 Assembly=0.2.0.0)
- CHANGELOG.md 新增 `[0.2.0]` 条目（交付内容+验证+已知保留）

## 五、放行条件 checklist

- [x] 全量回归绿（**155/0 连续两轮**，增量+clean 双口径 build 0-0)
- [x] D2.6 三件数据落盘（csv/json/md)+旧值差异表
- [x] 讨论组一致通过（arch-20/qa-20/visual-20/captain 4/4 赞成，见三）
- [x] 版本号 0.2.0+CHANGELOG 条目
- [x] 交付=一致通过+连续两轮复测无异常（captain 独立复跑+visual-20 独立复现+clean 后全复跑）

## 六、已知保留（C7,不阻碍 0.2.0)

- api bucket 100ms/store bucket 250ms 未实测覆盖（非 429 敏感路径）→D3/D4 或 0.3
- 天花板数值（~117）单出口 IP 单轮观测值，跨环境复测
- B1 退避 5000/90000 防御默认（无实测必要性证据亦无反证）
