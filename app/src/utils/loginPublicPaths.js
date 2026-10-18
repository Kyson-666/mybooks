// 「必须登录才能访问」(REQUIRE_LOGIN) 下的公开路由清单。
// 路由守卫（middleware/require-login.js）与 $backend 的 need_login 跳转共用这一份，
// 避免两处清单不同步（例如守卫放行 /welcome，而 $backend 还把它弹去登录页）。
export const LOGIN_PUBLIC_PATHS = [
    "/login",
    "/logout",
    "/signup",
    "/welcome",
    "/install",
    "/starting",
];
// 邮箱激活成功页（后端 /api/active/<user>/<code> 校验完 302 到这里，此时还没登录）
export const LOGIN_PUBLIC_PREFIXES = ["/active/"];

export function normalizePath(path) {
    // /login/ 与 /login 是同一页（后端 StaticFileHandler 还会把 /login 301 到 /login/）
    const p = (path || "/").replace(/\/+$/, "");
    return p || "/";
}

export function isLoginPublicPath(path) {
    const p = normalizePath(path);
    return LOGIN_PUBLIC_PATHS.includes(p) || LOGIN_PUBLIC_PREFIXES.some((prefix) => p.startsWith(prefix));
}
