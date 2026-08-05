const jwt = require('jsonwebtoken');

function bad1(token) {
    // ruleid: javascript-jwt-verify-disabled
    const decoded = jwt.decode(token);
    return decoded;
}

function bad2(token, secret) {
    // ruleid: javascript-jwt-verify-disabled
    const payload = jwt.verify(token, secret, { algorithms: ['HS256', 'none'] });
    return payload;
}

function ok1(token, secret) {
    // ok: javascript-jwt-verify-disabled
    const payload = jwt.verify(token, secret, { algorithms: ['HS256'] });
    return payload;
}
