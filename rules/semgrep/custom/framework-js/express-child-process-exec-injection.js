const { exec, execSync } = require('child_process');

app.get('/ping', (req, res) => {
    const host = req.query.host;
    // ruleid: express-child-process-exec-injection
    exec(`ping -c 1 ${host}`, (err, stdout) => {
        res.send(stdout);
    });
});

function bad2(userInput) {
    // ruleid: express-child-process-exec-injection
    execSync('echo ' + userInput);
}

function ok1() {
    // ok: express-child-process-exec-injection
    exec('uptime', (err, stdout) => {});
}
