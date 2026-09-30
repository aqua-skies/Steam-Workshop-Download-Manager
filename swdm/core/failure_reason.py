"""Item-level failure reason enumeration（C2，t41）。

steamcmd 的 ``I/O Operation Failed`` / ``Failed to download item`` 等输出
**不区分** entitlement（无所有权）/ auth（未登录）/ Steam Guard / 限流 /
网络故障（Valve issue steam-for-linux#13474，t31 评审认定为公认痛点）。
本模块把单次下载失败保守地归一成用户可读的原因桶，并渲染不误导的提示文案。

误报红线（search-fixer + core-tester 一致，t31 决议）：**通用 I/O 失败
绝不映射成「需正版账号」**——误报会让用户以为必须先买游戏，比不报更伤。
只有两条正向信号才提示账号：

1. **受限 App 名单 + 匿名下载未开始**：steamcmd 已登录成功但没有出现任何
   下载行（引擎消息「未开始下载…」），且 appid 在 :data:`RESTRICTED_APPS`
   内（匿名 file_url 为空的等价观测）。
2. **重试用尽后仍同一错误且本次运行无限流/超时信号**：所有 attempt 的失败
   message 完全相同，且本次运行没有观察到 rate_limit / timeout 特征。

与熔断器正交：熔断器管「通道健康度」（连续失败 → 冷却跳过整个通道），
本模块管「单个物品的可读结论」，纯函数、不触碰注册表或任何全局状态。
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Sequence


class FailureBucket(str, Enum):
    """失败原因桶（用户可读分类）。GENERIC 是兜底，绝不暗示账号。"""

    GENERIC = "generic"             # 通用 I/O 失败（红线：不区分权限/网络/限流）
    ACCOUNT_NEEDED = "account"      # 受限 App，正向信号支持
    ITEM_GONE = "item_gone"         # 物品不存在/已下架
    RATE_LIMITED = "rate_limited"   # 触发限流
    NETWORK = "network"             # 超时/无法连接
    DISK_FULL = "disk_full"         # 磁盘空间不足
    LOGIN_FAILED = "login_failed"   # 账号 provider 登录失败（凭据，非所有权）
    EMPTY_SUCCESS = "empty_success" # 报 SUCCESS 但 0 字节（E③）


# 已知「受限应用」——匿名账号无法下载其工坊物品（需用户自有账号）。
# 依据 research/bypass_ownership_research_1.4.1.md。新证据出现时在此扩展；
# t32（C5）未观测到第三方代理能绕过，故仍以 steamcmd 侧判定为准。
RESTRICTED_APPS: frozenset[str] = frozenset({
    "221100",   # DayZ
    "602960",   # Barotrauma
})

_HARD_SIGNALS = frozenset({"rate_limit", "timeout"})


def classify_failure(
    message: str,
    *,
    appid: str = "",
    signals: Iterable[str] = (),
    attempt_messages: Sequence[str] = (),
    restricted_apps: frozenset[str] = RESTRICTED_APPS,
) -> FailureBucket:
    """把一次下载失败归入 :class:`FailureBucket`（保守策略，误报优先避免）。

    - ``message``：引擎/通道给出的原始失败文案（蒸汽命令原始错误串亦可）。
    - ``signals``：本次运行观察到的 steamcmd 特征（rate_limit/timeout/retry）。
    - ``attempt_messages``：本任务历次 attempt 的失败文案（含本次），用于
      「重试后仍同错」判定。
    """
    msg = (message or "").strip()
    low = msg.lower()
    sigs = set(signals or ())

    # 1. 磁盘满（明确可操作，优先级最高）
    if "no space left" in low or "磁盘空间不足" in msg or "not enough space" in low:
        return FailureBucket.DISK_FULL
    # 2. 假成功（0 字节，E③）——本程序自产的确定性消息，优先于限流字样判定
    if "下载内容为空" in msg or "内容为空" in msg:
        return FailureBucket.EMPTY_SUCCESS
    # 3. 限流（本次运行有信号，或消息自带限流字样）
    if "rate_limit" in sigs or "限流" in msg or "rate limit" in low or "ratelimit" in low:
        return FailureBucket.RATE_LIMITED
    # 4. 网络/超时
    if "timeout" in sigs or "超时" in msg or "timeout" in low or "timed out" in low:
        return FailureBucket.NETWORK
    # 5. 账号 provider 登录失败（凭据问题，与「需正版账号」严格区分）
    if msg.startswith("登录失败") or "steam guard" in low or "invalid password" in low:
        return FailureBucket.LOGIN_FAILED
    # 6. 物品不存在/已下架
    if ("物品不存在" in msg or "下架" in msg
            or "does not exist" in low or "result=9" in low):
        return FailureBucket.ITEM_GONE
    # 7. 账号正向信号 ①：受限 App + 匿名下载未开始（登录成功但无下载行）
    if "未开始下载" in msg and str(appid or "").strip() in restricted_apps:
        return FailureBucket.ACCOUNT_NEEDED
    # 8. 账号正向信号 ②：重试后仍同一错误且本次无网络信号
    if (len(attempt_messages) >= 2
            and len(set(m.strip() for m in attempt_messages if m)) == 1
            and not (sigs & _HARD_SIGNALS)):
        return FailureBucket.ACCOUNT_NEEDED
    # 9. 兜底：通用 I/O —— 红线，绝不映射成账号
    return FailureBucket.GENERIC


def render_failure(bucket: FailureBucket, raw: str = "") -> str:
    """把桶渲染成用户可读、不误导的提示文案（含登录引导但不承诺因果）。"""

    if bucket == FailureBucket.ACCOUNT_NEEDED:
        return (
            "该游戏可能需要正版 Steam 账号才能下载（受限应用）。"
            "可在「设置 → 账号」登录 Steam 账号后重试；"
            "若你已拥有该游戏，失败原因可能并非权限问题——详见日志。"
        )
    if bucket == FailureBucket.ITEM_GONE:
        return "物品不存在或已从 Steam 工坊下架。"
    if bucket == FailureBucket.RATE_LIMITED:
        return "触发 Steam 限流，请稍后重试。"
    if bucket == FailureBucket.NETWORK:
        return "网络超时或无法连接 Steam 服务器，请检查网络后重试。"
    if bucket == FailureBucket.DISK_FULL:
        return "磁盘空间不足，请清理后重试。"
    if bucket == FailureBucket.LOGIN_FAILED:
        # 引擎已有完善的登录失败文案，原样透出
        return raw or "登录失败（可能是账号/密码错误，或触发 Steam Guard）"
    if bucket == FailureBucket.EMPTY_SUCCESS:
        return raw or "下载内容为空"
    # GENERIC：明确告知「未区分原因」，不给用户错误归因
    return "下载失败：steamcmd 未区分权限/网络/限流等原因，建议重试。详见日志。"
