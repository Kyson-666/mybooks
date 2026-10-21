#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""侧边栏显示项（``SIDEBAR_ITEMS``）的读取期归一化。

管理员在「站点与外观 → 侧边栏显示项目」勾选的导航项落在 ``SIDEBAR_ITEMS``，由
``GET /api/user/info`` 的 ``sys.sidebar_items`` 下发（见 webserver/handlers/base.py
的 ``_sys_info_with``），前端 ``AppHeader.vue`` 的 ``showItem(key)`` 据此决定显隐。

本模块存在的唯一理由是一处**升级期的静默丢项**：旧版 admin.py 在值为空时写入的默认
列表没有 ``authors`` / ``friends`` / ``booklists``（那三项本 PR 才成为合法取值）。
凡是打开过设置页的站点，那份旧默认列表已经持久化进 auto.py，升级后「值为空」不再成立，
于是 ``showItem`` 会把这三项判为「管理员取消勾选」而永久隐藏。缺席的键不可能是用户
主动取消勾选的结果（它在旧版本根本不是合法值），所以这是可证明的配置陈旧，而非用户意图。

处理方式与 ``webserver/base/homepage.py`` 一致：**只在读取期归一化，绝不回写配置**。
- 存的列表与某一代旧默认列表**集合相同** → 视为新默认列表（补上三个新键）。
- 集合不同（真·自定义子集，如 ``["tags","series"]``）→ 原样返回，用户意图必须继续生效。
- 空列表 → 原样返回（历史语义「全部显示」）。
- 仅含哨兵 ``none`` → 原样返回（「全部隐藏」；旧默认列表非空，永不与之冲突）。

本模块只有纯函数与一个读设置的便捷入口：不碰 DB、不写配置，方便单测。
"""

# 「全部隐藏」哨兵：设置页全不勾选时由前端写入，它不是导航项，仅表示全部隐藏。
SIDEBAR_NO_ITEM = "none"

# 当前默认列表（与 webserver/handlers/admin.py 里空值时写入的默认列表逐项同序，勿改顺序）。
SIDEBAR_DEFAULT_ITEMS = [
    "audiobooks",
    "printbooks",
    "publishers",
    "folders",
    "tags",
    "series",
    "languages",
    "rating",
    "booklists",
    "memo",
    "categories",
    "authors",
    "friends",
]

# 历史上 admin.py 空值时写入过的旧默认列表：v4.6.0 及此前为 10 项，「微调目录功能」之前
# 还是不带 categories 的 9 项。两代都是「管理员没动过侧边栏」的产物，都要认。
SIDEBAR_LEGACY_DEFAULTS = (
    ("audiobooks", "printbooks", "publishers", "folders", "tags", "series", "languages", "rating", "memo", "categories"),
    ("audiobooks", "printbooks", "publishers", "folders", "tags", "series", "languages", "rating", "memo"),
)

SIDEBAR_LEGACY_SETS = tuple(frozenset(items) for items in SIDEBAR_LEGACY_DEFAULTS)


def _is_legacy_default(stored):
    """非空列表的集合恰好等于某一代旧默认列表时，认定它是升级前的陈旧默认。"""
    return frozenset(stored) in SIDEBAR_LEGACY_SETS


def normalize_sidebar_items(raw):
    """返回下发给前端 / 交给设置页的侧边栏列表；只做读取期归一化，不写回配置。"""
    if not isinstance(raw, (list, tuple)):
        # 没配过，或 auto.py 被手改成字符串/dict：沿用「空表示全部显示」的旧语义
        return []
    stored = [item for item in raw if isinstance(item, str)]
    if not stored:
        return list(raw)
    if _is_legacy_default(stored):
        return list(SIDEBAR_DEFAULT_ITEMS)
    return list(raw)


def get_sidebar_items(settings=None):
    """读设置并归一化；入口与 ``get_homepage_config()`` 一致，两处调用方共用本函数。"""
    if settings is None:
        from webserver import loader

        settings = loader.get_settings()
    return normalize_sidebar_items(settings.get("SIDEBAR_ITEMS", []))
