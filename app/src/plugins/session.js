// 会话态单次拉取：路由守卫需要在页面组件渲染前判断"是否已登录"，
// 而 /api/user/info 原本只在 AppHeader.mounted 里拉，首屏守卫拿不到。
// 这里缓存 60 秒（只缓存成功响应）：既避免每次跳转都打接口，也不至于让
// "登录/退出/管理员改了开关"之后还拿着旧快照做判断。
// 失败/超时（后端启动中时 $backend 会返回永不 settle 的 Promise）不缓存，
// 否则守卫会被一个挂起的 Promise 卡住。
const TTL_MS = 60 * 1000;
const TIMEOUT_MS = 5000;

export default ({ app }, inject) => {
    let pending = null;
    let cached = null;
    let cachedAt = 0;
    // 每次 reset 递增：reset 之前发出的请求即使在 reset 之后才回来，也必须丢弃，
    // 否则它会把"旧用户已登录"重新写回 store 和缓存（登录/退出/换账号时都会踩到）。
    let epoch = 0;

    const isFresh = () => cached !== null && Date.now() - cachedAt < TTL_MS;

    inject("ensureSession", function () {
        const user = app.store.state.user;
        if (user && user.is_login) {
            return Promise.resolve({ err: "ok", user, sys: app.store.state.sys });
        }
        if (isFresh()) {
            return Promise.resolve(cached);
        }
        if (!pending) {
            const requestEpoch = epoch;
            let timer = null;
            const timeout = new Promise((resolve) => {
                timer = setTimeout(() => resolve({ err: "timeout" }), TIMEOUT_MS);
            });
            pending = Promise.race([app.$backend("/user/info"), timeout])
                .then((rsp) => {
                    if (requestEpoch !== epoch) {
                        return {};
                    }
                    if (rsp && rsp.sys) {
                        app.store.commit("login", rsp);
                        // 匿名快照只在"站点不要求登录"时缓存：否则另一个标签页登录后，
                        // 本标签页会拿着 60 秒内的匿名快照把已登录用户弹回登录页。
                        const loggedIn = !!(rsp.user && rsp.user.is_login);
                        const requireLogin = !!(rsp.sys.allow && rsp.sys.allow.require_login);
                        if (loggedIn || !requireLogin) {
                            cached = rsp;
                            cachedAt = Date.now();
                        }
                    }
                    return rsp || {};
                })
                .catch(() => ({}))
                .then((rsp) => {
                    if (timer) {
                        clearTimeout(timer);
                    }
                    if (requestEpoch === epoch) {
                        pending = null;
                    }
                    return rsp;
                });
        }
        return pending;
    });

    inject("resetSession", function () {
        epoch += 1;
        pending = null;
        cached = null;
        cachedAt = 0;
    });

    // 给 $backend 用：请求发出时记下代次，回来时若已变（登录/退出）
    // 就丢弃这个响应，避免迟到的 need_login 把刚登录的用户清掉。
    inject("sessionEpoch", function () {
        return epoch;
    });
};
