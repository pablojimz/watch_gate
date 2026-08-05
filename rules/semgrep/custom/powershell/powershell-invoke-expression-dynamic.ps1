# ruleid: powershell-invoke-expression-dynamic
Invoke-Expression $userInput

# ruleid: powershell-invoke-expression-dynamic
iex $downloadedScript

# ruleid: powershell-invoke-expression-dynamic
Invoke-Expression "Get-Process"

# ok: powershell-invoke-expression-dynamic
Get-Process
