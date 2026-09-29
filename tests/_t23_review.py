"""t23 评审 · gui-tester GUI 视角离线实测（B1-B4 + C）。

对 1.4.0 开发态的 GUI 改动做用户视角验证，为 t23 讨论组提供证据。
环境：QT_QPA_PLATFORM=offscreen + PYTHONUTF8=1 + import 前设 APPDATA。
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_t23_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, bool(ok), extra))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))


from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# offscreen 下 _apply_all 末尾的模态「已保存」对话框无人点击会永久阻塞；
# 桩成空操作（配置写入在对话框之前，不受影响）
_QBOX = QMessageBox.information
QMessageBox.information = staticmethod(lambda *a, **k: None)

from swdm.core.config import ensure_dirs  # noqa: E402
from swdm.core.logger import setup_logger  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

setup_logger("WARNING")
ensure_dirs()
app = QApplication.instance() or QApplication(sys.argv)
win = MainWindow()
win.show()
app.processEvents()

# 桩掉设置应用时的实网/部署副作用（refresh_engine 可能触发 steamcmd 自动部署）
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
app.processEvents()

# ====================================================== B4 通道动态下拉
st = win.settings_tab
combo = st.channel_combo
rows = st._channel_rows
names = [r[0] for r in rows]
texts = [combo.itemText(i) for i in range(combo.count())]
check("B4a 通道下拉按注册表动态生成（≥2 通道）", len(rows) >= 2, str(names))
check("B4b 含 steamcmd 与 cdn 通道", {"steamcmd", "cdn"} <= set(names), str(names))
check("B4c 下拉项是显示名（用户可读）",
      all(t and not t.isdigit() for t in texts), str(texts))
check("B4d 默认选中有效通道",
      combo.currentData() in names, repr(combo.currentData()))
# 选中切换写 config
combo.setCurrentIndex(combo.findData("cdn") if "cdn" in names else 0)
app.processEvents()
st._apply_all()
app.processEvents()
saved = win.svc.config.get("download", "channel", default="")
check("B4e 切换通道写入 config.download.channel",
      saved in names and saved != "", repr(saved))
# tooltip 有回退说明（帮普通用户理解"通道"）
tip = combo.toolTip()
check("B4f 下拉 tooltip 解释了回退与兜底",
      "回退" in tip and ("SteamCMD" in tip or "steamcmd" in tip.lower()), tip[:60])

# ====================================================== B2 调试 Tab 隐藏
# 默认隐藏
tab_names = [win._tabs.tabText(i) for i in range(win._tabs.count())]
check("B2a 默认无调试 Tab", not any("调试" in t for t in tab_names),
      str(tab_names))
check("B2b debug_tab 实例始终存在（排错路径不断）",
      getattr(win, "debug_tab", None) is not None)
# 设置开关存在且默认关
chk = st.debug_panel_check
check("B2c 设置页有调试面板开关", chk is not None)
check("B2d 开关默认关闭", chk.isChecked() is False)
# 打开开关 → Tab 出现（配置生效路径）
chk.setChecked(True)
app.processEvents()
st._apply_all()
app.processEvents()
check("B2e 打开开关后配置写入",
      bool(win.svc.config.get("logging", "show_debug_panel", default=False)))

# ====================================================== B1 暂停/继续合并
dl = win.downloads_tab
btn = dl.pause_all_btn
check("B1a 只有一个暂停/继续按钮（合并后）",
      sum(1 for c in dl.findChildren(type(btn))
          if "暂停" in c.text() or "继续" in c.text()) == 1,
      repr([c.text() for c in dl.findChildren(type(btn))]))
check("B1b 初始文案是「全部暂停」", "暂停" in btn.text(), repr(btn.text()))

# 暂停 → 文案切「全部继续」
dl.mgr.pause_all()
app.processEvents()
dl._sync_batch_buttons()
check("B1c 暂停后按钮切到「全部继续」", "继续" in btn.text(), repr(btn.text()))
# 再点 → 继续
dl._toggle_pause_all()
app.processEvents()
dl._sync_batch_buttons()
check("B1d 继续后按钮切回「全部暂停」", "暂停" in btn.text(), repr(btn.text()))
check("B1e mgr.paused 已复位", getattr(dl.mgr, "paused", False) is False)

# 另三个操作仍是独立按钮
all_btns = [c.text() for c in dl.findChildren(type(btn))]
check("B1f 重试失败/清除已完成仍独立存在",
      any("重试" in t for t in all_btns) and any("清除" in t for t in all_btns),
      str(all_btns))

# ====================================================== B3 搜索间隔 0.7s + 熔断
from swdm.core.game_search import GameSearchClient  # noqa: E402

gsc = GameSearchClient()
check("B3a 最低间隔为 0.7s", abs(gsc._min_interval - 0.7) < 1e-9,
      str(gsc._min_interval))

# 熔断语义：ConnectionError → 冷却 15s
import requests  # noqa: E402

import time as _time  # noqa: E402

gsc._record_failure(requests.ConnectionError("10053"))
_remain = gsc._cooldown_until - _time.time()
check("B3b 连接熔断 → 冷却 15s",
      14.0 <= _remain <= 15.0 and gsc._in_cooldown(),
      f"remain={_remain:.1f}")
# 冷却内 search 直接返回空（不发请求）
gsc._cache.clear()
r = gsc.search("garry")
check("B3c 冷却期内 search 返回空列表", r == [], str(r))

# 冷却过后恢复（时间快进）
gsc._cooldown_until = 0.0
gsc._fail_streak = 0
check("B3d 冷却结束后不再熔断", gsc._in_cooldown() is False)

# 缓存命中（300s）跳过网络
gsc._cache["garry"] = (1e12, [("4000", "Garry's Mod")])
r2 = gsc.search("garry")
check("B3e 缓存命中直接返回（体感即时）",
      len(r2) == 1 and r2[0][0] == "4000", str(r2))

# 本地即时层不受网络间隔影响（t12 联想体感保证）
wt = win.workshop_tab
wt._local_game_matches = lambda t: [("4000", "Garry's Mod")]
ed = wt.game_combo.lineEdit()
ed.setText("gar")
wt._on_search_text_edited("gar")
app.processEvents()
check("B3f 本地联想仍即时出候选（不等待 0.7s）",
      wt.game_combo.count() > 0
      and "Garry's Mod" in wt.game_combo.itemText(0),
      repr(wt.game_combo.itemText(0) if wt.game_combo.count() else ""))

# ====================================================== C 匿名降级链
from swdm.core.providers.registry import get_registry  # noqa: E402
from swdm.core.providers.base import Availability  # noqa: E402

reg = get_registry()
# 需 key 未配置 → is_configured False，链构造跳过
from swdm.core.providers.ggnetwork import GGNetworkProvider  # noqa: E402

prov = reg.get_provider("ggnetwork")
if prov is not None:
    needs_key = GGNetworkProvider.meta.requires_key
    if needs_key:
        # 强制无 key
        prov.config = {"api_key": ""}
        check("C① 需 key 未配置 → is_configured False",
              prov.is_configured() is False)
    else:
        check("C① ggnetwork 匿名可用（requires_key=False）", True)

# 链尾兜底：任意首选失败后 steamcmd 仍在链尾
chain = reg.build_chain(preferred="cdn")
tail = chain[-1].meta.name if chain else ""
check("C② 链尾永远是 steamcmd 兜底", tail == "steamcmd",
      str([c.meta.name for c in chain]))
# 首选 steamcmd（terminal）→ 不重复追加
chain2 = reg.build_chain(preferred="steamcmd")
check("C③ 首选即 terminal 时不重复追加",
      [c.meta.name for c in chain2] == ["steamcmd"],
      str([c.meta.name for c in chain2]))
# 熔断中的通道被跳过
reg._circuits["cdn"].record_failure()
reg._circuits["cdn"].record_failure()
reg._circuits["cdn"].record_failure()
chain3 = reg.build_chain(preferred="cdn")
check("C④ 熔断中的通道被链构造跳过",
      "cdn" not in [c.meta.name for c in chain3],
      str([c.meta.name for c in chain3]))
reg._circuits["cdn"].record_success()

# ====================================================== 结果
fails = [r for r in RESULTS if not r[1]]
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
