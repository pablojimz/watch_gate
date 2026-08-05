app.post('/calc', (req, res) => {
    const expr = req.body.expr;
    // ruleid: express-eval-dynamic-code
    const result = eval(expr);
    res.json({ result });
});

function bad2(userCode) {
    // ruleid: express-eval-dynamic-code
    const fn = new Function(userCode);
    return fn();
}

function ok1() {
    // ok: express-eval-dynamic-code
    return eval("1 + 1");
}
