"""Execute the shipped PowerShell recovery against in-memory NetSecurity mocks.

Windows-only protocol test: no NetSecurity command reaches the OS. Mac/Linux
skip it rather than presenting a text scan as Windows behavioral validation.
"""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(sys.platform == 'win32', 'PowerShell mock execution requires a Windows runner')
class WindowsRecoveryProtocol(unittest.TestCase):
    def test_full_rule_filter_witness_preserves_later_edits(self):
        import system_guard
        with tempfile.TemporaryDirectory(prefix='synthetic-windows-guard-') as temporary:
            folder = Path(temporary).resolve()
            (folder / 'plan.json').write_text(json.dumps({'schema': 'clearpath-system-guard/1',
                'spec': {'scope': 'fixture', 'platform': 'windows'}}), encoding='utf-8')
            script = r'''
$ErrorActionPreference='Stop'
$global:enables=0
$global:removes=0
$global:profiles=@('Domain','Private','Public')|ForEach-Object {[pscustomobject]@{Name=$_;Enabled='True';DefaultOutboundAction='Allow'}}
$global:rules=@([pscustomobject]@{Name='fixture-existing';Enabled='True';Direction='Outbound';Action='Allow';Profile='Any';
 Program='C:\fixture.exe';Protocol='TCP';LocalPort='Any';RemotePort='443';RemoteAddress='192.0.2.0/24';LocalAddress='Any';InterfaceAlias='Any';
 Package='';InterfaceType='Any';Service='Any';Authentication='NotRequired';Encryption='NotRequired';OverrideBlockRules='False';
 LocalUser='Any';RemoteUser='Any';RemoteMachine='Any';EdgeTraversalPolicy='Block';LooseSourceMapping='False';LocalOnlyMapping='False';Owner='';
 IcmpType='Any';DynamicTarget='Any';PolicyAppId=''})
function Global:Get-NetFirewallProfile {param($PolicyStore,$Name) return @($global:profiles|Where-Object {(-not $Name)-or $_.Name -eq $Name})}
function Global:Get-NetFirewallRule {
 param($PolicyStore,$Name,$Enabled,$Direction,$Action,$ErrorAction)
 return @($global:rules|Where-Object {((-not $Name)-or $_.Name -eq $Name)-and((-not $Enabled)-or $_.Enabled -eq $Enabled)-and((-not $Direction)-or $_.Direction -eq $Direction)-and((-not $Action)-or $_.Action -eq $Action)})
}
function Global:Get-NetFirewallAddressFilter {process {return [pscustomobject]@{RemoteAddress=$_.RemoteAddress;LocalAddress=$_.LocalAddress}}}
function Global:Get-NetFirewallPortFilter {process {return [pscustomobject]@{Protocol=$_.Protocol;LocalPort=$_.LocalPort;RemotePort=$_.RemotePort;IcmpType=$_.IcmpType;DynamicTarget=$_.DynamicTarget}}}
function Global:Get-NetFirewallInterfaceFilter {process {return [pscustomobject]@{InterfaceAlias=$_.InterfaceAlias}}}
function Global:Get-NetFirewallInterfaceTypeFilter {process {return [pscustomobject]@{InterfaceType=$_.InterfaceType}}}
function Global:Get-NetFirewallApplicationFilter {process {return [pscustomobject]@{Program=$_.Program;Package=$_.Package}}}
function Global:Get-NetFirewallServiceFilter {process {return [pscustomobject]@{Service=$_.Service}}}
function Global:Get-NetFirewallSecurityFilter {process {return [pscustomobject]@{Authentication=$_.Authentication;Encryption=$_.Encryption;OverrideBlockRules=$_.OverrideBlockRules;LocalUser=$_.LocalUser;RemoteUser=$_.RemoteUser;RemoteMachine=$_.RemoteMachine}}}
function Global:Enable-NetFirewallRule {param($PolicyStore,$Name) $global:enables++;($global:rules|Where-Object {$_.Name -eq $Name}).Enabled='True'}
function Global:Disable-NetFirewallRule {throw 'UNEXPECTED_DISABLED_SETTER'}
function Global:Set-NetFirewallProfile {throw 'UNEXPECTED_PROFILE_SETTER'}
function Global:New-NetFirewallRule {throw 'UNEXPECTED_NEW_RULE'}
function Global:Remove-NetFirewallRule {throw 'UNEXPECTED_RULE_DELETE'}
$block=[scriptblock]::Create([IO.File]::ReadAllText(__SOURCE__))
$stateDir=__FOLDER__
$null=. $block -Action Snapshot -StateDir $stateDir
$baseline=Snapshot
$before=Rule-Record $global:rules[0]
$global:rules[0].Enabled='False'
$expected=Rule-Record $global:rules[0]
$journal=[ordered]@{schema='clearpath-windows-guard-journal/1';before=$baseline;entries=@([ordered]@{kind='disabled';name='fixture-existing';before=$before;expected=$expected})}
Save-PrivateJson (Join-Path $stateDir 'native-journal.json') $journal
# Change one filter while still disabled. An OFF must not enable a broader rule.
$global:rules[0].RemoteAddress='Any'
$blocked=$false
try{$null=& $block -Action Restore -StateDir $stateDir}catch{if($_.Exception.Message -match 'GUARD_WINDOWS_RULE_CONFLICT'){$blocked=$true}else{throw}}
if(-not $blocked -or $global:enables -ne 0 -or $global:rules[0].Enabled -ne 'False' -or $global:rules[0].RemoteAddress -ne 'Any'){throw 'LATER_EDIT_NOT_PRESERVED'}
# The exact expected-disabled snapshot can be restored to the exact baseline.
$global:rules[0].RemoteAddress='192.0.2.0/24'
$null=& $block -Action Restore -StateDir $stateDir
if($global:enables -ne 1 -or $global:rules[0].Enabled -ne 'True'){throw 'EXACT_BASELINE_NOT_RESTORED'}
[ordered]@{conflict_preserved=$blocked;exact_restore=$true;native_netsecurity_calls=0}|ConvertTo-Json -Compress
'''
            script = script.replace('__SOURCE__', literal(ROOT / 'src/system_guard_windows.ps1')).replace('__FOLDER__', literal(folder))
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            exe = system_guard.windows_directory() / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            done = subprocess.run([str(exe), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                  capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            result = json.loads(done.stdout.strip())
            self.assertTrue(result['conflict_preserved'])
            self.assertTrue(result['exact_restore'])
            self.assertEqual(result['native_netsecurity_calls'], 0)


if __name__ == '__main__':
    unittest.main()
