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
            let timer = null;
            const timeout = new Promise((resolve) => {
                timer = setTimeout(() => resolve({ err: "timeout" }), TIMEOUT_MS);
            });
            pending = Promise.race([app.$backend("/user/info"), timeout])
                .then((rsp) => {
                    if (rsp && rsp.sys) {
                        app.store.commit("login", rsp);
                        cached = rsp;
                        cachedAt = Date.now();
                    }
                    return rsp || {};
                })
                .catch(() => ({}))
                .then((rsp) => {
                    if (timer) {
                        clearTimeout(timer);
                    }
                    pending = null;
                    return rsp;
                });
        }
        return pending;
    });

    inject("resetSession", function () {
        pending = null;
        cached = null;
        cachedAt = 0;
    });
};
