// 「必须登录才能访问」(REQUIRE_LOGIN) 的全站路由守卫。
//
// 后端 BaseHandler 会把匿名请求的 /api/* 一律回 user.need_login，但页面 HTML 是由
// SpaStaticHandler（继承 web.StaticFileHandler，不经过 BaseHandler）直出的，
// 后端拦不到"打开首页"这一下，所以页面级跳转只能在前端做。
// 这里只管 UX，真正的安全边界仍在后端门禁。
const PUBLIC_PATHS = ["/login", "/logout", "/signup", "/welcome", "/install", "/starting"];
// 分享链接按 token 授权，属于受控出口，不因必须登录而失效。
const PUBLIC_PREFIX = ["/s/"];

export default async function ({ app, route, redirect }) {
    if (process.server) {
        return;
    }
    const path = route.path || "/";
    if (PUBLIC_PATHS.includes(path) || PUBLIC_PREFIX.some((p) => path.startsWith(p))) {
        return;
    }
    if (app.store.state.user && app.store.state.user.is_login) {
        return;
    }

    const info = await app.$ensureSession();
    const user = (info && info.user) || app.store.state.user || {};
    const allow = (info && info.sys && info.sys.allow) || (app.store.state.sys && app.store.state.sys.allow) || {};
    if (user.is_login || allow.require_login !== true) {
        return;
    }
    redirect("/login?next=" + encodeURIComponent(route.fullPath));
}
