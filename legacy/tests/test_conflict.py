"""conflict_extractor 单元测试。

覆盖：中文关键词、英文关键词、HTML 链接、BBCode 链接、Markdown 链接、
无链接声明、误报抑制（“不冲突”/“no conflict”/“compatible”）、
自己链接自己、空文本、多冲突混合、本地库对照。

运行：$env:PYTHONUTF8=1; python tests/test_conflict.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.conflict_extractor import (  # noqa: E402
    ConflictInfo,
    check_installed_conflicts,
    extract_conflicts,
)

out_lines: list[str] = []


def p(*a):
    out_lines.append(" ".join(str(x) for x in a))


ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def ids_of(result):
    return [c.mod_id for c in result]


def conf_of(result):
    return [c.confidence for c in result]


# ---------------------------------------------------------------- dataclass
c0 = ConflictInfo("123", "Name", "stmt", "high")
check("dataclass 字段", c0.mod_id == "123" and c0.name == "Name" and c0.statement == "stmt")

# ---------------------------------------------------------- 1. 中文关键词
r = extract_conflicts("本 mod 与 毒蛇重击 mod 冲突，请勿同时使用。")
check("中文关键词：1 条", len(r) == 1, str(r))
check("中文关键词：无链接 → id 为空", r and r[0].mod_id == "", str(ids_of(r)))
check("中文关键词：置信度 medium", r and r[0].confidence == "medium", str(conf_of(r)))
check("中文关键词：名称含 mod 名", r and "毒蛇重击" in r[0].name, str([c.name for c in r]))
check("中文关键词：statement 含原句", r and "冲突" in r[0].statement and "请勿同时使用" in r[0].statement)

# ---------------------------------------------------------- 2. 英文关键词
r = extract_conflicts("This mod is incompatible with ABC Addon. Have fun!")
check("英文关键词：1 条", len(r) == 1, str(r))
check("英文关键词：medium 无 id", r and r[0].mod_id == "" and r[0].confidence == "medium", str(r))
check("英文关键词：名称含 ABC", r and "ABC" in r[0].name, str([c.name for c in r]))

r = extract_conflicts("Mutually exclusive with Another Mod, do not combine with it.")
check("英文短语 mutually exclusive / do not combine", len(r) == 1 and "Another Mod" in r[0].name, str(r))

# ---------------------------------------------------------- 3. HTML 链接
r = extract_conflicts(
    'Conflicts with <a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111222333">'
    "Big Boss Mod</a>"
)
check("HTML 链接：提取 id", r and r[0].mod_id == "111222333", str(ids_of(r)))
check("HTML 链接：链接文本作名称", r and r[0].name == "Big Boss Mod", str([c.name for c in r]))
check("HTML 链接：置信度 high", r and r[0].confidence == "high", str(conf_of(r)))
check("HTML 链接：statement 含原始标记", r and "Big Boss Mod" in r[0].statement and "<a href" in r[0].statement)

r = extract_conflicts(
    '冲突 <a href="https://steamcommunity.com/workshop/filedetails/?id=444555666" '
    'target="_blank"><b>Nasty Stuff</b></a>，请勿同时安装。'
)
check("workshop 路径链接 + 嵌套标签", r and r[0].mod_id == "444555666" and r[0].name == "Nasty Stuff",
      str(r))

# ---------------------------------------------------------- 4. BBCode 链接
r = extract_conflicts(
    "本 mod 不兼容 [url=https://steamcommunity.com/workshop/filedetails/?id=777]Old Mod[/url] ，"
    "请勿同时使用。"
)
check("BBCode 链接：提取 id", r and r[0].mod_id == "777", str(ids_of(r)))
check("BBCode 链接：链接文本作名称", r and r[0].name == "Old Mod", str([c.name for c in r]))
check("BBCode 链接：置信度 high", r and r[0].confidence == "high", str(conf_of(r)))

r = extract_conflicts(
    "请勿同时使用 [url]https://steamcommunity.com/sharedfiles/filedetails/?id=666[/url]"
)
check("BBCode 裸链接 [url]...[/url]", r and r[0].mod_id == "666" and r[0].confidence == "high", str(r))

# ---------------------------------------------------------- 5. Markdown 链接（需求示例）
r = extract_conflicts(
    "Conflict with [Some Mod](steamcommunity.com/sharedfiles/filedetails/?id=123)"
)
check("Markdown 链接：id + 名称 + high",
      r and r[0].mod_id == "123" and r[0].name == "Some Mod" and r[0].confidence == "high", str(r))

# ---------------------------------------------------------- 6. 无链接声明
r = extract_conflicts("不要和 123456789 一起装，会崩档。")
check("无链接声明：id 为空", r and r[0].mod_id == "", str(ids_of(r)))
check("无链接声明：medium", r and r[0].confidence == "medium", str(conf_of(r)))
check("无链接声明：名称含数字 id", r and "123456789" in r[0].name, str([c.name for c in r]))

# ---------------------------------------------------------- 7. 误报抑制
r = extract_conflicts("本 mod 已经优化，与其他 mod 不冲突，请放心使用。")
check("抑制：中文“不冲突”", r == [], str(r))

r = extract_conflicts(
    'No conflict with other mods. <a href="https://steamcommunity.com/sharedfiles/'
    'filedetails/?id=555">Random Mod</a>'
)
check("抑制：英文 no conflict（带链接也跳过）", r == [], str(r))

r = extract_conflicts("This mod is compatible with Everything.")
check("抑制：compatible（不误伤 incompatible）", r == [], str(r))

r = extract_conflicts("与 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=333'>C</a> 搭配推荐")
check("抑制：无关键词的链接不提取", r == [], str(r))

# ---------------------------------------------------------- 8. 自己链接自己
SELF = "123"
desc = (
    "本 mod 与 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=123'>我自己</a> "
    "冲突，也别和 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=999'>那个 mod</a> 一起用"
)
r = extract_conflicts(desc, appid=SELF)
check("自链接排除：只剩其他 id", r and ids_of(r) == ["999"], str(ids_of(r)))
check("自链接排除：仍是 high", r and r[0].confidence == "high" and r[0].name == "那个 mod", str(r))

r = extract_conflicts("冲突 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=123'>x</a>", appid=SELF)
check("自链接排除：仅自己链接 → 降级 medium 且 id 为空",
      r and len(r) == 1 and r[0].mod_id == "" and r[0].confidence == "medium", str(r))

r = extract_conflicts("冲突 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=123'>x</a>")
check("不传 appid 时自链接保留", r and ids_of(r) == ["123"] and r[0].confidence == "high", str(r))

# ---------------------------------------------------------- 9. 空文本
check("空文本", extract_conflicts("") == [])
check("None", extract_conflicts(None) == [])
check("纯空白", extract_conflicts("   \n\t ") == [])

# ---------------------------------------------------------- 10. 多冲突混合
desc = (
    "本 mod 简介：\n"
    '与 <a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111">A Mod</a> '
    "冲突，请勿同时使用。\n"
    "另外不兼容 B Mod。\n"
    "感谢支持！"
)
r = extract_conflicts(desc)
check("多冲突：2 条", len(r) == 2, str(r))
check("多冲突：一条带链接 high，一条无链接 medium",
      r and conf_of(r) == ["high", "medium"], str(conf_of(r)))
check("多冲突：id 与名称正确",
      r and r[0].mod_id == "111" and r[0].name == "A Mod" and "B Mod" in r[1].name, str(r))

# 一句之内混合 HTML + BBCode 两个冲突
r = extract_conflicts(
    '与 <a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111">A</a> 冲突，'
    "不兼容 [url=https://steamcommunity.com/workshop/filedetails/?id=222]B[/url]"
)
check("一句多冲突：两个 id 都提取", r and sorted(ids_of(r)) == ["111", "222"], str(ids_of(r)))
check("一句多冲突：都为 high", r and conf_of(r) == ["high", "high"], str(conf_of(r)))

# 重复链接去重
r = extract_conflicts(
    "冲突：[url=https://steamcommunity.com/sharedfiles/filedetails/?id=555]X[/url] "
    "[url=https://steamcommunity.com/sharedfiles/filedetails/?id=555]X[/url]"
)
check("重复链接去重", len(r) == 1 and r[0].mod_id == "555", str(r))

# ---------------------------------------------------------- 11. 软关键词（覆盖）
r = extract_conflicts(
    "本 mod 覆盖 <a href='https://steamcommunity.com/sharedfiles/filedetails/?id=888'>某些内容</a> 的行为"
)
check("软关键词“覆盖”：提取但 low", r and r[0].mod_id == "888" and r[0].confidence == "low", str(r))

r = extract_conflicts("本 mod 不覆盖任何内容。")
check("软关键词否定“不覆盖”不提取", r == [], str(r))

# ---------------------------------------------------------- 12. 裸链接 / 非工坊链接
r = extract_conflicts("冲突：https://steamcommunity.com/sharedfiles/filedetails/?id=777 请注意")
check("裸链接提取", r and r[0].mod_id == "777" and r[0].confidence == "high", str(r))

r = extract_conflicts("冲突 https://example.com/foo 和 https://steamcommunity.com/profiles/123")
check("非工坊链接不提取", r and len(r) == 1 and r[0].mod_id == "" and r[0].confidence == "medium", str(r))

# ------------------------------------------------------ 13. 本地库对照


class _Rec:
    def __init__(self, item_id, title, installed):
        self.item_id = item_id
        self.title = title
        self.installed = installed


class _FakeLibrary:
    """模拟 ModLibrary 契约：.get(item_id) / .search(keyword=...)，不碰磁盘。"""

    def __init__(self, records):
        self._recs = {str(r.item_id): r for r in records}

    def get(self, item_id):
        return self._recs.get(str(item_id))

    def search(self, keyword="", **kw):
        if not keyword:
            return list(self._recs.values())
        k = keyword.lower()
        return [r for r in self._recs.values() if k in (r.title or "").lower()]


lib = _FakeLibrary(
    [
        _Rec("111222333", "Big Boss Mod", True),
        _Rec("444555666", "Nasty Stuff", False),
        _Rec("300", "[Game] C Mod", True),
    ]
)

conflicts = [
    ConflictInfo("111222333", "Big Boss Mod", "s1", "high"),   # id 命中且已安装
    ConflictInfo("444555666", "Nasty Stuff", "s2", "high"),    # 命中但未安装
    ConflictInfo("", "C Mod", "s3", "medium"),                 # 名称模糊命中已安装
    ConflictInfo("", "完全不存在的东西", "s4", "medium"),       # 无命中
    ConflictInfo("", "a", "s5", "medium"),                     # 名称过短，不匹配
]
installed = check_installed_conflicts(lib, conflicts)
check("本地库对照：返回 2 条已安装", len(installed) == 2, str(installed))
check("本地库对照：id 精确命中",
      installed and installed[0].mod_id == "111222333", str(ids_of(installed)))
check("本地库对照：名称模糊命中（标题含装饰括号）",
      installed and any(c.name == "C Mod" for c in installed), str([c.name for c in installed]))

check("本地库对照：空冲突列表", check_installed_conflicts(lib, []) == [])
check("本地库对照：library 为 None", check_installed_conflicts(None, conflicts) == [])

# 异常库对象不应抛出
class _BadLib:
    def get(self, item_id):
        raise RuntimeError("db locked")

    def search(self, **kw):
        raise RuntimeError("db locked")


check("本地库对照：库异常不抛出", check_installed_conflicts(_BadLib(), conflicts) == [])

# ---------------------------------------------------------- 结果输出
result = "\n".join(out_lines)
print(result)
_out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_conflict_unit.txt")
with open(_out_path, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
