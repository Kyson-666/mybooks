// 「必须登录才能访问」(REQUIRE_LOGIN) 的全站路由守卫。
//
// 后端 BaseHandler 会把匿名请求的 /api/* 一律拦下，但页面 HTML 是由
// SpaStaticHandler（继承 web.StaticFileHandler，不经过 BaseHandler）直出的，
// 后端拦不到"打开首页"这一下，所以页面级跳转只能在前端做。
// 这里只管 UX，真正的安全边界仍在后端门禁。
import { isLoginPublicPath } from "~/utils/loginPublicPaths";

export default async function ({ app, route, redirect }) {
    if (process.server) {
        return;
    }
    if (isLoginPublicPath(route.path)) {
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
    // 带尾斜杠：/login 会先被 StaticFileHandler 301 到 /login/，那个 301 会丢掉 ?next=
    redirect("/login/?next=" + encodeURIComponent(route.fullPath));
}
