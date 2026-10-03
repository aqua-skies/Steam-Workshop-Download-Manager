# SWDM 1.4.2 输入：核心层只读静态审计（2026-09-30）

范围：swdm/core/ 全目标模块静态通读 + 跨文件调用方核对（services/settings_tab/workshop_tab/workers/debug_tab）+ 一条纯计算验证。未动任何文件/未跑写盘脚本，代码冻结未受影响。

范围说明：任务清单里的 library_db 模块不存在，SQLite 落地实际是 swdm/core/mod_library.py（同批审计）。

---

## 严重度清单（文件:行号 / 问题 / 修法 / 工作量 / 建议1.4.2）

### P0 严重（建议 1.4.2 必修）

**1. Backoff 等级无 clamp → 队列死锁** — throttle.py:86-87 + downloader.py:767
- `base * factor**level` 先于 min 溢出（2.0**1024 即 OverflowError，已实机验证），连续约1024次失败（夜间挂机+死网即可达到）在 downloader.py:767 的 record_failure（未包try）击穿工作线程 → job 卡在 _active → _run_loop 的 `len(self._active)>=concurrency` 永久挂起 → 队列死锁。
- 修法：_delay_unlocked 先 clamp level；767行加防御。S。建议1.4.2：是。

**2. cancel() 取消信号发到错误引擎（C3 账号通道）** — downloader.py:305
- cancel() 只调 self.engine.cancel()（共享匿名引擎）；C3 账号通道跑在专属引擎(account_steamcmd.py:135)上时取消信号发到错误引擎，账号 steamcmd 子进程不被中断、继续下载落盘，job 却已标 CANCELLED。
- 修法：记录 job->实际provider，cancel 时 provider.cancel()。M。是。

**3. 匿名态"测试登录"与下载并发引擎竞态** — steamcmd_engine.py:247-269/302-305 × settings_tab.py:432(+debug_tab.py:178)
- 直接用 svc.engine 且不走 _engine_lock，与下载并发时覆盖 _proc（manager cancel 会 terminate 错的进程）、_cancel_flag.clear() 解除挂起的取消、污染 _activity/_stall_killed。
- 修法：test_login 走串行锁或现场造独立引擎。M。是。

**4. "最大并发下载"配置永不生效** — downloader.py:119-121 × services.py:58-60
- AdaptiveConcurrency._max 构造时固化，refresh_engine 只改 downloader.max_concurrent；调大永不生效（实际仍≤旧值），调低也不立即降——配置变更静默失败。
- 修法：set_max() 同步。S。是。

### P1 高（建议 1.4.2 修）

**5. 看门狗盯错目录** — steamcmd_engine.py:344
- download_item 的看门狗 content_dir 用 self.install_dir 而非 install_dir 参数；配置了 per-game 目录时下载落在游戏目录、看门狗盯引擎默认目录，磁盘增长观测不到 + workshop 下载常60s+无输出 → 大文件被误判"停滞超时"杀掉、失败重试循环。主/账号引擎同犯。S。是。

**6. priority 未豁免全局节流** — steam_api.py:102-113/373
- _Throttle.acquire 不豁免 priority（只豁免端点级）；trip 后 _min_interval 抬到30-60s，用户点击/依赖解析在熔断窗外要排满等待，与"节流永不挡用户操作"声明相悖。S-M。是。

**7. config 读写无数据锁** — config.py:120-177
- get/set/load/reset 对 _data 无数据锁，reset/load 不持 _file_lock，save 在 _file_lock 内读未加锁的 _data；GUI写×核心读并发会撕裂嵌套字典（配置是下载/游戏目录/更新检查的热依赖）。
- 修法：_data_lock(RLock) 全保护，锁序 _data_lock→_file_lock。M。是（需回归配置路径）。

### P2 中（视排期）

