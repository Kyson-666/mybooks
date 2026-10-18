import { isLoginPublicPath } from "~/utils/loginPublicPaths";

export default ({ app }, inject) => {
    inject("alert", function (alertType, alertMsg, alertTo) {
        app.store.commit("alert", { type: alertType, msg: alertMsg, to: alertTo });
        if (alertType === 'success') {
            setTimeout(() => {
                app.store.commit('close_alert')
            }, 1300)
        }
    })
    inject("backend", function (url, options) {
        if (url === undefined) {
            throw "url is undefined "
        }
        var args = {
            mode: "cors", redirect: "follow", credentials: 'include',
        }
        var server = "";
        if (process.server) {
            if (app.context.req !== undefined) {
                // 某些NAS用户会在外面套一层反向代理，docker内无法访问该URL
                // 强制服务器地址为本机；通过 XFH 传递实际访问的域名
                server = app.context.$config.api_url;
                var headers = app.context.req.headers;
                args.headers = {
                    "cookie": headers.cookie,
                    "X-Forwarded-Host": headers.host,
                    "X-Forwarded-For": headers["x-forwarded-for"],
                    "X-Forwarded-Proto": headers["x-forwarded-proto"] || headers["x-scheme"] || "https",
                    "X-Scheme": headers["x-scheme"] || headers["x-forwarded-proto"] || "https",
                }
            } else {
                // 在server端但没有req对象时，直接返回空对象，避免fetch失败
                // 客户端会在mounted时重新请求数据
                return Promise.resolve({});
            }
        } else {
            server = window.location.origin;
        }

        var fullUrl = server + "/api" + url;
        const goStarting = () => {
            const { route, redirect } = app.context;
            if (route.path !== "/starting") {
                redirect(302, "/starting?next=" + encodeURIComponent(route.fullPath));
            }
        };

        if (options !== undefined) {
            Object.assign(args, options);
        }

        // 记下发出请求时的会话代次：请求在飞行期间登录/退出，回来的 need_login 就过期了
        const sessionEpoch = app.$sessionEpoch ? app.$sessionEpoch() : 0;

        return fetch(fullUrl, args)
            .then(rsp => {
                const shouldIgnore = url.endsWith("/tasks/running") && rsp.status !== 200;
                if (shouldIgnore) {
                    return { err: 'ok' };
                }
                var msg = "";
                if (rsp.status === 413) {
                    msg = "服务器响应了413异常状态码。<br/>可能是上传的文件过大，超过了服务器设置的上传大小。";
                    app.$alert("error", msg);
                    throw msg;
                }

                if (rsp.status === 502) {
                    if (!process.server) {
                        goStarting();
                        // 与 need_login 同款兜底：导航结束后 redirect 是空操作，
                        // 否则页面会停在一个永不 settle 的请求上（半空状态）。
                        if (process.client) {
                            setTimeout(() => {
                                if (!window.location.pathname.startsWith("/starting")) {
                                    window.location.assign(
                                        "/starting?next=" + encodeURIComponent(app.context.route.fullPath)
                                    );
                                }
                            }, 300);
                        }
                        return new Promise(() => {});
                    }
                    msg = "服务器正在启动中...";
                    app.$alert("info", msg);
                    throw msg;
                }

                if (rsp.status !== 200) {
                    msg = "服务器异常，状态码: " + rsp.status + "<br/>请查阅服务器日志:<br/>mybooks.log";
                    app.$alert("error", msg);
                    throw msg;
                }

                try {
                    return rsp.json();
                } catch (err) {
                    msg = "服务器异常，响应非JSON<br/>请查阅服务器日志:<br/>mybooks.log";
                    app.$alert("error", msg);
                    throw msg;
                }
            })
            .then(rsp => {
                const { route, redirect, res } = app.context;
                if (rsp.err === 'server_starting') {
                    goStarting();
                    // 启动期间原请求不再回调，避免各页面把它当成错误弹框
                    return process.server ? rsp : new Promise(() => {});
                }
                if (rsp.err === 'not_installed') {
                    redirect(301, "/install");
                } else if (rsp.err === 'not_invited') {
                    if (route.path !== "/welcome") {
                        // 302：带 next 的用户相关跳转不该被缓存；next 必须编码，否则 ?/# 会截断
                        redirect(302, "/welcome?next=" + encodeURIComponent(route.fullPath));
                    }
                } else if (rsp.err === 'user.need_login') {
                    // 请求发出后登录/退出过（代次变了）→ 这个响应已经过期：
                    // 刚登录成功的用户不能被一个迟到的 need_login 清回匿名。
                    if (app.$sessionEpoch && app.$sessionEpoch() !== sessionEpoch) {
                        return rsp;
                    }
                    // 「必须登录才能访问」开启后，任何页面/接口都可能返回它。
                    // 会话可能已过期：store 里的 is_login 和守卫的会话快照都要作废，
                    // 只清缓存不清 store 的话，守卫会一直走"已登录"快路径。
                    app.store.commit("clear_user");
                    if (app.$resetSession) {
                        app.$resetSession();
                    }
                    // 公开页（登录/退出/注册/访问码/安装）自己不再重复跳，避免环。
                    if (!isLoginPublicPath(route.path)) {
                        // 用 /login/（带尾斜杠）：/login 会先被 StaticFileHandler 301 到
                        // /login/，那个 301 丢 query，next 就没了（整页兜底时尤其明显）。
                        const to = "/login/?next=" + encodeURIComponent(route.fullPath);
                        // 302 而不是 301：登录跳转不该被浏览器/代理长期缓存。
                        redirect(302, to);
                        // 页面 mounted 里发的请求（导航已结束）在 Nuxt 2 客户端里
                        // redirect 是空操作，兜底整页跳转，避免停在半空页面。
                        if (process.client) {
                            setTimeout(() => {
                                if (!window.location.pathname.startsWith("/login")) {
                                    window.location.assign(to);
                                }
                            }, 300);
                        }
                    }
                } else if (rsp.err === 'exception') {
                    if (res !== undefined) {
                        res.setHeader('Cache-Control', 'no-cache');
                    }
                    app.store.commit("alert", { type: "error", msg: rsp.msg, to: null });
                }
                return rsp;
            })
    })
}

