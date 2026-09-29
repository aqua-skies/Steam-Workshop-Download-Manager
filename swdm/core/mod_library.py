"""Local mod library: SQLite storage with categorization, search, enable/disable and favorites (本地 mod 库).

Design goal (requirement 2): downloaded mods must be easy to categorize and search.
- Each record is keyed by publishedfileid (globally unique) plus appid (game)
- Multi-dimensional search by game / tag / category / status / keyword
- Disk layout: <library>/<game_name>/steamapps/workshop/content/<appid>/<item_id>/
- A metadata JSON sits next to the content, enabling offline search and migration
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from .games import game_name
from .logger import get_logger
from .paths import DB_FILE, ensure_dirs

log = get_logger("swdm.library")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mods (
    item_id TEXT PRIMARY KEY,
    appid TEXT NOT NULL,
    title TEXT,
    description TEXT,
    creator TEXT,
    creator_name TEXT,
    file_size INTEGER DEFAULT 0,
    subscriptions INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    preview_url TEXT,
    local_path TEXT,
    installed INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    category TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    favorite INTEGER DEFAULT 0,
    download_time INTEGER DEFAULT 0,
    time_updated INTEGER DEFAULT 0,
    source TEXT DEFAULT 'workshop',
    dependencies TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_mods_appid ON mods(appid);
CREATE INDEX IF NOT EXISTS idx_mods_category ON mods(category);
CREATE INDEX IF NOT EXISTS idx_mods_title ON mods(title);

CREATE TABLE IF NOT EXISTS jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT,
    appid TEXT,
    title TEXT,
    status TEXT,
    bytes_done INTEGER DEFAULT 0,
    message TEXT,
    created INTEGER
);
CREATE INDEX IF NOT EXISTS idx_jobs_item ON jobs(item_id);
"""

# 旧库迁移：为 mods 表补充 dependencies 列
_MIGRATIONS = [
    "ALTER TABLE mods ADD COLUMN dependencies TEXT DEFAULT '[]'",
]


@dataclass
class ModRecord:
    """One library row: workshop metadata plus local state (本地 mod 记录)."""

    item_id: str
    appid: str
    title: str = ""
    description: str = ""
    creator: str = ""
    creator_name: str = ""
    file_size: int = 0
    subscriptions: int = 0
    tags: list[str] = field(default_factory=list)
    preview_url: str = ""
    local_path: str = ""
    installed: bool = False
    enabled: bool = True
    category: str = ""
    notes: str = ""
    favorite: bool = False
    download_time: int = 0
    time_updated: int = 0
    source: str = "workshop"
    dependencies: list[str] = field(default_factory=list)   # 前置依赖 mod id

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ModRecord":
        return cls(
            item_id=str(row["item_id"]),
            appid=str(row["appid"]),
            title=row["title"] or "",
            description=row["description"] or "",
            creator=row["creator"] or "",
            creator_name=row["creator_name"] or "",
            file_size=int(row["file_size"] or 0),
            subscriptions=int(row["subscriptions"] or 0),
            tags=json.loads(row["tags"] or "[]"),
            preview_url=row["preview_url"] or "",
            local_path=row["local_path"] or "",
            installed=bool(row["installed"]),
            enabled=bool(row["enabled"]),
            category=row["category"] or "",
            notes=row["notes"] or "",
            favorite=bool(row["favorite"]),
            download_time=int(row["download_time"] or 0),
            time_updated=int(row["time_updated"] or 0),
            source=row["source"] or "workshop",
            dependencies=json.loads(row["dependencies"] or "[]") if "dependencies" in row.keys() else [],
        )

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "appid": self.appid,
            "title": self.title,
            "description": self.description,
            "creator": self.creator,
            "creator_name": self.creator_name,
            "file_size": self.file_size,
            "subscriptions": self.subscriptions,
            "tags": self.tags,
            "preview_url": self.preview_url,
            "local_path": self.local_path,
            "installed": self.installed,
            "enabled": self.enabled,
            "category": self.category,
            "notes": self.notes,
            "favorite": self.favorite,
            "download_time": self.download_time,
            "time_updated": self.time_updated,
            "source": self.source,
            "dependencies": self.dependencies,
        }


