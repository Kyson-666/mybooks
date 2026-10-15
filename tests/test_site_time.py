#!/usr/bin/env python3
"""webserver/site_time.py：站点时区的解析与「站点的一天」换算。

阅读统计按天分桶，分桶键必须是站点时区下的日期，否则 UTC+8 的读者在本地
00:00~08:00 的阅读会被记到前一天。
"""

import datetime
import unittest
from unittest import mock

from webserver import loader, site_time


class TestSiteTime(unittest.TestCase):
    def setUp(self):
        self.conf = loader.get_settings()
        self._saved = {
            key: self.conf.get(key)
            for key in ("site_timezone", "site_language")
            if key in self.conf
        }
        self._missing = [key for key in ("site_timezone", "site_language") if key not in self.conf]
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            self.conf[key] = value
        for key in self._missing:
            self.conf.pop(key, None)

    def _set(self, timezone=None, language=None):
        if timezone is None:
            self.conf.pop("site_timezone", None)
        else:
            self.conf["site_timezone"] = timezone
        if language is not None:
            self.conf["site_language"] = language

    # ---------- 默认值：语言决定 ----------

    def test_default_timezone_follows_language(self):
        self.assertEqual(site_time.default_timezone_name("zh"), "Asia/Shanghai")
        self.assertEqual(site_time.default_timezone_name("zh-TW"), "Asia/Shanghai")
        self.assertEqual(site_time.default_timezone_name("zh_CN"), "Asia/Shanghai")
        self.assertEqual(site_time.default_timezone_name("en"), "UTC")

    def test_default_timezone_falls_back_to_utc_plus_8(self):
        # 语言识别不出来时按默认语言（zh）走，即东八区，而不是静默退回 UTC
        for lang in ("", None, "fr", "auto"):
            self.assertEqual(site_time.default_timezone_name(lang), "Asia/Shanghai")

    def test_auto_resolves_by_site_language(self):
        self._set(timezone="auto", language="zh-TW")
        self.assertEqual(site_time.resolve_timezone_name(), "Asia/Shanghai")
        self._set(timezone="auto", language="en")
        self.assertEqual(site_time.resolve_timezone_name(), "UTC")

    def test_empty_value_means_auto(self):
        self._set(timezone="", language="en")
        self.assertEqual(site_time.resolve_timezone_name(), "UTC")
        self._set(timezone="   ", language="zh")
        self.assertEqual(site_time.resolve_timezone_name(), "Asia/Shanghai")

    def test_explicit_timezone_wins_over_language(self):
        self._set(timezone="America/New_York", language="zh")
        self.assertEqual(site_time.resolve_timezone_name(), "America/New_York")

    # ---------- 「站点的一天」 ----------

    def test_utc_plus_8_buckets_early_morning_reading_to_the_local_day(self):
        self._set(timezone="Asia/Shanghai", language="zh")
        # 北京时间 2026-10-15 00:30 = UTC 2026-10-14 16:30：UTC 日期还停在前一天
        instant = datetime.datetime(2026, 10, 14, 16, 30)
        self.assertEqual(site_time.site_date(instant), datetime.date(2026, 10, 15))
        # 北京时间 2026-10-14 23:30 = UTC 2026-10-14 15:30，仍属 10-14
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 10, 14, 15, 30)),
            datetime.date(2026, 10, 14),
        )

    def test_utc_timezone_keeps_the_utc_day(self):
        self._set(timezone="UTC", language="en")
        instant = datetime.datetime(2026, 10, 14, 16, 30)
        self.assertEqual(site_time.site_date(instant), datetime.date(2026, 10, 14))

    def test_site_date_accepts_aware_instants(self):
        self._set(timezone="Asia/Shanghai", language="zh")
        aware = datetime.datetime(2026, 10, 14, 16, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(site_time.site_date(aware), datetime.date(2026, 10, 15))

    def test_site_today_and_site_now_are_consistent(self):
        self._set(timezone="Asia/Shanghai", language="zh")
        self.assertEqual(site_time.site_today(), site_time.site_now().date())

    # ---------- 兜底与缓存 ----------

    def test_unknown_timezone_falls_back_to_the_language_default(self):
        self._set(timezone="Asia/Shanghi", language="zh")  # 拼错的 IANA 名
        self.assertEqual(site_time.resolve_timezone_name(), "Asia/Shanghai")
        self.assertEqual(site_time.timezone_label(), "UTC+08:00 (Asia/Shanghai)")
        # 名字不认识 → 按语言默认（东八区）而不是 UTC
        self.assertEqual(site_time.site_now().utcoffset(), datetime.timedelta(hours=8))

    def test_setting_change_is_picked_up_without_restart(self):
        self._set(timezone="Asia/Shanghai", language="zh")
        self.assertEqual(site_time.site_now().utcoffset(), datetime.timedelta(hours=8))
        self.conf["site_timezone"] = "UTC"
        self.assertEqual(site_time.site_now().utcoffset(), datetime.timedelta(0))

    def test_zero_offset_label(self):
        self._set(timezone="UTC", language="en")
        self.assertEqual(site_time.timezone_label(), "UTC+00:00 (UTC)")

    def test_half_hour_offset_label(self):
        self._set(timezone="Asia/Kolkata", language="en")
        self.assertEqual(site_time.timezone_label(), "UTC+05:30 (Asia/Kolkata)")

    def test_negative_offset_label(self):
        self._set(timezone="America/Sao_Paulo", language="en")
        self.assertEqual(site_time.timezone_label(), "UTC-03:00 (America/Sao_Paulo)")

    # ---------- 夏令时（固定偏移兜底会算错的那些日子） ----------

    def test_dst_aware_dates_differ_by_season_for_the_same_utc_clock(self):
        # 纽约：同一 UTC 钟点，冬季 EST(-5) 落在前一天、夏季 EDT(-4) 落在当天。
        # 用固定 -5 兜底会把夏季那条错到 07-14，正好钉住「必须真的走 zoneinfo」。
        self._set(timezone="America/New_York", language="en")
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 1, 15, 4, 30)),
            datetime.date(2026, 1, 14),
        )
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 7, 15, 4, 30)),
            datetime.date(2026, 7, 15),
        )

    def test_dst_transition_day_keeps_the_local_date(self):
        # 2026-03-08 当地 02:00 起 EST→EDT；UTC 05:30 还在切换前（EST），即当地 00:30 同日
        self._set(timezone="America/New_York", language="en")
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 3, 8, 5, 30)),
            datetime.date(2026, 3, 8),
        )

    def test_southern_hemisphere_dst_is_opposite_to_northern(self):
        # 悉尼：1 月 AEDT(+11)、7 月 AEST(+10)，与北半球相反
        self._set(timezone="Australia/Sydney", language="en")
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 1, 14, 12, 30)),
            datetime.date(2026, 1, 14),
        )
        self.assertEqual(
            site_time.site_date(datetime.datetime(2026, 7, 14, 15, 30)),
            datetime.date(2026, 7, 15),
        )

    # ---------- 无 tzdata 环境 ----------

    def test_missing_tzdata_uses_region_offset_for_names_outside_the_table(self):
        # 模拟精简镜像 / Windows 未装 tzdata：表外的 IANA 名按大区近似偏移（America/ → -5），
        # 而不是退回站点语言默认（中文站 +8，与芝加哥差 14 小时）
        self._set(timezone="America/Chicago", language="zh")
        with mock.patch.object(site_time, "ZoneInfo", None):
            self.assertEqual(site_time.site_now().utcoffset(), datetime.timedelta(hours=-5))
            self.assertEqual(site_time.resolve_timezone_name(), "America/Chicago")

    def test_misspelled_name_still_falls_back_to_the_language_default(self):
        # 本机有 tzdata 时，拼错的名字仍走语言默认，别被大区兜底吃掉（原名不能说成有效）
        self._set(timezone="Europe/Berlinn", language="zh")
        self.assertEqual(site_time.resolve_timezone_name(), "Asia/Shanghai")


if __name__ == "__main__":
    unittest.main()