**8.** ggnetwork.py:214 × failure_reason.py:78：GGNetwork 解析失败消息含"（服务不可用或被限流）"→ 一律落 RATE_LIMITED，用户被告知"触发 Steam 限流"——第三方后端故障被错归因。S。
**9.** failure_reason.py:84：LOGIN_FAILED 只认 startswith("登录失败")；链式异常包装 f"{name}: {e}" 与 steamcmd 原始 "Not Logged On" 漏判 → 滑落 GENERIC/ACCOUNT_NEEDED（与误报红线同类伤害；当前账号 hint 仅靠碰巧含 "Steam Guard" 侥幸命中）。S。
**10.** steam_api.py:780-784 × workshop_tab.py:1174-1202：browse 的 _browse_breaker 只在 RequestException 时 record_failure，429/403（RateLimitError 非 RequestException）不记 → 预取闸门在限流期内以为健康、持续空打并烧满退避。S。
**11.** game_search.py:95-97：最小间隔的 read-sleep-write 在锁外，并发联想请求可同时发出、实际间隔归零（正是实测触发 WinSock 10053 的连发模式）。建议仿 _endpoint_throttle 锁覆盖睡眠全程。S。
**12.** mod_library.py:156-329：`with self._conn() as c:` 只管事务不管 close，依赖 CPython 引用计数（异常路径残留句柄/cursor；PyPy 风险）；jobs 表只插不删、无限增长。S-M。
**13.** steamcmd_engine.py:302：proc.wait(timeout=30) 可抛 TimeoutExpired，跳过 _proc 清理、进程句柄滞留（被外层吞成"引擎异常"）。S。
**14.** ggnetwork.py:120/304-305：provider.cancel() 置位的 _stopping 全模块无人读取（死状态，取消契约形同虚设，实际靠 manager stop_event）；_maybe_extract 同名 .gma 互相 os.replace 覆盖（静默丢内容）、无 .gma 时 _extracted/ 残留并被 import 重复计字节。S。
**15.** downloader.py:202/272：物品已在队列时返回的是新建未入队的"幽灵 job"，其状态恒 QUEUED，UI 绑定它永不更新。S。
**16.** downloader.py:386-404：retry() 经 enqueue 新建 job，attempt_messages/signals 清零，failure_reason 信号②（重试仍同错）在手动脉冲场景失效。S。

### P3 低（13 条，要点）

- logger.py:79-80 重初始化不 close handler（日志文件锁滞留）
- api_cache.py:150-152 get_or_compute 等待者无超时自旋且该 API 生产已无调用方（死代码）
- detail_cache.py:131/148 .tmp 孤儿+stored_tu=0 永不双失效
- steam_api.py:317 类属性 _endpoint_last 被实例属性遮蔽（死代码）
- account_steamcmd.py:39/91 _instances 只增不删（registry 重建泄漏旧实例）
- steam_api.py:977-990 fetch_image 非原子写+并发交叉写+key截断180撞键
- mod_library.py:266-277 搜索 LIKE 通配符（%/_/）语义扩宽
- steam_api.py:222-234 from_dict 非数值字段直接 int() 抛 ValueError 且上游无兜底
- auth.py:62-73/160-161 _AUTH_FILE 非原子写+logout 不删 keyring
- downloader.py:295-330 回调持锁触发
- steamcmd_engine.py:144 声明的 _lock 从未使用
- mod_library.py:186-193 upsert 覆写 enabled（重下后用户禁用态被重置）

---

## 8 桶边界专检结论

桶序总体合理：E③"…下载内容为空（可能触发限流）"因 #2 先行正确落 EMPTY_SUCCESS✔；HTTP 429 经 signals→classify 链正确落 RATE_LIMITED✔；"未开始下载（物品可能不存在…）"不含子串"物品不存在"，不误落 ITEM_GONE✔。两处误分类风险=P2-1/P2-2，均为"分类质量"非崩溃。

## 熔断组件专检

circuit.py 与任务描述一致（3次连续失败→15s 冷却，ConnectionError 立即熔断；in_cooldown 无锁读 float 可不修）；registry._Circuit 是另一套（3次→60s），两套并存建议文档显式区分；豁免逻辑（terminal + breaker_exempt 不熔断兜底链）正确。缺陷=P2-10(browse breaker 不吞 429)。

## 无误报确认（不要重改）

A-P1 取消/完成竞态已闭环；api_cache/detail_cache 深拷贝三路径一致；零除 guards 全覆盖；路径穿越防御到位；引擎局部快照防 _proc 覆盖；账号凭据四风控到位。

## 1.4.2 修复集建议

P0-1/2/3/4 + P1-1/2 + P2-1/2 = 约1-1.5工作日（多为S/M纯逻辑，可配回归脚本）；P1-3 与 P2-3 涉及行为变更建议走讨论组评审再合入；P3 并技术债批次。
