Java.perform(function () {
    try {
        var Interceptor = Java.use('jc.a');
        var orig = Interceptor.a.overload('ig.f');
        orig.implementation = function (chain) {
            var req = null;
            try {
                req = chain.f.value;   // ig.f.f = Request
                console.log('[WS-REQ] ' + req.toString());
            } catch (e) { console.log('[WS-REQ-ERR] ' + e); }
            var resp = orig.call(this, chain);
            try {
                console.log('[WS-RESP] ' + resp.toString());
                // 读取响应体（仅当为错误 JSON 时）
                var body = resp.f20754b;   // ResponseBody
                if (body !== null) {
                    try {
                        var s = body.c().B(2000);
                        console.log('[WS-BODY] ' + s);
                    } catch (e2) { console.log('[WS-BODY-ERR] ' + e2); }
                }
            } catch (e) { console.log('[WS-RESP-ERR] ' + e); }
            return resp;
        };
        console.log('[WS] hooked jc.a');
    } catch (e) { console.log('[WS] hook failed: ' + e); }
});
