"""B3 剪贴板监听入队 + B5 批量粘贴导入 + 搜索冷却自动重发（t35）.

测试策略：
- offscreen 平台 QClipboard.dataChanged 不可靠（平台不触发），因此
  dataChanged 信号链路只做"连接/解绑"断言，解析→去重→入队的语义
  全部直接调用 win._on_clipboard_changed() 并注入 _clipboard_text
  返回值来验证（这条路径与信号触发的路径完全相同）。
- 剪贴板内容不记录/不缓存的硬约束：解析失败后不留下任何状态，
  断言 win 上不存在剪贴板文本缓存属性。
- 托盘态（窗口隐藏时复制链接）行为需人工在真机确认，见
  docs/clipboard_watch_notes.md。
"""
import os
import sys
import tempfile

# 必须在 import swdm 之前设置 APPDATA 临时目录（与 run_all 约定一致）
_APPDATA = tempfile.mkdtemp(prefix="swdm_t35_")
os.environ["APPDATA"] = _APPDATA
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, ".")

_RESULTS: list[str] = []


def check(cond, label):
    _RESULTS.append("[PASS] " + label if cond else "[FAIL] " + label)
    if not cond:
        print("FAIL:", label, flush=True)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from swdm.core.config import get_config
    from swdm.core.steam_api import WorkshopItem
    from swdm.gui.main_window import MainWindow

    cfg = get_config()
    cfg.reset()  # 干净配置：clipboard_watch 默认 True

    win = MainWindow()
    win.show()
    app.processEvents()

    # ------------------------------------------------ 1. 默认开启 + 连接
    check(cfg.get("general", "clipboard_watch", default=None) is True,
          "默认配置 clipboard_watch 为 True")
    check(getattr(win, "_clip_connected", False) is True,
          "启动后 dataChanged 已连接（_clip_connected=True）")

    # -------------------------------------- 2. 工坊链接 → 解析并入队（注入文本）
    _FAKE_ID = "390111022"
    _texts = {
        "clip_url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={_FAKE_ID}",
    }

    def _fake_details(ids):
        # 不触网：返回构造物品（result=1）
        return {i: WorkshopItem(publishedfileid=i, title=f"Item {i}",
                               appid="4000", result=1) for i in ids}

    win.svc.api.get_file_details = _fake_details  # type: ignore[method-assign]
    win._clipboard_text = lambda t=_texts["clip_url"]: t  # type: ignore[method-assign]
    win._on_clipboard_changed()
    snap = win.svc.downloader.snapshot()
    queued_ids = [j.id for j in snap["queued"]] + [j.id for j in snap["active"]]
    check(_FAKE_ID in queued_ids, "工坊链接已解析并入队")
    check(win.statusBar().currentMessage().find("已从剪贴板") >= 0,
          "状态栏非模态提示已显示")

    # --------------------------------------- 3. dataChanged 重复触发 → 去重
    win._on_clipboard_changed()
    snap = win.svc.downloader.snapshot()
    n = sum(1 for j in snap["queued"] + list(snap["active"]) if j.id == _FAKE_ID)
    check(n == 1, "同一链接重复触发只入队一次（队列去重）")

    # --------------------- 4. 非工坊内容静默跳过（不弹模态/不记录/不缓存）
    win._clipboard_text = lambda: "今天天气不错 https://example.com/blog"  # type: ignore[method-assign]
    before = len(win.svc.downloader.snapshot()["queued"])
    try:
        win._on_clipboard_changed()
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        print("exception:", e)
    after = len(win.svc.downloader.snapshot()["queued"])
    check(ok and before == after, "非工坊文本静默跳过、无异常、不入队")
    # 硬约束 2：不缓存剪贴板内容
    clip_attrs = [a for a in vars(win) if "clip" in a.lower()
                  and a != "_clip_connected"]
    cached_text = [a for a in clip_attrs
                   if isinstance(getattr(win, a, None), str)
                   and len(getattr(win, a, "")) > 0]
    check(not cached_text, "未缓存任何剪贴板文本内容（防御性设计）")

    # ----------------------- 5. resolve 失败/详情失败 → 静默不崩
    def _raise(*a, **k):
        raise RuntimeError("network down")

    win.svc.api.get_file_details = _raise  # type: ignore[method-assign]
    win._clipboard_text = lambda: f"https://steamcommunity.com/sharedfiles/filedetails/?id=999111222"  # type: ignore[method-assign]
    try:
        win._on_clipboard_changed()
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    check(ok, "详情请求失败时静默跳过不崩")
    win.svc.api.get_file_details = _fake_details  # type: ignore[method-assign]

    # ------------------------------ 6. 空剪贴板 / 纯空白 → 不调任何 API
    calls = {"n": 0}

    def _counting(ids):
        calls["n"] += 1
        return {}

    win.svc.api.get_file_details = _counting  # type: ignore[method-assign]
    for empty in ("", "   ", "\n\n"):
        win._clipboard_text = lambda t=empty: t  # type: ignore[method-assign]
        win._on_clipboard_changed()
    check(calls["n"] == 0, "空/纯空白剪贴板不发起详情请求")
    win.svc.api.get_file_details = _fake_details  # type: ignore[method-assign]

    # --------------------------- 7. 配置关闭 → 解绑 + 处理器直接 no-op
    cfg.set("general", "clipboard_watch", False)
    win._start_clipboard_watch()
    check(win._clip_connected is False, "配置关闭后 dataChanged 已解绑")
    win._clipboard_text = lambda: f"https://steamcommunity.com/sharedfiles/filedetails/?id=555666777"  # type: ignore[method-assign]
    before = len(win.svc.downloader.snapshot()["queued"])
    win._on_clipboard_changed()
    after = len(win.svc.downloader.snapshot()["queued"])
    check(before == after, "关闭状态下即使信号到达也不入队（处理器内二次判配置）")

    cfg.set("general", "clipboard_watch", True)
    win._start_clipboard_watch()
    check(win._clip_connected is True, "重新开启后即时重连（设置变更即生效）")

    # ------------------------- 8. _is_new_item 对 done/active 判重
    from swdm.core.downloader import DownloadJob

    def _mkjob(i):
        return DownloadJob(item=WorkshopItem(publishedfileid=i), appid="4000")

    _real_snapshot = win.svc.downloader.snapshot
    win.svc.downloader.snapshot = lambda: {  # type: ignore[method-assign]
        "queued": [_mkjob("111")], "active": [_mkjob("222")],
        "done": [_mkjob("333")],
    }
    check(win._is_new_item("111") is False, "_is_new_item 对队列内 id 判重")
    check(win._is_new_item("999") is True, "_is_new_item 对新 id 放行")
    # 恢复真实 snapshot，避免后续下载页刷新拿到假任务
    win.svc.downloader.snapshot = _real_snapshot  # type: ignore[method-assign]

    # ------------------------------------------------ 9. 设置页开关 UI
    from swdm.gui.settings_tab import SettingsTab

    # QMessageBox.information 在 _apply_all 会阻塞 offscreen，打桩
    import PySide6.QtWidgets as _qw

    _qw.QMessageBox.information = staticmethod(lambda *a, **k: None)  # type: ignore[attr-defined]
    # 必须用主窗口已接线的 settings_tab：新建实例的 settings_changed
    # 没有监听者，无法验证即时重连
    st: SettingsTab = win.settings_tab
    st._load_values()
    check(st.clipboard_watch_check.isChecked() is True,
          "设置页开关反映配置值（默认勾选）")
    check(st.clipboard_watch_check.toolTip().find("不记录") >= 0
          or st.clipboard_watch_check.toolTip().find("不缓存") >= 0,
          "开关 tooltip 说明防御性设计")
    st.clipboard_watch_check.setChecked(False)
    st._apply_all()
    check(get_config().get("general", "clipboard_watch") is False,
          "设置页保存写入 general.clipboard_watch")
    check(win._clip_connected is False, "保存后 settings_changed 即时解绑监听")
    st.clipboard_watch_check.setChecked(True)
    st._apply_all()
    check(get_config().get("general", "clipboard_watch") is True
          and win._clip_connected is True, "恢复开启后即时重连")

    # ------------------------------------- 10. resolve_any_url 纯本地语义
    api = win.svc.api
    check(api.resolve_any_url("https://steamcommunity.com/sharedfiles/filedetails/?id=123456")
          == ("", "123456"), "filedetails 链接解析出 id")
    check(api.resolve_any_url("纯数字 789") == ("", "789")
          or api.resolve_any_url("789") == ("", "789"), "纯数字 id 解析")
    check(api.resolve_any_url("hello world") == ("", ""), "普通文本解析为空")
    check(api.resolve_any_url("") == ("", ""), "空文本解析为空")

    # ---------------------------------------- 11. B5 批量粘贴 token 解析
    from swdm.gui.workshop_tab import WorkshopTab

    tab = win.workshop_tab
    # 展开合集与详情都打桩，纯测 token→id 解析与去重
    tab.svc.api.get_collection_details = lambda cid: []  # type: ignore[method-assign]
    tab.svc.api.get_file_details = _fake_details  # type: ignore[method-assign]
    # 链接不带 appid 且当前未选游戏时会弹 AppID 模态框，打桩返回 4000
    _qw.QInputDialog.getText = staticmethod(lambda *a, **k: ("4000", True))  # type: ignore[attr-defined]
    tokens = [
        "https://steamcommunity.com/sharedfiles/filedetails/?id=100000001",
        "https://steamcommunity.com/sharedfiles/filedetails/?id=100000002",
        "100000001",            # 与第一个重复
        "这不是链接",
    ]
    tab._import_tokens(tokens)
    snap = win.svc.downloader.snapshot()
    ids = [j.id for j in snap["queued"] + list(snap["active"])]
    check("100000001" in ids and "100000002" in ids, "B5 两个有效链接均入队")
    check(ids.count("100000001") == 1, "B5 重复 token 去重")
    check("这不是链接" not in ids, "B5 无效 token 被跳过")

    # ------------------------- 12. 搜索冷却自动重发待选词（技术债）
    import swdm.core.game_search as gs

    class _FakeClient:
        def __init__(self):
            self.cooldown = True
            self.remaining = 0.05
            self.searched = []

        def is_in_cooldown(self):
            return self.cooldown

        def cooldown_remaining(self):
            return self.remaining

        def search(self, term):
            self.searched.append(term)
            return []

    fake = _FakeClient()
    tab._search_client = fake
    tab.game_combo.setEditText("garry")
    tab._do_game_search()
    check(tab._pending_search_term == "garry",
          "冷却期内待选词已记录")
    check(tab._search_retry_timer.isActive(),
          "冷却重发定时器已启动")
    # 冷却到期：模拟定时器触发 → 重发
    fake.cooldown = False
    tab._search_retry_timer.setInterval(10)
    tab._search_retry_timer.start()

    def _wait_for_search(timeout_ms=3000):
        """用 QTest.qWait 真正让事件循环跑，等 worker 线程回填 searched。"""
        from PySide6.QtTest import QTest

        for _ in range(max(1, timeout_ms // 100)):
            QTest.qWait(100)
            if fake.searched:
                return True
        return False

    check(_wait_for_search() and "garry" in fake.searched,
          "冷却结束后自动重发同一待选词")
    check(tab._pending_search_term == "", "重发后待选词已清空")

    # 用户改词后旧词不再重发
    fake.searched.clear()
    fake.cooldown = True
    tab.game_combo.setEditText("counter")
    tab._do_game_search()
    tab.game_combo.setEditText("csgo")  # 冷却期间用户继续输入
    fake.cooldown = False
    tab._search_retry_timer.setInterval(10)
    tab._search_retry_timer.start()
    _wait_for_search()
    check("counter" not in fake.searched,
          "用户改词后旧待选词不再重发")

    # _on_search_ready 清待发词
    tab._pending_search_term = "stale"
    tab._search_version += 1
    tab._on_search_ready([], tab._search_version)
    check(tab._pending_search_term == "", "搜索结果到达后待选词清空")

    # GameSearchClient 公开冷却接口存在且语义正确
    client = gs.GameSearchClient()
    check(hasattr(client, "is_in_cooldown") and not client.is_in_cooldown(),
          "GameSearchClient.is_in_cooldown 公开且冷却外返回 False")
    check(client.cooldown_remaining() == 0.0, "cooldown_remaining 冷却外为 0")

    # 收口
    try:
        win.svc.downloader.stop()
    except Exception:  # noqa: BLE001
        pass
    win.close()

    fails = [r for r in _RESULTS if r.startswith("[FAIL]")]
    with open(os.path.join("tests", "_t35_out.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_RESULTS) + "\n")
        f.write(f"\nRESULT: {'ALL PASS' if not fails else 'FAIL ' + str(len(fails))}\n")
    print("\n".join(_RESULTS))
    print(f"RESULT: {'ALL PASS' if not fails else 'FAIL ' + str(len(fails))}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
