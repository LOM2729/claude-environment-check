param([Parameter(Mandatory=$true)][string]$AdapterName)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try {
    if ($AdapterName.IndexOfAny([char[]]'*?[]') -ge 0) { exit 1 }
    $rows = @(Get-NetAdapterBinding -ComponentID ms_tcpip6 | Where-Object { $_.Name -ceq $AdapterName })
    if ($rows.Count -ne 1) { exit 1 }
    [ordered]@{ name = [string]$rows[0].Name; enabled = [bool]$rows[0].Enabled; description = [string]$rows[0].InterfaceDescription } | ConvertTo-Json -Compress
} catch { exit 1 }
