# Read-only presence check. Do not output values, paths or exception details.
# User/Machine values do not establish a running application's environment.
param(
    [ValidateSet('Process', 'User', 'Machine')]
    [string[]]$Scope = @('Process', 'User', 'Machine')
)

if ($env:OS -ne 'Windows_NT') {
    throw 'Run this check in native Windows PowerShell, not macOS or WSL.'
}

$claudeCheckKeys = @(
    'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN',
    'ANTHROPIC_BASE_URL', 'CLAUDE_CONFIG_DIR', 'ANTHROPIC_PROFILE',
    'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'
)
foreach ($claudeCheckScope in $Scope) {
    foreach ($claudeCheckKey in $claudeCheckKeys) {
        try {
            $claudeCheckValue = [Environment]::GetEnvironmentVariable(
                $claudeCheckKey, [System.EnvironmentVariableTarget]$claudeCheckScope
            )
            if ($null -eq $claudeCheckValue) {
                $claudeCheckState = 'absent'
            } elseif ($claudeCheckValue.Length -eq 0) {
                $claudeCheckState = 'empty'
            } else {
                $claudeCheckState = 'present'
            }
        } catch {
            $claudeCheckState = 'unavailable'
        }
        '{0}{1}{2}{1}{3}' -f $claudeCheckScope.ToLowerInvariant(), "`t", $claudeCheckKey, $claudeCheckState
        $claudeCheckValue = $null
    }
}
