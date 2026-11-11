"""Run shipped policy checks against isolated NetSecurity fixtures on Windows."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


FIXTURE = r"""
$ErrorActionPreference='Stop'
$global:writes=0
$global:freezeActive=$false
function Copy-Fixture($value){return ($value|ConvertTo-Json -Depth 20 -Compress|ConvertFrom-Json)}
$global:storedProfiles=@('Domain','Private','Public')|ForEach-Object {[pscustomobject]@{Name=$_;Enabled='True';DefaultOutboundAction='Block'}}
$global:activeProfiles=Copy-Fixture @($global:storedProfiles)
$rule=[pscustomobject]@{Name='Clearpath-fixture-node-0';Enabled='True';Direction='Outbound';Action='Allow';Profile='Any';
 Program='C:\fixture.exe';Protocol='TCP';LocalPort='Any';RemotePort='443';RemoteAddress='192.0.2.10';LocalAddress='Any';InterfaceAlias='Ethernet';
 Package='';InterfaceType='Any';Service='Any';Authentication='NotRequired';Encryption='NotRequired';OverrideBlockRules='False';
 LocalUser='Any';RemoteUser='Any';RemoteMachine='Any';EdgeTraversalPolicy='Block';LooseSourceMapping='False';LocalOnlyMapping='False';Owner='';
 IcmpType='Any';DynamicTarget='Any';PolicyAppId=''}
$global:stored=@($rule)
$global:active=@(Copy-Fixture $rule)
function Global:Get-NetFirewallProfile {param($PolicyStore,$Name)
 $rows=if($PolicyStore -eq 'ActiveStore'){$global:activeProfiles}else{$global:storedProfiles}
 return @($rows|Where-Object {(-not $Name)-or $_.Name -eq $Name})
}
function Global:Get-NetFirewallRule {param($PolicyStore,$Name,$Enabled,$Direction,$Action,$ErrorAction)
 $rows=if($PolicyStore -eq 'ActiveStore'){$global:active}else{$global:stored}
 return @($rows|Where-Object {((-not $Name)-or $_.Name -eq $Name)-and((-not $Enabled)-or $_.Enabled -eq $Enabled)-and((-not $Direction)-or $_.Direction -eq $Direction)-and((-not $Action)-or $_.Action -eq $Action)})
}
function Global:Get-NetFirewallAddressFilter {process {return [pscustomobject]@{RemoteAddress=$_.RemoteAddress;LocalAddress=$_.LocalAddress}}}
function Global:Get-NetFirewallPortFilter {process {
 if($global:missingPort){return}
 if($global:missingPortProperty){return [pscustomobject]@{Protocol=$_.Protocol;LocalPort=$_.LocalPort;RemotePort=$_.RemotePort;IcmpType=$_.IcmpType}}
 return [pscustomobject]@{Protocol=$_.Protocol;LocalPort=$_.LocalPort;RemotePort=$_.RemotePort;IcmpType=$_.IcmpType;DynamicTarget=$_.DynamicTarget}
}}
function Global:Get-NetFirewallInterfaceFilter {process {return [pscustomobject]@{InterfaceAlias=$_.InterfaceAlias}}}
function Global:Get-NetFirewallInterfaceTypeFilter {process {return [pscustomobject]@{InterfaceType=$_.InterfaceType}}}
function Global:Get-NetFirewallApplicationFilter {process {return [pscustomobject]@{Program=$_.Program;Package=$_.Package}}}
function Global:Get-NetFirewallServiceFilter {process {return [pscustomobject]@{Service=$_.Service}}}
function Global:Get-NetFirewallSecurityFilter {process {return [pscustomobject]@{Authentication=$_.Authentication;Encryption=$_.Encryption;OverrideBlockRules=$_.OverrideBlockRules;LocalUser=$_.LocalUser;RemoteUser=$_.RemoteUser;RemoteMachine=$_.RemoteMachine}}}
function Global:Get-NetAdapter {return [pscustomobject]@{Name='Ethernet'}}
function Global:Enable-NetFirewallRule {param($PolicyStore,$Name)
 $global:writes++
 @($global:stored|Where-Object {$_.Name -eq $Name})|ForEach-Object {$_.Enabled='True'}
 if(-not $global:freezeActive){@($global:active|Where-Object {$_.Name -eq $Name})|ForEach-Object {$_.Enabled='True'}}
}
function Global:Disable-NetFirewallRule {throw 'UNEXPECTED_NATIVE_SETTER'}
function Global:Set-NetFirewallProfile {throw 'UNEXPECTED_NATIVE_SETTER'}
function Global:New-NetFirewallRule {throw 'UNEXPECTED_NATIVE_SETTER'}
function Global:Remove-NetFirewallRule {throw 'UNEXPECTED_NATIVE_SETTER'}
$block=[scriptblock]::Create([IO.File]::ReadAllText(__SOURCE__))
$stateDir=__FOLDER__
$null=. $block -Action Snapshot -StateDir $stateDir
function Must-Reject($operation,$code){
 $matched=$false
 try{& $operation}catch{if($_.Exception.Message -match $code){$matched=$true}else{throw}}
 if(-not $matched){throw 'EXPECTED_POLICY_REJECTION'}
}
"""


@unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell fixture runner required')
class WindowsGuardPolicy(unittest.TestCase):
    def run_fixture(self, body):
        import system_guard
        with tempfile.TemporaryDirectory(prefix='synthetic-guard-policy-') as temporary:
            folder = Path(temporary).resolve()
            core = folder / 'core-fixture.bin'
            core.write_bytes(b'fixture only')
            (folder / 'plan.json').write_text(json.dumps({
                'schema': 'clearpath-system-guard/1',
                'spec': {'scope': 'fixture', 'platform': 'windows', 'interfaces': ['Ethernet'],
                         'tunnels': [], 'core_path': str(core), 'windows_disable_rules': ['existing']},
            }), encoding='utf-8')
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            script = FIXTURE.replace('__SOURCE__', quote(ROOT / 'src/system_guard_windows.ps1'))
            script = script.replace('__FOLDER__', quote(folder))
            script += body + "\n[ordered]@{fixture_passed=$true;writes=$global:writes}|ConvertTo-Json -Compress\n"
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            exe = system_guard.windows_directory() / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            done = subprocess.run([str(exe), '-NoLogo', '-NoProfile', '-NonInteractive',
                                   '-EncodedCommand', encoded],
                                  capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            result = json.loads(done.stdout.strip())
            self.assertTrue(result['fixture_passed'])
            return result

    def test_exact_effective_policy_has_extended_fields_and_matches_journal(self):
        result = self.run_fixture(r"""