class ModLibrary:
    """mod 库的数据库访问层（线程安全）。"""

    def __init__(self, db_path: str = DB_FILE) -> None:
        ensure_dirs()
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        # timeout=30s：多实例/多线程共用同一 DB 文件时，SQLite 默认 5s
        # 锁超时在并发写场景下易抛 "database is locked"（t4-P2 / t9 议题 F）
        c = sqlite3.connect(self._db_path, timeout=30.0)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(_SCHEMA)
            # 兼容旧库：补列（已存在则跳过）
            for sql in _MIGRATIONS:
                try:
                    c.execute(sql)
                except sqlite3.OperationalError:
                    pass
            c.commit()

    # ------------------------------------------------------------- 增删改
    def upsert(self, rec: ModRecord) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO mods (item_id, appid, title, description, creator, creator_name,
                       file_size, subscriptions, tags, preview_url, local_path, installed,
                       enabled, category, notes, favorite, download_time, time_updated, source,
                       dependencies)
                   VALUES (:item_id,:appid,:title,:description,:creator,:creator_name,
                       :file_size,:subscriptions,:tags,:preview_url,:local_path,:installed,
                       :enabled,:category,:notes,:favorite,:download_time,:time_updated,:source,
                       :dependencies)
                   ON CONFLICT(item_id) DO UPDATE SET
                       appid=excluded.appid, title=excluded.title, description=excluded.description,
                       creator=excluded.creator, creator_name=excluded.creator_name,
                       file_size=excluded.file_size, subscriptions=excluded.subscriptions,
                       tags=excluded.tags, preview_url=excluded.preview_url,
                       local_path=excluded.local_path, installed=excluded.installed,
                       enabled=excluded.enabled, download_time=excluded.download_time,
                       time_updated=excluded.time_updated, dependencies=excluded.dependencies
                   -- category/notes/favorite 为用户元数据，重新下载时保留原值，不覆盖""",
                {
                    **rec.to_dict(),
                    "tags": json.dumps(rec.tags, ensure_ascii=False),
                    "dependencies": json.dumps(rec.dependencies, ensure_ascii=False),
                    "installed": int(rec.installed),
                    "enabled": int(rec.enabled),
                    "favorite": int(rec.favorite),
                },
            )
            c.commit()

    def delete(self, item_id: str, remove_files: bool = False) -> bool:
        rec = self.get(item_id)
        if not rec:
            return False
        if remove_files and rec.local_path and os.path.isdir(rec.local_path):
            try:
                shutil.rmtree(rec.local_path, ignore_errors=True)
            except OSError as e:
                log.warning("删除 mod 文件失败 %s: %s", rec.local_path, e)
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM mods WHERE item_id = ?", (item_id,))
            c.commit()
        log.info("已从库中移除 mod %s（文件=%s）", item_id, remove_files)
        return True

    def set_enabled(self, item_id: str, enabled: bool) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE mods SET enabled=? WHERE item_id=?", (int(enabled), item_id))
            c.commit()

    def set_category(self, item_id: str, category: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE mods SET category=? WHERE item_id=?", (category, item_id))
            c.commit()

    def set_favorite(self, item_id: str, favorite: bool) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE mods SET favorite=? WHERE item_id=?", (int(favorite), item_id))
            c.commit()

    def set_notes(self, item_id: str, notes: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE mods SET notes=? WHERE item_id=?", (notes, item_id))
            c.commit()

    # ------------------------------------------------------------- 查询
    def get(self, item_id: str) -> ModRecord | None:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM mods WHERE item_id=?", (str(item_id),)).fetchone()
        return ModRecord.from_row(row) if row else None

    def all(self) -> list[ModRecord]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM mods ORDER BY download_time DESC").fetchall()
        return [ModRecord.from_row(r) for r in rows]

    def search(
        self,
        keyword: str = "",
        appid: str = "",
        category: str = "",
        tag: str = "",
        enabled_only: bool = False,
        disabled_only: bool = False,
        favorites_only: bool = False,
        sort: str = "time",       # time / title / size / subs / appid
    ) -> list[ModRecord]:
        clauses: list[str] = []
        params: list = []
        if keyword:
            clauses.append("(title LIKE ? OR notes LIKE ? OR creator_name LIKE ? OR item_id LIKE ?)")
            kw = f"%{keyword}%"
            params += [kw, kw, kw, kw]
        if appid:
            clauses.append("appid = ?")
            params.append(str(appid))
        if category:
            clauses.append("category = ?")
            params.append(category)
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        if enabled_only:
            clauses.append("enabled = 1")
        if disabled_only:
            clauses.append("enabled = 0")
        if favorites_only:
            clauses.append("favorite = 1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = {
            "time": "download_time DESC",
            "title": "title COLLATE NOCASE ASC",
            "size": "file_size DESC",
            "subs": "subscriptions DESC",
            "appid": "appid ASC, title COLLATE NOCASE ASC",
        }.get(sort, "download_time DESC")
        sql = f"SELECT * FROM mods{where} ORDER BY {order}"
        with self._lock, self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [ModRecord.from_row(r) for r in rows]

    def categories(self, appid: str = "") -> list[str]:
        sql = "SELECT DISTINCT category FROM mods WHERE category != ''"
        params: list = []
        if appid:
            sql += " AND appid = ?"
            params.append(str(appid))
        with self._lock, self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [r["category"] for r in rows]

    def all_tags(self, appid: str = "") -> list[str]:
        recs = self.search(appid=appid)
        tags: set[str] = set()
        for r in recs:
            tags.update(r.tags)
        return sorted(tags)

    def stats(self) -> dict:
        with self._lock, self._conn() as c:
            total = c.execute("SELECT COUNT(*) n FROM mods").fetchone()["n"]
            enabled = c.execute("SELECT COUNT(*) n FROM mods WHERE enabled=1").fetchone()["n"]
            size = c.execute("SELECT COALESCE(SUM(file_size),0) s FROM mods").fetchone()["s"]
            games = c.execute("SELECT COUNT(DISTINCT appid) n FROM mods").fetchone()["n"]
        return {"total": total, "enabled": enabled, "size": size, "games": games}

    # --------------------------------------------------------- 任务历史
    def log_job(self, item_id: str, appid: str, title: str, status: str, bytes_done: int = 0, message: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO jobs (item_id, appid, title, status, bytes_done, message, created) VALUES (?,?,?,?,?,?,?)",
                (str(item_id), str(appid), title, status, bytes_done, message, int(time.time())),
            )
            c.commit()

    def job_history(self, limit: int = 100) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- 磁盘组织
    def organize_path(self, appid: str, item_id: str, library_dir: str) -> str:
        """规范化磁盘路径：<library>/<游戏名>/<item_id>。"""
        return os.path.join(library_dir, _safe_dirname(game_name(appid)), str(item_id))

    def write_metadata_sidecar(self, rec: ModRecord) -> None:
        """在 mod 目录旁写入元数据 JSON，便于离线检索/迁移。"""
        if not rec.local_path:
            return
        # legacy 单文件 mod 的 local_path 可能指向 .bin 文件，取其目录
        target = rec.local_path
        if os.path.isfile(target):
            target = os.path.dirname(target)
        try:
            os.makedirs(target, exist_ok=True)
            meta_path = os.path.join(target, "swdm_meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(rec.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.warning("写入元数据失败 %s: %s", target, e)

    def import_existing(self, library_dir: str, appid: str) -> int:
        """扫描 steamcmd 下载目录，导入未登记的 mod。返回导入数量。"""
        base = os.path.join(library_dir, "steamapps", "workshop", "content", str(appid))
        if not os.path.isdir(base):
            return 0
        imported = 0
        for item_id in os.listdir(base):
            path = os.path.join(base, item_id)
            if not os.path.isdir(path):
                continue
            if self.get(item_id):
                continue
            size = _dir_size(path)
            rec = ModRecord(
                item_id=item_id,
                appid=str(appid),
                title=f"未命名 mod {item_id}",
                local_path=path,
                installed=True,
                file_size=size,
                download_time=int(time.time()),
                source="imported",
            )
            self.upsert(rec)
            imported += 1
        if imported:
            log.info("从 %s 导入 %d 个 mod", base, imported)
        return imported


def _safe_dirname(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "unknown"


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total
