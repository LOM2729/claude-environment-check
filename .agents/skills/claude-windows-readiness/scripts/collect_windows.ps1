# Windows local metadata only. No network probe, setting changes or raw values.
# Compatible with Windows PowerShell 5.1; the parent process supplies a timeout.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($env:OS -ne 'Windows_NT') { exit 2 }

$result = [ordered]@{}
try { $result.system_version = (Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec 4).Version } catch {}
try { $result.timezone = (Get-TimeZone).Id } catch {}
try { $result.system_locale = (Get-Culture).Name } catch {}
try { $result.ui_locale = (Get-UICulture).Name } catch {}
try { $result.languages = @((Get-WinUserLanguageList).LanguageTag) } catch {}
try {
    $proxy = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($null -ne $proxy.ProxyEnable) {
        $result.http_proxy_enabled = [bool]$proxy.ProxyEnable
    }
    $result.pac_present = -not [string]::IsNullOrEmpty([string]$proxy.AutoConfigURL)
    # ProxyEnable is WinINET's manual switch, not a per-protocol/process guarantee.
} catch {}
try {
    $dns = @(Get-DnsClientServerAddress)
    $v4 = 0; $v6 = 0
    foreach ($entry in $dns) {
        foreach ($value in $entry.ServerAddresses) {
            $address = $null
            if ([System.Net.IPAddress]::TryParse([string]$value, [ref]$address)) {
                if ($address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) { $v4++ }
                elseif ($address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) { $v6++ }
            }
        }
    }
    $result.dns_v4_count = $v4; $result.dns_v6_count = $v6
} catch {}
try {
    $result.ipv4_interface_count = @(Get-NetIPInterface -AddressFamily IPv4).Count
    $result.ipv6_interface_count = @(Get-NetIPInterface -AddressFamily IPv6).Count
} catch {}
try { $result.time_service_running = ((Get-Service w32time).Status -eq 'Running') } catch {}
# Automatic time/time-zone UI switches are left unknown: a service's start mode
# is not proof of those switches or a successful synchronization.
# Native objects are never serialized; only the explicitly chosen scalars above.
$result | ConvertTo-Json -Depth 4 -Compress