$s=Snapshot
if($s.policy_schema -ne 'clearpath-windows-guard-policy/2' -or $s.policy_issues.Count){throw 'BAD_POLICY_SNAPSHOT'}
foreach($field in @('IcmpType','DynamicTarget','PolicyAppId')){
 if(-not $s.owned[0].Contains($field) -or -not $s.active_owned[0].Contains($field)){throw 'MISSING_POLICY_FIELD'}
}
Assert-AppliedPolicy $s @($s.owned)
""")
        self.assertEqual(result['writes'], 0)

    def test_effective_conditions_drift_stays_readable_but_blocks_acceptance(self):
        result = self.run_fixture(r"""
$expected=@((Snapshot).owned)
foreach($field in @('RemoteAddress','IcmpType','DynamicTarget','PolicyAppId')){
 $old=$global:active[0].$field
 $global:active[0].$field='changed-fixture'
 $s=Snapshot
 if($s.policy_issues -notcontains 'owned_policy_store_difference'){throw 'EFFECTIVE_DRIFT_NOT_RECORDED'}
 Must-Reject {Assert-AppliedPolicy $s $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
 $global:active[0].$field=$old
}
""")
        self.assertEqual(result['writes'], 0)

    def test_duplicate_missing_and_both_store_removed_rules_fail_exact_set(self):
        self.run_fixture(r"""
$expected=@((Snapshot).owned)
$saved=Copy-Fixture $global:active[0]
$global:active+=@(Copy-Fixture $saved)
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
Must-Reject {Exact-Rule $saved.Name 'ActiveStore'} 'RULE_AMBIGUOUS'
$global:active=@()
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
$global:stored=@()
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
""")

    def test_unreviewed_allow_and_missing_or_permissive_profile_are_rejected(self):
        self.run_fixture(r"""
$expected=@((Snapshot).owned)
$foreign=Copy-Fixture $global:active[0];$foreign.Name='new-foreign-allow'
$global:active+=@($foreign)
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
$global:active=@($global:active|Where-Object {$_.Name -ne 'new-foreign-allow'})
$global:activeProfiles[0].DefaultOutboundAction='Allow'
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'ACTIVE_POLICY_NOT_APPLIED'
$global:activeProfiles=@($global:activeProfiles|Where-Object {$_.Name -ne 'Domain'})
Must-Reject {Assert-AppliedPolicy (Snapshot) $expected} 'ACTIVE_POLICY_NOT_APPLIED'
""")

    def test_validate_compares_reviewed_foreign_rule_full_effective_conditions(self):
        result = self.run_fixture(r"""
$global:stored[0].Name='existing';$global:active[0].Name='existing'
Validate
$global:active[0].PolicyAppId='different-fixture'
Must-Reject {Validate} 'RULE_CONFLICT'
$global:active[0].PolicyAppId=''
$global:active+=@(Copy-Fixture $global:active[0])
Must-Reject {Validate} 'POLICY_STORE_CONFLICT'
""")
        self.assertEqual(result['writes'], 0)

    def test_missing_filter_cannot_become_an_empty_verified_value(self):
        result = self.run_fixture(r"""
$global:missingPort=$true
Must-Reject {Snapshot} 'RULE_FILTER_UNAVAILABLE'
""")
        self.assertEqual(result['writes'], 0)

    def test_missing_extended_property_is_unknown_and_cannot_activate(self):
        result = self.run_fixture(r"""
$expected=@((Snapshot).owned)
$global:missingPortProperty=$true
$s=Snapshot
if($s.policy_issues -notcontains 'rule_policy_fields_unavailable'){throw 'MISSING_PROPERTY_NOT_RECORDED'}
Must-Reject {Assert-AppliedPolicy $s $expected} 'EFFECTIVE_RULES_NOT_APPLIED'
$global:missingPortProperty=$false
$global:stored[0].PSObject.Properties.Remove('PolicyAppId')
$global:active[0].PSObject.Properties.Remove('PolicyAppId')
$s=Snapshot
if($s.policy_issues -notcontains 'rule_policy_fields_unavailable'){throw 'MISSING_RULE_PROPERTY_NOT_RECORDED'}
$global:stored[0].Name='existing';$global:active[0].Name='existing'
Must-Reject {Validate} 'POLICY_FIELDS_UNAVAILABLE'
""")
        self.assertEqual(result['writes'], 0)

    def test_legacy_journal_remains_restorable_and_keeps_legacy_readback_label(self):
        result = self.run_fixture(r"""
$global:stored[0].Name='existing';$global:active[0].Name='existing'
$baseline=Snapshot-ForBaseline (Snapshot) ([pscustomobject]@{})
$before=Rule-Record $global:stored[0]
foreach($field in @('IcmpType','DynamicTarget','PolicyAppId','PolicyReadbackComplete')){$before.Remove($field)}
$global:stored[0].Enabled='False';$global:active[0].Enabled='False'
$expected=Rule-Record $global:stored[0]
foreach($field in @('IcmpType','DynamicTarget','PolicyAppId','PolicyReadbackComplete')){$expected.Remove($field)}
Save-PrivateJson $journalPath ([ordered]@{schema='clearpath-windows-guard-journal/1';before=$baseline;
 entries=@([ordered]@{kind='disabled';name='existing';before=$before;expected=$expected})})
Restore
$receipt=Get-Content -LiteralPath (Join-Path $stateDir 'native-restored.json') -Raw -Encoding UTF8|ConvertFrom-Json
if($receipt.policy_readback_schema -ne 'legacy-recorded-fields'){throw 'LEGACY_SCOPE_NOT_LABELLED'}
if($global:stored[0].Enabled -ne 'True' -or $global:active[0].Enabled -ne 'True'){throw 'LEGACY_RULE_NOT_RESTORED'}
""")
        self.assertEqual(result['writes'], 1)

    def test_new_journal_restore_checks_effective_readback_and_keeps_recovery_material(self):
        result = self.run_fixture(r"""
$global:stored[0].Name='existing';$global:active[0].Name='existing'
$baseline=Snapshot
$before=Rule-Record $global:stored[0]
$global:stored[0].Enabled='False';$global:active[0].Enabled='False'
$expected=Rule-Record $global:stored[0]
Save-PrivateJson $journalPath ([ordered]@{schema='clearpath-windows-guard-journal/1';before=$baseline;
 entries=@([ordered]@{kind='disabled';name='existing';before=$before;expected=$expected})})
$global:freezeActive=$true
Must-Reject {Restore} 'RULE_CONFLICT'
if(-not(Test-Path -LiteralPath $journalPath)){throw 'RECOVERY_JOURNAL_MISSING'}
$global:freezeActive=$false
$global:active[0].Enabled='True'
Restore
$receipt=Get-Content -LiteralPath (Join-Path $stateDir 'native-restored.json') -Raw -Encoding UTF8|ConvertFrom-Json
if($receipt.policy_readback_schema -ne 'clearpath-windows-guard-policy/2'){throw 'NEW_READBACK_NOT_LABELLED'}
""")
        self.assertEqual(result['writes'], 1)


if __name__ == '__main__':
    unittest.main()
