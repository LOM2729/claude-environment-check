# Local-only DNS configuration identity. Caller hashes this in memory; never publishes raw addresses.
$ErrorActionPreference = 'Stop'
try {
    $rows = @(Get-DnsClientServerAddress | Where-Object { $_.ServerAddresses.Count -gt 0 } |
        Sort-Object InterfaceIndex, AddressFamily | ForEach-Object {
            [ordered]@{ interface = [int]$_.InterfaceIndex; family = [int]$_.AddressFamily; servers = @($_.ServerAddresses) }
        })
    ConvertTo-Json -InputObject $rows -Depth 4 -Compress
} catch { exit 1 }
