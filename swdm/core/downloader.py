"""下载管理器：队列 + 并发调度 + 状态回调。

与 GUI 解耦：通过可订阅的回调（on_started/on_progress/on_finished）通知状态，
GUI 层（QThread/信号）负责桥接。核心可独立测试。
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .game_dirs import configured_game_dirs
from .logger import get_logger
from .mod_library import ModLibrary, ModRecord
from .steam_api import WorkshopItem
from .steamcmd_engine import DownloadResult, DownloadStatus, SteamCMDEngine
from .throttle import (
    AdaptiveConcurrency,
    Backoff,
    ProgressSmoother,
    classify_steamcmd_line,
    jittered,
)

log = get_logger("swdm.downloader")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadJob:
    item: WorkshopItem
    appid: str
    status: JobStatus = JobStatus.QUEUED
    bytes_done: int = 0
    total_bytes: int = 0
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    attempt: int = 0
    # 需求 3：速度/ETA 供 UI 展示；resumed_bytes 为重试时已有的部分内容字节数
    speed_mbps: float = 0.0
    eta_seconds: float = 0.0
    resumed_bytes: int = 0
    # 1.4.0：实际使用的 provider 名（链式回退后记录最终通道）
    channel: str = ""
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def id(self) -> str:
        return self.item.publishedfileid

    @property
    def percent(self) -> int:
        # 完成判定以字节数为准（u9/u10）：即使完成回调被 Qt 合并/延迟，
        # 只要 bytes_done 已达 total_bytes，UI 立刻显示 100%，不再卡 99%
        if self.total_bytes > 0:
            if self.bytes_done >= self.total_bytes:
                return 100
            return min(99, int(self.bytes_done / self.total_bytes * 100))
        return -1


class DownloadManager:
    """管理下载队列与并发执行。"""

    def __init__(
        self,
        engine: SteamCMDEngine,
        library: ModLibrary,
        max_concurrent: int = 2,
        auto_retry: int = 1,
        jitter_base: float = 2.0,
        jitter_spread: float = 0.4,
        backoff: Backoff | None = None,
        concurrency: AdaptiveConcurrency | None = None,
        api=None,
    ) -> None:
        self.engine = engine
        self.library = library
        self.api = api  # CDN 通道需要（解析 file_url）
        self.max_concurrent = max(1, max_concurrent)   # 并发上限（配置值）
        self.auto_retry = auto_retry
        # 需求 1：抖动 / 全局退避 / 并发自适应
        self._jitter_base = max(0.0, float(jitter_base))
        self._jitter_spread = max(0.0, min(1.0, float(jitter_spread)))
        self._backoff = backoff if backoff is not None else Backoff()
        self._concurrency = (
            concurrency if concurrency is not None else AdaptiveConcurrency(self.max_concurrent)
        )
        self._queue: deque[DownloadJob] = deque()
        self._active: dict[str, DownloadJob] = {}
        self._paused = False          # F1：暂停标志（停止派发新任务）
        self._done: list[DownloadJob] = []
        # A-P1：cancel 已受理、但 worker 尚未收尾的 job_id。
        # cancel() 抢先把 job 置 CANCELLED 并登记后，worker 仍可能在
        # 微秒窗口内跑完链路并覆盖终态/导入库/触发重试；worker 收尾时
        # 见到自己在此集合中，则让取消语义胜出。
        self._cancelling: set[str] = set()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        # steamcmd 引擎串行锁（同会话不支持并发，详见 _run_steamcmd）
        self._engine_lock = threading.Lock()
        self._running = False
        self._worker: threading.Thread | None = None
        # 回调
        # 观察者列表（允许多个 GUI 监听者；回调在子线程触发，
        # GUI 侧必须通过 Qt 信号桥接回主线程，否则跨线程操作控件会冻结）
        self.on_started: list = []      # [(job)]
        self.on_progress: list = []     # [(job)]
        self.on_finished: list = []     # [(job)]
        self.on_queue_changed: list = []
        self.on_throttle = None     # (kind, line) 节流信号，供 UI 订阅
        self.last_throttle: tuple | None = None
        # 桥接引擎的限流/超时特征 -> 退避 + 并发降级
        # append 订阅（A-P3：引擎侧已改为订阅者列表，后赋值不覆盖既有订阅）
        self.engine.on_throttle_signal.append(self._on_throttle_signal)

    # ----------------------------------------------------------- 节流（需求 1）
    def _on_throttle_signal(self, kind: str, line: str) -> None:
        """steamcmd 输出出现 RateLimit/Timeout/Retrying 特征时的处理。

        硬信号（rate_limit / timeout）：全局退避升级 + 并发立刻降到 1。
        软信号（retry）：仅小幅退避（steamcmd 自己已在重试）。
        """
        self.last_throttle = (kind, line, time.time())
        if kind in ("rate_limit", "timeout"):
            delay = self._backoff.record_failure(kind)
            cur = self._concurrency.on_failure(kind)
            log.warning(
                "触发退避 [%s]：并发上限 -> %d，本次退避 %.0fs（等级 %d）",
                kind, cur, delay, self._backoff.level,
            )
        else:
            self._backoff.nudge()
            log.info("软信号 [%s]：轻微退避（等级 %d）", kind, self._backoff.level)
        if self.on_throttle:
            try:
                self.on_throttle(kind, line)
            except Exception:  # noqa: BLE001
                log.exception("on_throttle 回调异常")

    def _throttle_wait(self, job: DownloadJob) -> None:
        """任务开始前的等待：随机抖动 + 当前退避等级对应的间隔。

        抖动打散请求节律；退避等级越高间隔越长（连续失败后的全局退避）。
        """
        delay = max(self._jitter_base, self._backoff.level_delay)
        delay = jittered(delay, self._jitter_spread)
        if delay <= 0:
            return
        job.message = (
            f"退避等待 {delay:.1f}s 后重试…" if job.attempt > 0
            else f"排队节流 {delay:.1f}s…"
        )
        log.info("任务 %s 节流等待 %.1fs（退避等级 %d）", job.id, delay, self._backoff.level)
        time.sleep(delay)

    # ------------------------------------------------------------- 队列操作
    def enqueue(self, item: WorkshopItem, appid: str) -> DownloadJob:
        job = DownloadJob(item=item, appid=str(appid), total_bytes=item.file_size)
        with self._lock:
            if any(j.id == job.id for j in self._queue) or job.id in self._active:
                log.info("物品 %s 已在队列中，跳过", job.id)
                return job
            self._queue.append(job)
            self._cond.notify_all()
        log.info("加入下载队列: %s (%s)", job.id, item.title)
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()
        return job

    def _fire_started(self, job) -> None:
        for cb in list(self.on_started):
            cb(job)

    def _fire_progress(self, job) -> None:
        for cb in list(self.on_progress):
            cb(job)

    def _fire_finished(self, job) -> None:
        for cb in list(self.on_finished):
            cb(job)

    def add_listener(self, started=None, progress=None, finished=None,
                     queue_changed=None) -> None:
        """注册下载事件监听（可多个）。回调在下载子线程触发，
        GUI 侧必须经 Qt 信号桥接回主线程。"""
        if started:
            self.on_started.append(started)
        if progress:
            self.on_progress.append(progress)
        if finished:
            self.on_finished.append(finished)
        if queue_changed:
            self.on_queue_changed.append(queue_changed)

    def enqueue_with_dependencies(
        self,
        item: WorkshopItem,
        appid: str,
        api: Any = None,
        auto_deps: bool = True,
        skip_installed: bool = True,
        max_depth: int = 10,
    ) -> list[DownloadJob]:
        """下载物品并自动带上前置依赖（需求：依赖 mod 下载配置）。

        依赖解析成功时返回的作业列表按"依赖在前、本物品在后"排序；
        解析失败或关闭自动依赖时仅入队本物品。
        """
        jobs: list[DownloadJob] = []
        if auto_deps and api is not None:
            try:
                deps, _skipped = api.resolve_dependency_tree(
                    item, max_depth=max_depth,
                    skip_installed=skip_installed, library=self.library,
                )
            except Exception:  # noqa: BLE001
                log.exception("解析依赖树失败，仅下载本物品")
                deps = []
            for dep in deps:
                if dep.publishedfileid == item.publishedfileid:
                    continue
                jobs.append(self.enqueue(dep, dep.appid or str(appid)))
        jobs.append(self.enqueue(item, str(appid)))
        return jobs

    def enqueue_high_priority(self, item: WorkshopItem, appid: str) -> DownloadJob:
        """插入队首（前置依赖优先于本物品下载）。已在队列中的跳过。"""
        job = DownloadJob(item=item, appid=str(appid), total_bytes=item.file_size)
        with self._lock:
            if any(j.id == job.id for j in self._queue) or job.id in self._active:
                log.info("物品 %s 已在队列中，跳过", job.id)
                return job
            self._queue.appendleft(job)
            self._cond.notify_all()
        log.info("插入队首: %s (%s)", job.id, item.title)
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()
        return job

    def enqueue_many(self, items: list[WorkshopItem], appid: str) -> list[DownloadJob]:
        return [self.enqueue(it, appid) for it in items]

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._active.get(job_id)
            if job:
                # 竞态窗口：worker 已在 _exec_job 里把 job 置成终态
                # （SUCCESS/FAILED）但尚未走到 553 行移出 _active。
                # 此时 cancel() 若抢先覆盖成 CANCELLED，会把真实结果抹掉
                # （下载成功却显示已取消，并造成 _done 重复登记/finished
                # 双发）。终态 job 不再取消，交给 worker 的收尾路径登记。
                if job.status in (JobStatus.SUCCESS, JobStatus.FAILED):
                    if self.on_queue_changed:
                        for cb in list(self.on_queue_changed):
                            cb()
                    return
                # A-P1：先登记 pending-cancel 再置停止标记（同一把锁内），
                # 保证 worker 一旦观察到 _stop 被置位时，_cancelling 里
                # 一定已有本 job_id（worker 据此判定取消胜出）
                self._cancelling.add(job_id)
                job._stop.set()
                try:
                    self.engine.cancel()
                except Exception:  # noqa: BLE001
                    log.debug("引擎取消异常（忽略，强制标记）", exc_info=True)
                # 强制把卡住的任务移出活跃集合，避免取消后仍显示"下载中"
                # 且再点取消/移除无反应（bug4/7）
                if job_id in self._active:
                    self._active.pop(job_id, None)
                    job.status = JobStatus.CANCELLED
                    job.message = "已取消"
                    self._done.append(job)
                    self._cond.notify_all()
                    self._fire_finished(job)
                if self.on_queue_changed:
                    for cb in list(self.on_queue_changed):
                        cb()
                return
            for j in list(self._queue):
                if j.id == job_id:
                    self._queue.remove(j)
                    j.status = JobStatus.CANCELLED
                    j.message = "已从队列移除"
                    self._done.append(j)
                    self._fire_finished(j)
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()

    def cancel_all(self) -> None:
        with self._lock:
            for j in list(self._queue):
                self.cancel(j.id)
            for jid in list(self._active):
                self.cancel(jid)

    def clear_history(self) -> None:
        with self._lock:
            self._done.clear()

    # ------------------------------------------------- F1：批量队列管理
    def pause_all(self) -> None:
        """暂停：进行中的任务继续跑完，队列里的不再派发。"""
        with self._lock:
            self._paused = True
        self._notify_queue_changed()

    def resume_all(self) -> None:
        """恢复派发。"""
        with self._lock:
            self._paused = False
            self._cond.notify_all()
        self._notify_queue_changed()

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def retry_all_failed(self) -> int:
        """重试全部失败/已取消任务，返回重试数量。"""
        with self._lock:
            failed = [j for j in self._done
                      if j.status in (JobStatus.FAILED, JobStatus.CANCELLED)]
        n = 0
        for j in failed:
            if self.retry(j.id):
                n += 1
        return n

    def clear_completed(self) -> int:
        """清空已完成（含失败/取消）的记录，返回清除数量。"""
        with self._lock:
            n = len(self._done)
            self._done.clear()
        self._notify_queue_changed()
        return n

    def _notify_queue_changed(self) -> None:
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()

    def retry(self, job_id: str) -> bool:
        """重试失败/已取消的任务：从完成记录移除旧 job 后重新入队。

        返回 True 表示已重新排队。供下载页失败行"重试"按钮调用
        （B3：核心层原有 auto_retry，但 UI 无手动重试入口）。
        """
        with self._lock:
            old = next((j for j in self._done if j.id == job_id), None)
            if old is None:
                return False
            if old.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
                return False
            self._done.remove(old)
            # A-P1：清除可能残留的 pending-cancel 标记，避免重试的
            # 成功结果被上一轮取消的残留标记误杀为 CANCELLED
            self._cancelling.discard(job_id)
        # enqueue 内部也要持锁：先出锁再入队，避免重入死锁
        job = self.enqueue(old.item, old.appid)
        return job.id == job_id

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "queued": [j for j in self._queue],
                "active": list(self._active.values()),
                "done": list(self._done),
            }

    # ------------------------------------------------------------- 生命周期
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker = threading.Thread(target=self._run_loop, daemon=True, name="dl-manager")
            self._worker.start()
        log.info(
            "下载管理器已启动 (并发上限=%d，任务间抖动 %.1f±%.0f%%)",
            self.max_concurrent, self._jitter_base, self._jitter_spread * 100,
        )

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._cond.notify_all()
        self.cancel_all()

    def _run_loop(self) -> None:
        while self._running:
            with self._lock:
                self._cond.wait_for(lambda: bool(self._queue) or not self._running)
                if not self._running:
                    break
                # F1：暂停时不派发新任务（进行中的任务继续跑完）
                while self._paused and self._running:
                    self._cond.wait(timeout=0.5)
                if not self._running:
                    break
                # 生效并发上限由自适应策略决定（失败特征 -> 降到 1）
                while len(self._active) >= self._concurrency.current:
                    self._cond.wait(timeout=0.5)
                if not self._queue:
                    continue
                job = self._queue.popleft()
                self._active[job.id] = job
            t = threading.Thread(target=self._exec_job, args=(job,), daemon=True)
            t.start()

    # ------------------------------------------------------------- 单任务
    def _run_steamcmd(self, job: DownloadJob, install_dir: str, smoother):
        """串行调用 steamcmd（bug7/8：steamcmd 同会话不支持并发，
        多任务共享 engine 的 _proc 实例字段会竞态崩溃，
        必须加锁串行；cancel 因此也只会作用于当前唯一任务）。"""
        with self._engine_lock:
            return self.engine.download_item(
                appid=job.appid,
                item_id=job.id,
                total_hint=job.total_bytes,
                install_dir=install_dir,
                on_progress=lambda pct, done, msg: self._on_engine_progress(
                    job, smoother, pct, done, msg
                ),
            )

    def _content_dir(self, job: DownloadJob, install_dir: str) -> str:
        """统一内容落地目录（所有 provider 共用 steamcmd 布局）。"""
        base = install_dir or getattr(self.engine, "install_dir", "") or ""
        dest_dir = os.path.join(
            base, "steamapps", "workshop", "content", str(job.appid), str(job.id)
        )
        os.makedirs(dest_dir, exist_ok=True)
        return dest_dir

    def _run_provider(self, provider, job: DownloadJob, install_dir: str,
                      smoother) -> DownloadResult:
        """执行单个 provider。steamcmd 走串行锁路径，其余走 provider.download。"""
        name = provider.meta.name
        if name == "steamcmd":
            # 保持 1.3.9 行为：engine_lock 串行 + engine.download_item
            return self._run_steamcmd(job, install_dir, smoother)
        dest_dir = self._content_dir(job, install_dir)
        return provider.download(
            job.item, dest_dir,
            on_progress=lambda pct, done, msg: self._on_engine_progress(
                job, smoother, pct, done, msg
            ),
            stop_event=job._stop,
            total_hint=job.total_bytes,
        )

    def _build_channel_chain(self, preferred: str):
        """构造 provider 回退链；注入 engine 并订阅限流信号。"""
        from .providers import get_registry

        reg = get_registry()
        # steamcmd provider 需要共享 engine 单例（串行锁仍在 manager 侧）
        sc = reg.get_provider("steamcmd", self.api)
        if sc is not None and getattr(sc, "engine", None) is not self.engine:
            sc.set_engine(self.engine)
            if self._on_throttle_signal not in sc.on_throttle_signal:
                sc.on_throttle_signal.append(self._on_throttle_signal)
        return reg.build_chain(preferred, api=self.api)

    def _run_channel_chain(self, job: DownloadJob, install_dir: str,
                           smoother) -> DownloadResult:
        """遍历 provider 回退链。一条链 = 一次 attempt，回退不消耗重试。"""
        from .providers import get_registry

        _reg = get_registry()
        preferred = "steamcmd"
        try:
            from .config import get_config

            preferred = (get_config().get("download", "channel",
                                          default="steamcmd") or "steamcmd")
        except Exception:  # noqa: BLE001
            pass

        try:
            chain = self._build_channel_chain(preferred)
        except Exception:  # noqa: BLE001
            # registry 不可用（如 providers 包损坏）：降级到旧行为
            log.exception("provider 链构造失败，降级 steamcmd")
            chain = []

        if not chain:
            # 兜底：至少保证 steamcmd 可用
            try:
                from .providers.steamcmd import SteamCMDProvider

                prov = SteamCMDProvider({}, api=self.api)
                prov.set_engine(self.engine)
                chain = [prov]
            except Exception as e:  # noqa: BLE001
                return DownloadResult(
                    item_id=job.id, appid=job.appid,
                    status=DownloadStatus.FAILED,
                    message=f"无可用下载通道: {e}",
                )

        result: DownloadResult | None = None
        for provider in chain:
            name = provider.meta.name
            try:
                # 每个实例订阅一次限流信号（熔断/退避用）
                if self._on_throttle_signal not in provider.on_throttle_signal:
                    provider.on_throttle_signal.append(self._on_throttle_signal)
                result = self._run_provider(provider, job, install_dir, smoother)
            except Exception as e:  # noqa: BLE001
                log.exception("通道 %s 执行异常 %s", name, job.id)
                result = DownloadResult(
                    item_id=job.id, appid=job.appid,
                    status=DownloadStatus.FAILED, message=f"{name}: {e}",
                )
            if result is None:
                continue
            job.channel = name
            # 熔断反馈：成功重置计数，失败累计（连续 3 次后 60s 冷却跳过该通道）
            # terminal 通道（steamcmd）豁免——它是永不下线的兜底，熔断它会让链变空
            if result.status == DownloadStatus.SUCCESS:
                _reg.record_success(name)
            elif result.status != DownloadStatus.CANCELLED and not provider.meta.terminal:
                _reg.record_failure(name)
            if result.status == DownloadStatus.SUCCESS:
                return result
            if job._stop.is_set():
                return result
            # 结构化回退判定（替代旧的消息含"回退"字符串判定）
            if not provider.should_fallback(result):
                return result
            log.info("物品 %s 通道 %s 失败，回退下一通道：%s",
                     job.id, name, (result.message or "")[:80])
        if result is None:
            result = DownloadResult(
                item_id=job.id, appid=job.appid,
                status=DownloadStatus.FAILED, message="所有通道均不可用",
            )
        return result

    def _retire_cancelled(self, job: DownloadJob) -> None:
        """A-P1：cancel 已受理的 job 收尾——终态 CANCELLED 且只登记一次。

        cancel() 抢先登记时（job 已被移出 _active）本方法只清 pending
        标记；否则由本方法完成登记与 finished 通知。二者互斥，靠
        `_active` 移出操作原子完成（同一把 _lock）。
        """
        with self._lock:
            self._cancelling.discard(job.id)
            retired_here = job.id in self._active
            if retired_here:
                self._active.pop(job.id, None)
                job.status = JobStatus.CANCELLED
                job.message = job.message or "已取消"
                job.finished_at = time.time()
                self._done.append(job)
            self._cond.notify_all()
        if retired_here and self.on_finished:
            self._fire_finished(job)
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()

    def _exec_job(self, job: DownloadJob) -> None:
        # 需求 1：任务间随机抖动 + 退避等待（在独立线程中执行，不持锁）
        self._throttle_wait(job)

        # A-P1：等待期间被取消 → 直接收尾，不入链（cancel() 通常已登记，
        # 此时仅清 pending 标记；若尚未登记则由本方法补登记）
        if job._stop.is_set():
            self._retire_cancelled(job)
            return

        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        if self.on_started:
            self._fire_started(job)

        # 该游戏的专属下载目录（仅当用户为此游戏配置过时才生效，
        # 否则用引擎默认目录，保持与未配置行为一致）
        install_dir = ""
        try:
            gd = configured_game_dirs().get(str(job.appid))
            if gd:
                install_dir = gd
        except Exception:  # noqa: BLE001
            log.debug("游戏目录解析失败，使用默认目录", exc_info=True)

        # 需求 2：续传。失败/中断时保留 content 目录，重试前报告已有部分内容
        # （steamcmd 重复下载会校验已有内容、只补差异）
        try:
            existing = self.engine.ensure_partial(
                job.id, job.appid, install_dir=install_dir
            )
        except Exception:  # noqa: BLE001
            existing = 0
        if existing > 0:
            job.resumed_bytes = existing
            job.message = f"续传中（已有 {existing / 1048576:.1f} MB）"
            log.info("任务 %s 续传：已有 %d 字节", job.id, existing)
            self._fire_progress(job)

        # 需求 3：每个任务独立的进度平滑器（~10Hz 限流 + 不倒退 + 速度/ETA）
        smoother = ProgressSmoother(min_interval=0.1)
        smoother.reset(job.resumed_bytes)

        # 下载通道：provider 链式回退（1.4.0）。
        # 一条链 = 一次 attempt：链内回退不消耗 auto_retry。
        result = self._run_channel_chain(job, install_dir, smoother)

        job.finished_at = time.time()
        # E③：steamcmd 偶发报 SUCCESS 但实际字节数为 0（限流假成功/内容未落地），
        # 误报成功会让用户以为下载完成。0 字节改判失败，走正常失败/自动重试路径。
        if (result.status == DownloadStatus.SUCCESS
                and result.bytes_done <= 0
                and not job._stop.is_set()):
            log.warning("物品 %s 报 SUCCESS 但 0 字节，改判失败", job.id)
            result = DownloadResult(
                item_id=job.id, appid=job.appid,
                status=DownloadStatus.FAILED,
                message="steamcmd 报告成功但下载内容为空（可能触发限流）",
            )
        # A-P1：cancel 与完成登记竞态的正式收口。
        # cancel() 的 add(_cancelling) + _stop.set() + 移出 _active +
        # 登记 _done 全程持有 _lock；本判定块同样全程持锁，两者严格串行：
        #  - cancel 先行：本 job 已置 CANCELLED 并登记，本路径跳过终态决定、
        #    入库导入与自动重试（取消语义胜出，杜绝「取消后仍成功入库 /
        #    状态被覆盖回成功」的微秒窗口）。
        #  - 本路径先行：终态已在此锁内定下，cancel() 随后拿锁时 _active
        #    已无本 job（或其终态守卫直接 early-return），真实结果不覆盖
        #    （7g/7h 回归点）。
        # queued_retry：自动重试的判定与重新入队都在同一把锁内完成，
        # cancel() 无法插在「判定可重试」与「重新入队」之间把已取消的
        # 任务复活；重试期间状态保持 RUNNING（轮询方不会误判为终态，
        # 7a 回归点），只有重试机会用尽才置 FAILED。
        queued_retry = False
        with self._lock:
            cancelled_pending = job.id in self._cancelling
            self._cancelling.discard(job.id)
            owns_retire = job.id in self._active
            needs_backoff = False
            if cancelled_pending:
                if result.status == DownloadStatus.SUCCESS:
                    log.info("任务 %s 在完成瞬间被取消：保持 CANCELLED，不导入库", job.id)
                job.status = JobStatus.CANCELLED
                job.message = "已取消"
            elif owns_retire:
                if job._stop.is_set() and result.status != DownloadStatus.SUCCESS:
                    job.status = JobStatus.CANCELLED
                    job.message = "已取消"
                elif result.status == DownloadStatus.SUCCESS:
                    job.status = JobStatus.SUCCESS
                    job.bytes_done = result.bytes_done
                    job.message = "下载成功"
                elif (job.attempt < self.auto_retry
                      and not job._stop.is_set()):
                    # 失败但可自动重试：保持 RUNNING，直接原子入队
                    job.attempt += 1
                    job.message = f"重试中({job.attempt})：{result.message}"
                    self._active.pop(job.id, None)
                    self._queue.append(job)
                    self._cond.notify_all()
                    queued_retry = True
                    needs_backoff = True
                else:
                    job.status = JobStatus.FAILED
                    job.message = result.message or "下载失败"
                    needs_backoff = True
            else:
                log.warning("任务 %s 收尾时不在 _active 且非取消，跳过登记", job.id)

        # 失败必记退避（含即将自动重试的失败）：全局退避升级 + 并发降级
        if needs_backoff:
            self._backoff.record_failure(result.message or "failed")
            cur = self._concurrency.on_failure(result.message or "failed")
            log.info("失败退避：并发上限 -> %d（退避等级 %d）", cur, self._backoff.level)

        if queued_retry:
            log.info("任务 %s 自动重试 %s", job.id, job.attempt)
            if self.on_progress:
                self._fire_progress(job)
            return

        if not cancelled_pending and owns_retire:
            if job.status == JobStatus.SUCCESS:
                self._backoff.record_success()          # 成功：退避缓慢回落
                cur = self._concurrency.on_success()    # 持续成功：并发逐步回升
                if cur != self.max_concurrent:
                    log.info("并发回升 -> %d", cur)
                self._register_to_library(job, result)

        # log_job 写 SQLite（可能触发 "database is locked" 等异常）：
        # 若放任异常传播，工作线程会死在 _active 未清理的状态，调度循环
        # 的 `while len(self._active) >= concurrency` 永久挂起，整个队列
        # 假死。历史记录失败不应阻塞状态机流转。
        try:
            self.library.log_job(job.id, job.appid, job.item.title, job.status.value, job.bytes_done, job.message)
        except Exception:  # noqa: BLE001
            log.exception("记录任务历史失败（不影响下载状态机）%s", job.id)
        with self._lock:
            # cancel() 可能已把本 job 从 _active 移出并登记进 _done
            # （取消路径同样 append 到 _done 并 fire finished）；
            # 此时不可重复追加，否则完成列表出现重复行、clear_completed
            # 计数与 retry_all_failed 重试数被夸大
            retired_here = job.id in self._active
            if retired_here:
                self._active.pop(job.id, None)
                self._done.append(job)
            self._cond.notify_all()
        # 仅在本路径完成登记时 fire finished；若 cancel() 已登记并
        # fire 过（job 已移出 _active），重复 fire 会让 GUI 完成列表
        # 收到两次同一条目
        if retired_here and self.on_finished:
            self._fire_finished(job)
        if self.on_queue_changed:
            for cb in list(self.on_queue_changed):
                cb()

    def _on_engine_progress(
        self, job: DownloadJob, smoother: ProgressSmoother, pct: int, done: int, msg: str
    ) -> None:
        """引擎进度回调：经平滑器限流后写入 job，再通知 UI。

        - 10Hz 限流：被丢弃的更新直接返回，不触发 on_progress
        - 字节不倒退：smoother 内部钳制
        - 速度/ETA：写入 job.speed_mbps / job.eta_seconds
        - 完成事件（pct >= 100）强制下发
        """
        snap = smoother.feed(int(done or 0), job.total_bytes, force=bool(pct is not None and pct >= 100))
        if snap is None:
            return
        job.bytes_done = snap["bytes"]
        job.speed_mbps = snap["speed_mbps"]
        job.eta_seconds = snap["eta"]
        if job.resumed_bytes > 0 and snap["percent"] < 100:
            job.message = f"续传中（已有 {job.resumed_bytes / 1048576:.1f} MB）· {snap['label']}"
        elif snap["percent"] < 0:
            # 不确定进度（steamcmd 无逐字节输出）：优先用引擎消息，
            # 它带"已下载 X MB"这类可见的进展信息（bug5）
            job.message = msg or snap["label"]
        else:
            job.message = snap["label"]
        if self.on_progress:
            self._fire_progress(job)

    def _register_to_library(self, job: DownloadJob, result: DownloadResult) -> None:
        """下载成功后登记到 mod 库（需求 2/3：分类检索）。"""
        try:
            it = job.item
            rec = self.library.get(job.id) or ModRecord(
                item_id=job.id, appid=job.appid
            )
            rec.title = rec.title or it.title or f"mod {job.id}"
            rec.appid = job.appid
            rec.description = it.description or rec.description
            rec.creator = it.creator or rec.creator
            rec.file_size = result.bytes_done or it.file_size or rec.file_size
            rec.subscriptions = it.subscriptions or rec.subscriptions
            rec.tags = it.tags or rec.tags
            rec.dependencies = it.dependencies or rec.dependencies
            rec.preview_url = it.preview_url or rec.preview_url
            try:
                gd = configured_game_dirs().get(str(job.appid)) or ""
            except Exception:  # noqa: BLE001
                gd = ""
            rec.local_path = self._normalize_content_path(
                result.path, job.appid, job.id, gd
            )
            rec.installed = True
            rec.enabled = True
            rec.download_time = int(time.time())
            rec.time_updated = it.time_updated
            rec.source = "workshop"
            self.library.upsert(rec)
            self.library.write_metadata_sidecar(rec)
            log.info("已登记 mod %s 到本地库", job.id)
        except Exception:  # noqa: BLE001
            log.exception("登记 mod 到本地库失败 %s", job.id)

    @staticmethod
    def _normalize_content_path(reported_path: str, appid: str, item_id: str,
                                install_dir: str = "") -> str:
        """规范化本地路径为物品内容目录。

        steamcmd 的 Success 行对 legacy 格式 mod（L4D2/KF/Civ 等单文件）
        报告的是 <hcontent>_legacy.bin 文件路径，而非目录；统一回退到
        content/<appid>/<itemid> 目录，保证 isdir 与元数据旁车可用。

        install_dir 为该游戏的专属下载根目录（回退路径拼接用）。
        """
        import os

        if reported_path and os.path.isdir(reported_path):
            return reported_path
        if reported_path and os.path.isfile(reported_path):
            # 文件：取其所在目录（正是内容目录）
            return os.path.dirname(reported_path)
        root = install_dir or "."
        return reported_path or os.path.join(
            root, "steamapps", "workshop", "content", str(appid), str(item_id)
        )
