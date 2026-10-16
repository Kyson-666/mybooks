// 站点时区下的「今天」。
//
// 阅读统计按天分桶由服务端按 sys.timezone 切天（见 webserver/site_time.py），前端的
// 「今天」标记与区间端点必须落在同一个时区上：浏览器时区与站点不同（例如站点设为
// UTC 而访客在 UTC+8）时，直接 new Date() 会让月历高亮错一格、把服务端还没有的
// 明天当成区间右端。
//
// timezone 缺失或非法时退回浏览器本地时区，行为与改动前一致。

export function siteTodayStr(timezone) {
    const now = new Date();
    if (timezone) {
        try {
            const parts = new Intl.DateTimeFormat('en-US', {
                timeZone: timezone,
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
            }).formatToParts(now);
            const pick = (type) => (parts.find((p) => p.type === type) || {}).value;
            const [y, m, d] = [pick('year'), pick('month'), pick('day')];
            if (y && m && d) {
                return `${y}-${m}-${d}`;
            }
        } catch (error) {
            console.warn('Invalid site timezone, falling back to browser timezone:', timezone, error);
        }
    }
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${m}-${d}`;
}

// 「站点时区的今天」对应的 Date：时刻取浏览器本地当天 00:00。页面里的周/月/年锚点
// 运算都按浏览器本地时间做，这里只把「是哪一天」换成站点那一天。
export function siteTodayDate(timezone) {
    return new Date(`${siteTodayStr(timezone)}T00:00:00`);
}
