// 只接受"同源站内路径"的 next（登录/访问码/启动页的回跳目标）。
//
// 必须挡的不只是 //host：
// - `/\host`：浏览器对 special scheme 把反斜杠当斜杠，等于 //host；
// - `/foo\t/bar` 之类带控制字符的变形，靠 URL 解析后再比 origin 兜住；
// - 带 scheme 的绝对地址。
// 返回去掉 origin 的 path+search+hash（保持原样，避免双重编码）。
export default function safeNext(raw, fallback = "/") {
    if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//")) {
        return fallback;
    }
    if (raw.indexOf("\\") !== -1) {
        return fallback;
    }
    if (typeof window === "undefined") {
        return fallback;
    }
    let url;
    try {
        url = new URL(raw, window.location.origin);
    } catch (e) {
        return fallback;
    }
    if (url.origin !== window.location.origin) {
        return fallback;
    }
    // 解析后再判一次 pathname：`/..//evil.com`、`/./\evil.com` 这类点段会被 URL
    // 归一化成 `//evil.com`，origin 仍是本站，只比对入参前缀会漏掉；
    // 以 `//` 开头的路径交给 location.replace 就是协议相对地址（会跳外站）。
    const pathname = url.pathname || "";
    if (!pathname.startsWith("/") || pathname.startsWith("//")) {
        return fallback;
    }
    return pathname + url.search + url.hash;
}
