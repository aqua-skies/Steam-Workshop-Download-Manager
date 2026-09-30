#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""t38 C3 私人账户 provider 测试：合规分层 / 默认链不含 / 凭据不落日志不随导出泄漏 /
账号失败与熔断解耦 / Steam Guard 首登入口。

脚本式：check(name, cond, extra) + RESULT: ALL PASS。
环境与既有测试一致：import swdm 前设 APPDATA 临时目录、offscreen Qt。
"""
from __future__ import annotations

import os
import sys
import tempfile

# ---- 环境前置（必须在 import swdm 前）
_APPDATA = tempfile.mkdtemp(prefix="swdm_c3_")
os.environ["APPDATA"] = _APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, extra: str = "") -> None:
    ok = bool(cond)
    _RESULTS.append((name, ok, str(extra)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}")


from swdm.core.providers import (  # noqa: E402
    Availability,
    ProviderKind,
    ProviderMeta,
    get_registry,
)
from swdm.core.providers.account_steamcmd import (  # noqa: E402
    AccountSteamCMDProvider,
    get_auth_manager,
    reset_auth_state,
    set_auth_manager,
)
from swdm.core.providers.registry import _Circuit  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus, SteamCMDEngine  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.downloader import DownloadJob, DownloadManager  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.logger import snapshot as log_snapshot  # noqa: E402
from swdm.core.auth import AuthManager  # noqa: E402


def _item(item_id="12345", appid="4000"):
    return WorkshopItem(publishedfileid=item_id, appid=appid, title="t")


def _fail(msg="fail"):
    return DownloadResult(item_id="12345", appid="4000",
                          status=DownloadStatus.FAILED, message=msg)


def _ok():
    return DownloadResult(item_id="12345", appid="4000",
                          status=DownloadStatus.SUCCESS, message="ok")


class _FakeAuth:
    """假 AuthManager：可控登录态与凭据。"""

    def __init__(self, anon=True, creds=("", "", "")):
        self._anon = anon
        self._creds = creds

    def is_anonymous(self):
        return self._anon

    def get_credentials(self):
        return self._creds


class _FakeEngine:
    """假 SteamCMDEngine：按预设结果返回。"""

    def __init__(self, results=None, install_dir="C:/swdm_test_install"):
        self.results = list(results or [])
        self.calls = []
        self.on_throttle_signal: list = []
        self.install_dir = install_dir
        self.exe_path = ""
        self.anonymous = True
        self.username = ""
        self.password = ""
        self.guard_code = ""
        self.validate = False
        self.stall_timeout = 60.0
        self.min_bytes_per_sec = 200_000.0

    def download_item(self, **kw):
        self.calls.append(kw)
        if not self.results:
            return _ok()
        r = self.results.pop(0)
        return r() if callable(r) else r


# ==================== 0. 元数据与合规分层 ====================
def test_meta():
    reg = get_registry()
    names = list(reg._classes.keys())
    check("注册表包含 account_steamcmd", "account_steamcmd" in names, str(names))

    m = AccountSteamCMDProvider.meta
    check("C3 标记 supports_account=True", m.supports_account is True)
    check("非链尾 terminal=False", m.terminal is False)
    check("breaker_exempt=True（风控③）", m.breaker_exempt is True)
    check("anonymous_ok=False（必须登录）", m.anonymous_ok is False)
    check("kind 为 ENGINE", m.kind == ProviderKind.ENGINE)

    # 结构性安全属性：兜底 steamcmd 恒不用账号
    from swdm.core.providers.steamcmd import SteamCMDProvider

    check("兜底 steamcmd supports_account=False",
          SteamCMDProvider.meta.supports_account is False)
    check("兜底 steamcmd terminal=True（链尾恒在）",
          SteamCMDProvider.meta.terminal is True)

    # 默认值：老通道 meta 不受影响
    from swdm.core.providers.cdn import CDNProvider

    check("CDN supports_account 默认 False", CDNProvider.meta.supports_account is False)
    check("ProviderMeta supports_account 默认 False",
          ProviderMeta(name="x", display_name="X", kind=ProviderKind.HTTP)
          .supports_account is False)


# ==================== 1. 默认链不含（t38 硬性断言） ====================
def test_default_chain_excludes():
    set_auth_manager(None)
    reg = get_registry()
    # 匿名态：无论首选是谁，链里都不能出现 account_steamcmd
    for pref in ("steamcmd", "", "cdn", "ggnetwork"):
        chain = reg.build_chain(pref)
        names = [p.meta.name for p in chain]
        check(f"默认链(首选={pref!r})不含 account_steamcmd",
              "account_steamcmd" not in names, str(names))
    chain = reg.build_chain("steamcmd")
    names = [p.meta.name for p in chain]
    check("匿名态链尾是 steamcmd", names and names[-1] == "steamcmd", str(names))

    # list_channels 展示层：匿名态标 NO_KEY
    rows = reg.list_channels()
    row = next((r for r in rows if r[0] == "account_steamcmd"), None)
    check("通道列表含 account_steamcmd", row is not None)
    if row:
        check("匿名态 availability=NO_KEY", row[2] == Availability.NO_KEY, str(row[2]))


# ==================== 2. 登录后链含私人账号通道 ====================
def test_chain_includes_when_logged_in():
    reg = get_registry()
    set_auth_manager(_FakeAuth(anon=False, creds=("tester", "pw123", "")))
    try:
        prov = reg.get_provider("account_steamcmd")
        check("登录态 is_configured=True", prov.is_configured() is True)
        # engine 由 manager 注入后 probe 才 OK（链构造不依赖 probe）
        prov.set_engine(_FakeEngine([_ok()]))
        check("登录态 probe=OK", prov.probe() == Availability.OK, str(prov.probe()))

        # 首选=account_steamcmd：链含它且兜底仍在
        chain = reg.build_chain("account_steamcmd")
        names = [p.meta.name for p in chain]
        check("首选 account_steamcmd 时链首即账号通道", names[:1] == ["account_steamcmd"], str(names))
        check("首选 account_steamcmd 时链尾仍是 steamcmd",
              "steamcmd" in names and names[-1] == "steamcmd", str(names))

        # 首选=其他通道时，账号通道按 priority=90 自然扩展进链（兜底之前）
        chain = reg.build_chain("ggnetwork")
        names = [p.meta.name for p in chain]
        check("登录态链含 account_steamcmd", "account_steamcmd" in names, str(names))
        check("account_steamcmd 排在 steamcmd 之前（低风险层自然扩展）",
              "account_steamcmd" in names and "steamcmd" in names and
              names.index("account_steamcmd") < names.index("steamcmd"), str(names))
    finally:
        set_auth_manager(None)


# ==================== 3. 凭据不落日志（风控①） ====================
def test_no_credentials_in_logs():
    set_auth_manager(None)
    # 3a) 引擎级过滤：含账号名/密码/验证码的输出行必须被替换
    eng = SteamCMDEngine(anonymous=False, username="myuser01",
                         password="pw12345", guard_code="X7Y8Z")
    check("用户名被替换", "myuser01" not in eng._redact_secrets("Connecting to Steam as myuser01"))
    check("密码被替换", "pw12345" not in eng._redact_secrets("some pw12345 here"))
    check("验证码被替换", "X7Y8Z" not in eng._redact_secrets("guard X7Y8Z ok"))
    line_out = eng._redact_secrets("Connecting to Steam as myuser01 done")
    check("替换后含占位符", "***" in line_out, line_out)
    # 匿名引擎无密钥，原样返回（保证性能与匿名路径零行为变化）
    anon = SteamCMDEngine(anonymous=True)
    check("匿名引擎不过滤", anon._redact_secrets("plain line") == "plain line")

    # 3b) 端到端：_run 的 on_line 回调拿到的行已脱敏
    seen = []
    eng2 = SteamCMDEngine(anonymous=False, username="leo99",
                          password="secretPW", guard_code="G42")
    orig_run = SteamCMDEngine._run

    def fake_run(self, commands, on_line=None, feed_stdin="", install_dir=""):
        on_line("logging in as leo99 ...")
        on_line("Login Failure: Invalid Password secretPW")
        return 0

    SteamCMDEngine._run = fake_run
    try:
        eng2.test_login()
    finally:
        SteamCMDEngine._run = orig_run
    # test_login 的错误串来自 _FAIL_RE 匹配行，行已脱敏
    # 3c) 日志缓冲与订阅里不得出现明文凭据
    leak = [e for e in log_snapshot()
            if "secretPW" in e.get("message", "") or "leo99" in e.get("message", "")]
    check("日志环形缓冲无明文密码/用户名", not leak,
          str([e.get("message") for e in leak[:3]]))

    # 3d) auth.login_user 的日志不得含用户名
    am = AuthManager()
    snap_before = len(log_snapshot())
    am.login_user("mrlogintest", "pwXYZ", remember=False)
    msgs = [e.get("message", "") for e in log_snapshot()[snap_before:]]
    leaked = [m for m in msgs if "mrlogintest" in m or "pwXYZ" in m]
    check("login_user 日志不含账号名/密码", not leaked, str(leaked[:3]))
    am.logout()


# ==================== 4. 凭据不随导出包泄漏（风控④） ====================
def test_no_credentials_in_persistent_files():
    am = AuthManager()
    am.login_user("poolexport", "pwEXPORT", remember=True)
    # auth.json 不得含明文密码
    import json

    auth_path = os.path.join(_APPDATA, "SWDM", "auth.json")
    ok_no_pw = True
    txt = ""
    if os.path.exists(auth_path):
        txt = open(auth_path, "r", encoding="utf-8").read()
        ok_no_pw = "pwEXPORT" not in txt
    check("auth.json 无明文密码", ok_no_pw, txt[:120])
    d = json.loads(txt) if txt else {}
    check("auth.json 只有 has_password 标志", d.get("has_password") in (True, False))
    # 回退文件若存在必须非明文（base64 混淆）
    cred_path = os.path.join(_APPDATA, "SWDM", ".cred")
    if os.path.exists(cred_path):
        raw = open(cred_path, "rb").read()
        check("回退 .cred 非明文", b"pwEXPORT" not in raw, str(raw[:30]))
    am.clear_stored()
    am.logout()

    # 导出语义自检：mod 记录序列化默认不含任何凭据字段
    from swdm.core.mod_library import ModRecord

    rec = ModRecord(item_id="1", appid="4000", title="t")
    d = rec.to_dict()
    check("ModRecord 导出无任何凭据字段",
          not any(k in d for k in ("password", "username", "guard", "api_key")), str(d))


# ==================== 5. 账号失败与熔断解耦（风控③） ====================
def test_auth_failure_decoupled_from_breaker():
    set_auth_manager(_FakeAuth(anon=False, creds=("decouptest", "pw", "")))
    reg = get_registry()
    reg.record_success("account_steamcmd")

    acct = reg.get_provider("account_steamcmd")   # 用注册表缓存的实例，失活对 build_chain 可见
    ok_engine = _FakeEngine([_ok()])
    acct.set_engine(ok_engine)  # 借配置；下载走 get_engine() 的账号引擎
    # 替身 get_engine：返回持续登录失败的假账号引擎
    acct.get_engine = lambda: _FakeEngine([_fail("登录失败（可能是账号/密码错误，或触发 Steam Guard）")])

    from swdm.core.providers.steamcmd import SteamCMDProvider

    tail = SteamCMDProvider({})
    tail.set_engine(_FakeEngine([_ok()]))

    lib = ModLibrary()
    mgr = DownloadManager(_FakeEngine([_ok()]), lib, auto_retry=0)
    from swdm.core.throttle import ProgressSmoother

    sm = ProgressSmoother(min_interval=0.1)
    dest = os.path.join(_APPDATA, "c3_decouple")

    for i in range(3):
        job = DownloadJob(item=_item(), appid="4000")
        mgr._build_channel_chain = lambda pref: [acct, tail]
        res = mgr._run_channel_chain(job, dest, sm)
        check(f"账号失败后链回退成功 [{i}]", res.status == DownloadStatus.SUCCESS,
              res.message[:60])

    circ = reg._circuits.get("account_steamcmd")
    check("账号通道 3 次失败后未熔断（breaker_exempt）",
          circ is not None and circ.is_tripped() is False)
    check("账号通道一次失败后会话级失活", acct._auth_dead is True)
    # 失活后 is_configured 降为 False → build_chain 跳过它
    check("失活后 is_configured=False", acct.is_configured() is False)
    names = [p.meta.name for p in reg.build_chain("account_steamcmd")]
    check("失活后链自动回退到匿名兜底（不含账号通道）",
          "account_steamcmd" not in names and "steamcmd" in names, str(names))
    # reset_auth_state（用户改了凭据）应重开
    reset_auth_state()
    check("reset_auth_state 重开会话级失活", acct._auth_dead is False)
    set_auth_manager(None)


# ==================== 6. 下载路径接入：串行锁与专属引擎 ====================
def test_download_uses_dedicated_engine():
    set_auth_manager(_FakeAuth(anon=False, creds=("ded1", "pw", "G9")))
    acct = AccountSteamCMDProvider({})
    shared = _FakeEngine([_ok()])
    acct.set_engine(shared)

    captured = {}
    real_engine = acct.get_engine()
    check("get_engine 返回专属引擎（非共享引擎）", real_engine is not shared)
    check("专属引擎携带账号", real_engine.username == "ded1")
    check("专属引擎 anonymous=False", real_engine.anonymous is False)
    check("专属引擎 install_dir 沿用共享引擎",
          real_engine.install_dir == shared.install_dir)

    # 凭据变化 → 自动重建（签名校验）
    set_auth_manager(_FakeAuth(anon=False, creds=("ded1", "pw2", "G9")))
    eng2 = acct.get_engine()
    check("凭据变化后引擎重建（新密码生效）", eng2.password == "pw2")
    check("引擎实例被缓存（同凭据不重建）", acct.get_engine() is eng2)

    # download 路径：走 manager 串行锁（_run_steamcmd 用 get_engine 返回的引擎）
    ok_eng = _FakeEngine([_ok()])
    acct.get_engine = lambda: ok_eng
    from swdm.core.providers.steamcmd import SteamCMDProvider

    fake_shared = _FakeEngine([_fail("共享引擎不该被调用")])
    tail = SteamCMDProvider({})
    tail.set_engine(fake_shared)

    lib = ModLibrary()
    mgr = DownloadManager(fake_shared, lib, auto_retry=0)
    from swdm.core.throttle import ProgressSmoother

    sm = ProgressSmoother(min_interval=0.1)
    job = DownloadJob(item=_item(), appid="4000")
    mgr._build_channel_chain = lambda pref: [acct]
    res = mgr._run_channel_chain(job, os.path.join(_APPDATA, "c3_eng"), sm)
    check("账号通道下载成功", res.status == DownloadStatus.SUCCESS)
    check("用的是账号专属引擎", len(ok_eng.calls) == 1 and not fake_shared.calls)
    # 下载成功不熔断
    reg = get_registry()
    circ = reg._circuits.get("account_steamcmd")
    check("成功重置熔断计数", circ is not None and circ.is_tripped() is False)
    set_auth_manager(None)


# ==================== 7. should_fallback 安全属性 ====================
def test_always_fallback():
    set_auth_manager(_FakeAuth(anon=False, creds=("fb", "pw", "")))
    acct = AccountSteamCMDProvider({})
    for r in (_fail("登录失败"), _fail("任意错误"),
              DownloadResult(item_id="1", appid="4000",
                             status=DownloadStatus.CANCELLED)):
        check(f"失败/取消一律允许回退 {r.status.value}",
              acct.should_fallback(r) is True)
    set_auth_manager(None)


# ==================== 8. GUI：Guard 首登入口 + 本地存储明示 + 测试引擎工厂 ======
def test_gui_guard_flow():
    from swdm.gui.main_window import MainWindow
    from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

    app = QApplication.instance() or QApplication(sys.argv[:1])
    # 对话框打补丁（与既有套件同协议）
    QInputDialog.getText = staticmethod(lambda *a, **k: ("G7G7G7", True))
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)

    win = MainWindow()
    st = win.settings_tab

    # 风控②：验证码输入控件存在且提示文案明确
    check("验证码输入框存在", st.guard_edit is not None)
    ph = st.guard_edit.placeholderText()
    check("验证码占位提示含 Steam Guard", "Steam Guard" in ph, ph)

    # 风控④：本地存储等级明示
    priv = st.privacy_label.text()
    check("隐私明示含『仅本地存储』", "仅本地存储" in priv, priv[:40])
    check("隐私明示含『仅本人使用』", "仅本人使用" in priv)

    # 匿名态：登录测试工厂返回共享引擎
    check("匿名态登录测试用共享引擎", st._login_engine_factory() is win.svc.engine)

    # 登录态：工厂返回专属账号引擎（不污染共享引擎）
    win.svc.auth.login_user("guitester", "guipw", remember=False)
    try:
        eng = st._login_engine_factory()
        check("登录态测试引擎携带账号", eng.username == "guitester")
        check("登录态测试引擎 anonymous=False", eng.anonymous is False)
        check("共享引擎仍保持匿名", win.svc.engine.anonymous is True)
        check("共享引擎无账号凭据", not win.svc.engine.username)
    finally:
        win.svc.auth.logout()

    # Guard 重试入口：模拟一次 Guard 型失败 → 应触发验证码保存路径（打桩协议下不阻塞）
    st.auth = win.svc.auth  # 真实 auth（匿名态），_apply_account 走匿名分支
    before = st.guard_edit.text()
    called = {"apply": 0, "test": 0}
    st._apply_account = lambda: called.__setitem__("apply", called["apply"] + 1)
    st._test_login = lambda: called.__setitem__("test", called["test"] + 1)
    st.test_login_btn.setEnabled(True)
    st._on_login_result(False, "登录失败：未收到成功标志（可能需要 Steam Guard 或触发速率限制）")
    app.processEvents()
    check("Guard 失败后写入验证码输入框", st.guard_edit.text() == "G7G7G7",
          st.guard_edit.text())
    check("Guard 失败后保存并重测", called["apply"] == 1 and called["test"] == 1,
          str(called))
    st.guard_edit.setText(before)

    # 非 Guard 失败不触发验证码弹窗
    st._on_login_result(False, "登录失败：Invalid Password")
    check("非 Guard 失败不写验证码", st.guard_edit.text() == "")

    # 账号明示标签存在（匿名态默认文案）
    check("登录状态标签存在", st.login_status is not None)


# ==================== 9. 主窗口状态栏与通道下落在账号态不崩 ====================
def test_main_window_account_mode_smoke():
    from swdm.gui.main_window import MainWindow
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    win = MainWindow()
    win.svc.auth.login_user("statususer", "pw", remember=False)
    try:
        win._refresh_status_bar()
        txt = win.status_label.text()
        check("状态栏显示登录账号名", "statususer" in txt, txt[:60])
        # 登录态下通道下拉包含账号通道且可用
        st = win.settings_tab
        st._refresh_channel_combo()
        labels = [st.channel_combo.itemText(i) for i in range(st.channel_combo.count())]
        has_acct = any("私人账号" in l for l in labels)
        check("通道下拉列出了私人账号通道（登录态）", has_acct, str(labels))
        # 且不标 NO_KEY（已配置）
        import re

        idx = next((i for i, l in enumerate(labels) if "私人账号" in l), -1)
        nokey = "未配置" in (labels[idx] if idx >= 0 else "")
        check("登录态私人账号通道标为可用（非未配置）", idx >= 0 and not nokey, labels[idx] if idx >= 0 else "")
        _ = re  # silence
    finally:
        win.svc.auth.logout()
        win.svc.refresh_engine()


# ==================== 10. 综合链路：匿名默认行为零变化 ====================
def test_anonymous_baseline_unchanged():
    set_auth_manager(None)
    reg = get_registry()
    chain = reg.build_chain("steamcmd")
    names = [p.meta.name for p in chain]
    check("匿名默认链 == [steamcmd]", names == ["steamcmd"], str(names))
    tail = chain[-1]
    check("链尾 terminal 兜底 anonymous_ok", tail.meta.anonymous_ok is True)
    check("链尾 supports_account=False（兜底永不依赖账号）",
          tail.meta.supports_account is False)


def main() -> int:
    for fn in (test_meta, test_default_chain_excludes, test_chain_includes_when_logged_in,
               test_no_credentials_in_logs, test_no_credentials_in_persistent_files,
               test_auth_failure_decoupled_from_breaker, test_download_uses_dedicated_engine,
               test_always_fallback, test_gui_guard_flow,
               test_main_window_account_mode_smoke, test_anonymous_baseline_unchanged):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            check(f"{fn.__name__} 未抛异常", False, f"{type(e).__name__}: {e}")
    bad = [r for r in _RESULTS if not r[1]]
    print(f"\n总计 {len(_RESULTS)} 项，失败 {len(bad)} 项")
    for n, _, extra in bad:
        print(f"  FAIL: {n} {extra}")
    print("RESULT:", "ALL PASS" if not bad else f"FAIL ({len(bad)})")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
