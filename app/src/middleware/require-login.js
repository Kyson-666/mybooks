// 「必须登录才能访问」(REQUIRE_LOGIN) 的全站路由守卫。
//
// 后端 BaseHandler 会把匿名请求的 /api/* 一律拦下，但页面 HTML 是由
// SpaStaticHandler（继承 web.StaticFileHandler，不经过 BaseHandler）直出的，
// 后端拦不到"打开首页"这一下，所以页面级跳转只能在前端做。
// 这里只管 UX，真正的安全边界仍在后端门禁。
import { isLoginPublicPath } from "~/utils/loginPublicPaths";

// TXT 专用阅读器是目前唯一走 SPA 路由的阅读页（EPUB/PDF 由后端直出页面，
// MyReader 由 nginx 反代）。页面本身不含书籍内容，正文接口仍由后端按逐本分享
// 授权校验（/api/read/txt/<id>、/api/book/txt/parser）。分享访客点"在线阅读"
// 后，后端 /read/<bid> 会 302 到这里；若守卫按普通页面弹回登录，就会出现
// "分享页能打开、TXT 阅读器进不去"的割裂。is_guest 在 REQUIRE_LOGIN 下即
// "持有有效分享授权"（见 UserInfo.get_user_info）。
const SHARE_READER_PATH = /^\/book\/\d+\/readtxt\/?$/;

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
    // 分享访客放行阅读器页面；没有该书授权的请求会在正文接口被拒并跳登录。
    if (user.is_guest && SHARE_READER_PATH.test(route.path)) {
        return;
    }
    // 带尾斜杠：/login 会先被 StaticFileHandler 301 到 /login/，那个 301 会丢掉 ?next=
    redirect("/login/?next=" + encodeURIComponent(route.fullPath));
}
