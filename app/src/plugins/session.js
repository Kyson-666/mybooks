// 会话态单次拉取：路由守卫需要在页面组件渲染前判断"是否已登录"，
// 而 /api/user/info 原本只在 AppHeader.mounted 里拉，首屏守卫拿不到。
// 这里缓存一次 Promise，避免每次跳转都打一次接口；登录成功后由登录页调用
// $resetSession() 作废缓存，否则守卫会拿旧的"未登录"快照把人弹回登录页。
export default ({ app }, inject) => {
    let pending = null;

    inject("ensureSession", function () {
        const user = app.store.state.user;
        if (user && user.is_login) {
            return Promise.resolve({ err: "ok", user, sys: app.store.state.sys });
        }
        if (!pending) {
            pending = app
                .$backend("/user/info")
                .then((rsp) => {
                    if (rsp && rsp.sys) {
                        app.store.commit("login", rsp);
                    }
                    return rsp || {};
                })
                .catch(() => ({}));
        }
        return pending;
    });

    inject("resetSession", function () {
        pending = null;
    });
};
