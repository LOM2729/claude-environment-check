param(
  [Parameter(Mandatory=$true)][ValidateSet('Secure','Audit','Snapshot','Coverage','Validate','Arm','Apply','Restore','Persist','Unpersist','Disarm','Expire','RecoveryReady')][string]$Action,
  [Parameter(Mandatory=$true)][string]$StateDir
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
if($Action -in @('Secure','Audit')){
  $scope=Split-Path -Path $StateDir -Leaf
  $plan=[pscustomobject]@{schema='clearpath-system-guard/1';spec=[pscustomobject]@{platform='windows';scope=$scope}}
}else{$plan=Get-Content -LiteralPath (Join-Path $StateDir 'plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json}
if($plan.schema -ne 'clearpath-system-guard/1' -or $plan.spec.platform -ne 'windows' -or $plan.spec.scope -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,31}$'){throw 'GUARD_WINDOWS_PLAN_INVALID'}
$spec=$plan.spec
$prefix='Clearpath-'+$spec.scope.ToLower()+'-'
$taskBase='Clearpath-Guard-'+$spec.scope.ToLower()
$journalPath=Join-Path $StateDir 'native-journal.json'
$stateLock=$null
if($Action -eq 'Expire'){
  $stateLock=[IO.File]::Open((Join-Path $StateDir '.operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
  while($true){try{$stateLock.Lock(0,1);break}catch [IO.IOException]{Start-Sleep -Milliseconds 100}}
}
$mutex=$null
if($Action -ne 'RecoveryReady'){
  $mutex=New-Object Threading.Mutex($false,('Global\'+$taskBase))
  if(-not $mutex.WaitOne(15000)){throw 'GUARD_WINDOWS_BUSY'}
}

function Save-PrivateJson($Path,$Object){
  $tmp=$Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
  $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Object|ConvertTo-Json -Depth 30 -Compress))
  $f=[IO.File]::Open($tmp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$f.Write($bytes,0,$bytes.Length);$f.Flush($true)}finally{$f.Dispose()}
  if(Test-Path -LiteralPath $Path){[IO.File]::Replace($tmp,$Path,$null)}else{[IO.File]::Move($tmp,$Path)}
}
function Audit-StateTree{
  $common=[Environment]::GetFolderPath('CommonApplicationData')
  $expected=Join-Path $common ('Clearpath\guard\'+$spec.scope.ToLower())
  if([IO.Path]::GetFullPath($StateDir) -ine [IO.Path]::GetFullPath($expected)){throw 'GUARD_WINDOWS_STATE_PATH'}
  $paths=@((Join-Path $common 'Clearpath'),(Join-Path $common 'Clearpath\guard'),$StateDir)
  if(Test-Path -LiteralPath $StateDir){$paths+=@(Get-ChildItem -LiteralPath $StateDir -File|Select-Object -ExpandProperty FullName)}
  foreach($path in $paths){
    if(-not(Test-Path -LiteralPath $path)){continue}
    $item=Get-Item -LiteralPath $path
    if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'GUARD_WINDOWS_STATE_REPARSE_REJECTED'}
    $acl=Get-Acl -LiteralPath $path
    if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'GUARD_WINDOWS_STATE_OWNER'}
    foreach($ace in $acl.Access){
      $sid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
      if($ace.AccessControlType -eq 'Allow' -and $sid -notin @('S-1-5-18','S-1-5-32-544') -and ([int]$ace.FileSystemRights -band 0xD0156)){throw 'GUARD_WINDOWS_STATE_WRITABLE'}
    }
  }
  # Include all ancestors in reparse checks. The OS-known common-data directory
  # may allow creating new children; owned descendants above must not be writable.
  $path=[IO.DirectoryInfo]::new($StateDir)
  while($null -ne $path){
    if($path.Exists -and ($path.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GUARD_WINDOWS_STATE_REPARSE_REJECTED'}
    $path=$path.Parent
  }
}
function Values($v){return (@($v)|ForEach-Object {[string]$_}|Sort-Object)-join "`0"}
function Address-Values($values){
  return @($values|ForEach-Object {
    $text=[string]$_
    if($text -match '^([0-9.]+)/([0-9.]+)$' -and $Matches[2].Contains('.')){
      $ip=[Net.IPAddress]::Parse($Matches[1]);$mask=[Net.IPAddress]::Parse($Matches[2])
      $bits=($mask.GetAddressBytes()|ForEach-Object {[Convert]::ToString($_,2).PadLeft(8,'0')})-join ''
      if($bits -notmatch '^1*0*$'){throw 'GUARD_WINDOWS_ADDRESS_MASK_INVALID'}
      $text=$ip.ToString()+'/'+($bits.Replace('0','').Length)
    }
    if($text -match '^([0-9.]+)/32$'){$text=[Net.IPAddress]::Parse($Matches[1]).ToString()}
    $text
  }|Sort-Object)
}
function Rule-Record($rule){
  $a=@($rule|Get-NetFirewallAddressFilter)
  $p=@($rule|Get-NetFirewallPortFilter)
  $i=@($rule|Get-NetFirewallInterfaceFilter)
  $it=@($rule|Get-NetFirewallInterfaceTypeFilter)
  $app=@($rule|Get-NetFirewallApplicationFilter)
  $service=@($rule|Get-NetFirewallServiceFilter)
  $security=@($rule|Get-NetFirewallSecurityFilter)
  foreach($count in @($a.Count,$p.Count,$i.Count,$it.Count,$app.Count,$service.Count,$security.Count)){
    if($count -ne 1){throw 'GUARD_WINDOWS_RULE_FILTER_UNAVAILABLE'}
  }
  $a=$a[0];$p=$p[0];$i=$i[0];$it=$it[0];$app=$app[0];$service=$service[0];$security=$security[0]
  $policyFieldsAvailable=($p.PSObject.Properties.Name -contains 'IcmpType') -and
    ($p.PSObject.Properties.Name -contains 'DynamicTarget') -and ($rule.PSObject.Properties.Name -contains 'PolicyAppId')
  $protocol=[string]$p.Protocol
  $protocolNames=@{'TCP'='6';'UDP'='17';'Any'='256'}
  if($protocolNames.ContainsKey($protocol)){$protocol=$protocolNames[$protocol]}
  return [ordered]@{Name=[string]$rule.Name;Enabled=[string]$rule.Enabled;Direction=[string]$rule.Direction;Action=[string]$rule.Action;
    Profile=[string]$rule.Profile;Program=[string]$app.Program;Package=[string]$app.Package;Protocol=$protocol;LocalPort=@($p.LocalPort|Sort-Object);
    RemotePort=@($p.RemotePort|Sort-Object);RemoteAddress=@(Address-Values $a.RemoteAddress);LocalAddress=@(Address-Values $a.LocalAddress);
    InterfaceAlias=@($i.InterfaceAlias|Sort-Object);InterfaceType=@($it.InterfaceType|Sort-Object);Service=[string]$service.Service;
    Authentication=[string]$security.Authentication;Encryption=[string]$security.Encryption;OverrideBlockRules=[string]$security.OverrideBlockRules;
    LocalUser=[string]$security.LocalUser;RemoteUser=[string]$security.RemoteUser;RemoteMachine=[string]$security.RemoteMachine;
    EdgeTraversalPolicy=[string]$rule.EdgeTraversalPolicy;LooseSourceMapping=[string]$rule.LooseSourceMapping;
    LocalOnlyMapping=[string]$rule.LocalOnlyMapping;Owner=[string]$rule.Owner;
    IcmpType=@($p.IcmpType|Sort-Object);DynamicTarget=[string]$p.DynamicTarget;PolicyAppId=[string]$rule.PolicyAppId;
    PolicyReadbackComplete=[bool]$policyFieldsAvailable}
}
function Record-Dict($object){$d=[ordered]@{};foreach($p in $object.PSObject.Properties){$d[$p.Name]=$p.Value};return $d}
function Profiles($store){return @(Get-NetFirewallProfile -PolicyStore $store | Sort-Object Name | ForEach-Object {
  [ordered]@{Name=[string]$_.Name;Enabled=[string]$_.Enabled;DefaultOutboundAction=[string]$_.DefaultOutboundAction}})}
function Snapshot{
  $stored=@(Get-NetFirewallRule -PolicyStore PersistentStore)
  $active=@(Get-NetFirewallRule -PolicyStore ActiveStore)
  $owned=@($stored|Where-Object {$_.Name.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)}|Sort-Object Name|ForEach-Object {Rule-Record $_})
  $effectiveOwned=@($active|Where-Object {$_.Name.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)}|Sort-Object Name|ForEach-Object {Rule-Record $_})
  $storedAllows=@($stored|Where-Object {[string]$_.Enabled -eq 'True' -and [string]$_.Direction -eq 'Outbound' -and [string]$_.Action -eq 'Allow'})
  $activeAllows=@($active|Where-Object {[string]$_.Enabled -eq 'True' -and [string]$_.Direction -eq 'Outbound' -and [string]$_.Action -eq 'Allow'})
  $issues=@()
  if(@(@($owned)+@($effectiveOwned)|Where-Object {-not $_.PolicyReadbackComplete}).Count){
    $issues+=@('rule_policy_fields_unavailable')
  }
  foreach($set in @(@{rules=$owned},@{rules=$effectiveOwned},@{rules=$storedAllows},@{rules=$activeAllows})){
    if(@($set.rules|Group-Object Name|Where-Object {$_.Count -gt 1}).Count){$issues+=@('ambiguous_rule_names')}
  }
  if(($owned|ConvertTo-Json -Depth 20 -Compress) -cne ($effectiveOwned|ConvertTo-Json -Depth 20 -Compress)){
    $issues+=@('owned_policy_store_difference')
  }
  $allows=@($activeAllows|Where-Object {-not $_.Name.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)}|Select-Object -ExpandProperty Name|Sort-Object)
  $storedAllowNames=@($storedAllows|Where-Object {-not $_.Name.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)}|Select-Object -ExpandProperty Name|Sort-Object)
  if((Values $allows) -cne (Values $storedAllowNames)){$issues+=@('allow_policy_store_difference')}
  # Keep discrepancies readable so normal status and independent recovery can
  # diagnose a changed effective policy. Only activation asserts convergence.
  return [ordered]@{profiles=@(Profiles 'PersistentStore');active_profiles=@(Profiles 'ActiveStore');allow_names=$allows;owned=$owned;
    policy_schema='clearpath-windows-guard-policy/2';active_owned=$effectiveOwned;persistent_allow_names=$storedAllowNames;
    policy_issues=@($issues|Sort-Object -Unique)}
}
function Exact-Rule($name,$store='PersistentStore'){
  if($name -match '[*?\[\]]'){throw 'GUARD_WINDOWS_RULE_NAME_INVALID'}
  $r=@(Get-NetFirewallRule -PolicyStore $store -Name $name -ErrorAction SilentlyContinue|Where-Object {$_.Name -ieq $name})
  if($r.Count -gt 1){throw 'GUARD_WINDOWS_RULE_AMBIGUOUS'}
  if($r.Count -eq 1 -and $r[0].Name -cne $name){throw 'GUARD_WINDOWS_RULE_NAME_CHANGED'}
  if($r.Count -eq 1){return $r[0]};return $null
}
function Assert-DesiredRule($r,$expected){
  $actual=Rule-Record $r
  foreach($key in $expected.Keys){
    $want=$expected[$key]
    if($key -eq 'Protocol'){
      $mapped=@{'TCP'='6';'UDP'='17';'Any'='256'}
      if($mapped.ContainsKey([string]$want)){$want=$mapped[[string]$want]}
    }
    if($key -in @('RemoteAddress','LocalAddress')){$want=Address-Values $want}
    if((Values $actual[$key]) -cne (Values $want)){throw 'GUARD_WINDOWS_RULE_CONFLICT'}
  }
}
function Persist-Journal{Save-PrivateJson $journalPath $script:journal}
function Add-Entry($entry){$script:journal.entries+=@($entry);Persist-Journal}
function Add-OwnRule($suffix,$direction,$protocol,$address,$ports,$program,$aliases,$action='Allow',$localPorts='Any'){
  $name=$prefix+$suffix
  if(Exact-Rule $name){throw 'GUARD_WINDOWS_OWNED_RULE_EXISTS'}
  $expected=[ordered]@{Name=$name;Enabled='False';Direction=$direction;Action=$action;Profile='Any';Program=$program;
    Protocol=$protocol;LocalPort=@($localPorts);RemotePort=@($ports);RemoteAddress=@($address);InterfaceAlias=@($aliases)}
  $entry=[ordered]@{kind='rule';name=$name;creation_expected=$expected;expected=$null}
  Add-Entry $entry
  $params=@{PolicyStore='PersistentStore';Name=$name;DisplayName=$name;Enabled='False';Profile='Any';Direction=$direction;Action=$action;
    Protocol=$protocol;RemoteAddress=$address;RemotePort=$ports;LocalPort=$localPorts;Program=$program;InterfaceAlias=$aliases}
  New-NetFirewallRule @params|Out-Null
  Assert-DesiredRule (Exact-Rule $name) $expected
  # A disabled creation cannot open traffic. Pin the complete native record
  # before the enabling setter so interrupted activation has an exact witness.
  $entry.expected=Rule-Record (Exact-Rule $name)
  if(-not $entry.expected.PolicyReadbackComplete){throw 'GUARD_WINDOWS_POLICY_FIELDS_UNAVAILABLE'}
  $entry.expected.Enabled='True'
  Persist-Journal
  Enable-NetFirewallRule -PolicyStore PersistentStore -Name $name|Out-Null
  Assert-DesiredRule (Exact-Rule $name) $entry.expected
}
function Validate{
  $s=Snapshot
  if(@($s.owned).Count -ne 0 -or @($s.active_owned).Count -ne 0){throw 'GUARD_WINDOWS_OWNED_RULES_EXIST'}
  if(@($s.policy_issues).Count){throw 'GUARD_WINDOWS_POLICY_STORE_CONFLICT'}
  if((Values $s.allow_names) -cne (Values $spec.windows_disable_rules) -or
     (Values $s.persistent_allow_names) -cne (Values $spec.windows_disable_rules)){throw 'GUARD_WINDOWS_ALLOW_RULE_REVIEW_REQUIRED'}
  foreach($profiles in @(@{rows=$s.profiles},@{rows=$s.active_profiles})){
    if((Values @($profiles.rows|ForEach-Object {$_.Name})) -cne (Values @('Domain','Private','Public'))){throw 'GUARD_WINDOWS_PROFILE_SCOPE'}
  }
  foreach($name in @($spec.windows_disable_rules)){
    $r=Exact-Rule $name
    if($null -eq $r -or [string]$r.Enabled -ne 'True' -or [string]$r.Direction -ne 'Outbound' -or [string]$r.Action -ne 'Allow'){throw 'GUARD_WINDOWS_RULE_NOT_LOCAL'}
    $effective=Exact-Rule $name 'ActiveStore'
    if($null -eq $effective){throw 'GUARD_WINDOWS_POLICY_STORE_CONFLICT'}
    $storedRecord=Rule-Record $r
    $activeRecord=Rule-Record $effective
    if(-not $storedRecord.PolicyReadbackComplete -or -not $activeRecord.PolicyReadbackComplete){throw 'GUARD_WINDOWS_POLICY_FIELDS_UNAVAILABLE'}
    Assert-DesiredRule $effective $storedRecord
  }
  $names=@(Get-NetAdapter -IncludeHidden|Select-Object -ExpandProperty Name)
  foreach($name in @($spec.interfaces)+@($spec.tunnels)){if($names -cnotcontains $name){throw 'GUARD_WINDOWS_INTERFACE_MISSING'}}
  if(-not (Test-Path -LiteralPath $spec.core_path -PathType Leaf)){throw 'GUARD_WINDOWS_CORE_UNAVAILABLE'}
  if((Get-Item -LiteralPath $spec.core_path).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'GUARD_WINDOWS_CORE_REPARSE_REJECTED'}
}
function Arm{
  if(Get-ScheduledTask -TaskName ($taskBase+'-*') -ErrorAction SilentlyContinue){throw 'GUARD_WINDOWS_TIMER_EXISTS'}
  $exe=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $backend=Join-Path $StateDir 'backend.ps1'
  if($backend.Contains('"') -or $StateDir.Contains('"')){throw 'GUARD_WINDOWS_PATH_INVALID'}
  $args='-NoLogo -NoProfile -NonInteractive -File "'+$backend+'" -Action Expire -StateDir "'+$StateDir+'"'
  $a=New-ScheduledTaskAction -Execute $exe -Argument $args
  $principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
  $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
  $state=Get-Content -LiteralPath (Join-Path $StateDir 'state.json') -Raw -Encoding UTF8|ConvertFrom-Json
  $readyPath=Join-Path $StateDir 'recovery-ready.json'
  if(Test-Path -LiteralPath $readyPath){Remove-Item -LiteralPath $readyPath}
  $probeArgs='-NoLogo -NoProfile -NonInteractive -File "'+$backend+'" -Action RecoveryReady -StateDir "'+$StateDir+'"'
  $probe=New-ScheduledTaskAction -Execute $exe -Argument $probeArgs
  try{
    Register-ScheduledTask -TaskName ($taskBase+'-Preflight') -Action $probe -Principal $principal -Settings $settings|Out-Null
    Start-ScheduledTask -TaskName ($taskBase+'-Preflight')
    $until=(Get-Date).AddSeconds(8)
    do{Start-Sleep -Milliseconds 100;if(Test-Path -LiteralPath $readyPath){break}}while((Get-Date) -lt $until)
    if(-not(Test-Path -LiteralPath $readyPath)){throw 'GUARD_WINDOWS_RECOVERY_WORKER_NOT_READY'}
    $ready=Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($ready.nonce -cne $state.recovery_nonce -or $ready.binding -cne $state.binding -or $ready.sid -ne 'S-1-5-18'){throw 'GUARD_WINDOWS_RECOVERY_WORKER_NOT_READY'}
  }finally{Unregister-ScheduledTask -TaskName ($taskBase+'-Preflight') -Confirm:$false -ErrorAction SilentlyContinue}
  Register-ScheduledTask -TaskName ($taskBase+'-Deadline') -Action $a -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds([int]$spec.fuse_seconds)) -Principal $principal -Settings $settings | Out-Null
  Register-ScheduledTask -TaskName ($taskBase+'-BootRecovery') -Action $a -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $principal -Settings $settings | Out-Null
  foreach($n in @('Deadline','BootRecovery')){if(-not(Get-ScheduledTask -TaskName ($taskBase+'-'+$n))){throw 'GUARD_WINDOWS_TIMER_NOT_ARMED'}}
}
function Assert-AppliedPolicy($snapshot,$expected){
  if(@($snapshot.policy_issues).Count -or @($snapshot.allow_names).Count -or
     @($snapshot.persistent_allow_names).Count){throw 'GUARD_WINDOWS_EFFECTIVE_RULES_NOT_APPLIED'}
  foreach($profiles in @(@{rows=$snapshot.profiles},@{rows=$snapshot.active_profiles})){
    if((Values @($profiles.rows|ForEach-Object {$_.Name})) -cne (Values @('Domain','Private','Public')) -or
       @($profiles.rows|Where-Object {$_.Enabled -ne 'True' -or $_.DefaultOutboundAction -ne 'Block'}).Count){
      throw 'GUARD_WINDOWS_ACTIVE_POLICY_NOT_APPLIED'
    }
  }
  foreach($records in @(@{rows=$snapshot.owned},@{rows=$snapshot.active_owned})){
    if(($records.rows|ConvertTo-Json -Depth 20 -Compress) -cne ($expected|ConvertTo-Json -Depth 20 -Compress)){throw 'GUARD_WINDOWS_EFFECTIVE_RULES_NOT_APPLIED'}
  }
}
function Apply{
  Validate
  $before=Snapshot
  $script:journal=[ordered]@{schema='clearpath-windows-guard-journal/1';before=$before;entries=@()}
  Persist-Journal
  foreach($name in @($spec.windows_disable_rules)){
    $beforeRecord=Rule-Record (Exact-Rule $name)
    $expectedRecord=Rule-Record (Exact-Rule $name);$expectedRecord.Enabled='False'
    Add-Entry ([ordered]@{kind='disabled';name=$name;before=$beforeRecord;expected=$expectedRecord})
    Disable-NetFirewallRule -PolicyStore PersistentStore -Name $name|Out-Null
  }
  $n=0
  foreach($node in @($spec.nodes)){
    Add-OwnRule ('node-'+$n) 'Outbound' ([string]$node.protocol).ToUpper() @($node.address) @($node.ports) $spec.core_path @($spec.interfaces);$n++
  }
  $n=0
  foreach($tun in @($spec.tunnels)){Add-OwnRule ('tun-'+$n) 'Outbound' 'Any' @('Any') @('Any') 'Any' @($tun);$n++}
  $n=0
  foreach($e in @($spec.exceptions)){
    if($e.direction -eq 'out'){Add-OwnRule ('exception-'+$n) 'Outbound' ([string]$e.protocol).ToUpper() @($e.network) @($e.ports) 'Any' @($spec.interfaces)}
    else{Add-OwnRule ('exception-'+$n) 'Inbound' ([string]$e.protocol).ToUpper() @($e.network) @('Any') 'Any' @($spec.interfaces) 'Allow' @($e.ports)}
    $n++
  }
  $n=0
  foreach($address in @($spec.bootstrap_dns)){
    foreach($proto in @('TCP','UDP')){Add-OwnRule ('dns-'+$n+'-'+$proto) 'Outbound' $proto @($address) @(53) $spec.core_path @($spec.interfaces)};$n++
  }
  Add-OwnRule 'loopback4' 'Outbound' 'Any' @('127.0.0.0/8') @('Any') 'Any' @('Any')
  Add-OwnRule 'dhcp' 'Outbound' 'UDP' @('255.255.255.255') @(67) 'Any' @($spec.interfaces) 'Allow' @(68)
  Add-OwnRule 'ipv6-block' 'Outbound' 'Any' @('::/0') @('Any') 'Any' @($spec.interfaces) 'Block'
  foreach($profile in @($before.profiles)){
    Add-Entry ([ordered]@{kind='profile';name=$profile.Name;enabled=$profile.Enabled;outbound=$profile.DefaultOutboundAction})
    Set-NetFirewallProfile -PolicyStore PersistentStore -Name $profile.Name -Enabled True -DefaultOutboundAction Block
  }
  $after=Snapshot
  $expected=@($script:journal.entries|Where-Object {$_.kind -eq 'rule'}|ForEach-Object {$_.expected}|Sort-Object Name)
  Assert-AppliedPolicy $after $expected
}
function Snapshot-ForBaseline($current,$baseline){
  if($baseline.policy_schema -eq 'clearpath-windows-guard-policy/2'){return $current}
  if($null -ne $baseline.policy_schema){throw 'GUARD_WINDOWS_BASELINE_SCHEMA_UNSUPPORTED'}
  # Legacy deployments retain their hash-pinned worker. This compatibility path
  # reads only the fields that a legacy journal actually witnessed.
  $owned=@($current.owned|ForEach-Object {
    $row=Record-Dict ([pscustomobject]$_)
    foreach($key in @('IcmpType','DynamicTarget','PolicyAppId','PolicyReadbackComplete')){$row.Remove($key)}
    $row
  })
  return [ordered]@{profiles=$current.profiles;active_profiles=$current.active_profiles;allow_names=$current.allow_names;owned=$owned}
}
function Restore{
  if(-not(Test-Path -LiteralPath $journalPath)){return}
  $j=Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8|ConvertFrom-Json
  if($j.schema -ne 'clearpath-windows-guard-journal/1'){throw 'GUARD_WINDOWS_JOURNAL_INVALID'}
  $entries=@($j.entries);[array]::Reverse($entries)
  foreach($e in $entries){
    if($e.kind -eq 'profile'){
      $p=Get-NetFirewallProfile -PolicyStore PersistentStore -Name $e.name
      if(([string]$p.Enabled -ne 'True' -and [string]$p.Enabled -ne $e.enabled) -or ([string]$p.DefaultOutboundAction -ne 'Block' -and [string]$p.DefaultOutboundAction -ne $e.outbound)){throw 'GUARD_WINDOWS_PROFILE_CONFLICT'}
      Set-NetFirewallProfile -PolicyStore PersistentStore -Name $e.name -Enabled $e.enabled -DefaultOutboundAction $e.outbound
    }elseif($e.kind -eq 'rule'){
      if(-not ([string]$e.name).StartsWith($prefix,[StringComparison]::Ordinal)){throw 'GUARD_WINDOWS_FOREIGN_RULE'}
      $r=Exact-Rule $e.name
      if($r){
        if($null -eq $e.expected){throw 'GUARD_WINDOWS_CREATED_RULE_REVIEW_REQUIRED'}
        $expected=Record-Dict $e.expected
        $actual=Rule-Record $r
        if($actual.Enabled -eq 'False'){$expected.Enabled='False'}
        Assert-DesiredRule $r $expected
        Remove-NetFirewallRule -PolicyStore PersistentStore -Name $e.name
      }
    }elseif($e.kind -eq 'disabled'){
      $r=Exact-Rule $e.name
      if($null -eq $r){throw 'GUARD_WINDOWS_DISABLED_RULE_CONFLICT'}
      $beforeRecord=Record-Dict $e.before
      $expectedRecord=Record-Dict $e.expected
      if([string]$r.Enabled -eq 'True'){Assert-DesiredRule $r $beforeRecord}
      else{Assert-DesiredRule $r $expectedRecord;Enable-NetFirewallRule -PolicyStore PersistentStore -Name $e.name|Out-Null;Assert-DesiredRule (Exact-Rule $e.name) $beforeRecord}
      if($j.before.policy_schema -eq 'clearpath-windows-guard-policy/2'){
        $effective=Exact-Rule $e.name 'ActiveStore'
        if($null -eq $effective){throw 'GUARD_WINDOWS_RESTORE_EFFECTIVE_RULE_CONFLICT'}
        Assert-DesiredRule $effective $beforeRecord
      }
    }else{throw 'GUARD_WINDOWS_JOURNAL_INVALID'}
  }
  $now=Snapshot
  $compared=Snapshot-ForBaseline $now $j.before
  if(($compared|ConvertTo-Json -Depth 30 -Compress) -cne ($j.before|ConvertTo-Json -Depth 30 -Compress)){throw 'GUARD_WINDOWS_RESTORE_READBACK_CONFLICT'}
  Save-PrivateJson (Join-Path $StateDir 'native-restored.json') ([ordered]@{restored=$true;at=[DateTime]::UtcNow.ToString('o');
    policy_readback_schema=if($j.before.policy_schema){$j.before.policy_schema}else{'legacy-recorded-fields'}})
}
function Disarm{
  foreach($n in @('Deadline','BootRecovery')){
    $name=$taskBase+'-'+$n
    $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($task){Unregister-ScheduledTask -TaskName $name -Confirm:$false}
  }
}
try{
  if($Action -eq 'Audit'){Audit-StateTree}
  elseif($Action -eq 'Secure'){
    Audit-StateTree
    $common=[Environment]::GetFolderPath('CommonApplicationData')
    $expected=Join-Path $common ('Clearpath\guard\'+$spec.scope.ToLower())
    if([IO.Path]::GetFullPath($StateDir) -ine [IO.Path]::GetFullPath($expected)){throw 'GUARD_WINDOWS_STATE_PATH'}
    $owner=New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    foreach($dir in @((Join-Path $common 'Clearpath'),(Join-Path $common 'Clearpath\guard'),$StateDir)){
      $exists=Test-Path -LiteralPath $dir
      if($exists){
        $item=Get-Item -LiteralPath $dir
        if(-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GUARD_WINDOWS_STATE_REPARSE_REJECTED'}
        $old=Get-Acl -LiteralPath $dir
        if($old.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'GUARD_WINDOWS_STATE_OWNER'}
        foreach($ace in $old.Access){
          $id=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
          if($ace.AccessControlType -eq 'Allow' -and $id -notin @('S-1-5-18','S-1-5-32-544') -and ([int]$ace.FileSystemRights -band 0xD0156)){throw 'GUARD_WINDOWS_STATE_WRITABLE'}
        }
      }else{New-Item -ItemType Directory -Path $dir|Out-Null}
      $acl=New-Object Security.AccessControl.DirectorySecurity
      $acl.SetOwner($owner);$acl.SetAccessRuleProtection($true,$false)
      foreach($sid in @('S-1-5-18','S-1-5-32-544')){
        $who=New-Object Security.Principal.SecurityIdentifier($sid)
        $rule=New-Object Security.AccessControl.FileSystemAccessRule($who,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
      }
      Set-Acl -LiteralPath $dir -AclObject $acl
    }
    foreach($p in Get-ChildItem -LiteralPath $StateDir -File){
      $fileAcl=New-Object Security.AccessControl.FileSecurity
      $fileAcl.SetOwner($owner);$fileAcl.SetAccessRuleProtection($true,$false)
      foreach($sid in @('S-1-5-18','S-1-5-32-544')){
        $who=New-Object Security.Principal.SecurityIdentifier($sid)
        $fileAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($who,'FullControl','Allow')))
      }
      Set-Acl -LiteralPath $p.FullName -AclObject $fileAcl
    }
  }elseif($Action -eq 'Snapshot'){Snapshot|ConvertTo-Json -Depth 30 -Compress}
  elseif($Action -eq 'Coverage'){[ordered]@{physical_interfaces=@(Get-NetAdapter -Physical -IncludeHidden|Select-Object -ExpandProperty Name|Sort-Object -Unique)}|ConvertTo-Json -Compress}
  elseif($Action -eq 'RecoveryReady'){
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if($sid -ne 'S-1-5-18'){throw 'GUARD_WINDOWS_RECOVERY_IDENTITY'}
    $state=Get-Content -LiteralPath (Join-Path $StateDir 'state.json') -Raw -Encoding UTF8|ConvertFrom-Json
    Save-PrivateJson (Join-Path $StateDir 'recovery-ready.json') ([ordered]@{nonce=$state.recovery_nonce;binding=$state.binding;sid=$sid})
  }
  elseif($Action -eq 'Validate'){Validate}
  elseif($Action -eq 'Arm'){Arm}
  elseif($Action -eq 'Apply'){Apply}
  elseif($Action -eq 'Restore'){Restore}
  elseif($Action -eq 'Persist'){} # Native NetSecurity is inherently persistent; confirmation cancels recovery.
  elseif($Action -eq 'Unpersist'){} # Restore changes only the exact baseline fields/rules in the journal.
  elseif($Action -eq 'Disarm'){Disarm}
  elseif($Action -eq 'Expire'){
    $state=Get-Content -LiteralPath (Join-Path $StateDir 'state.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if($state.phase -notin @('confirmed','restored','uninstalled')){
      # At startup always restore pending native persistent changes, even before the deadline.
      Restore
      $state.phase='restored';$state.persisted=$false
      Save-PrivateJson (Join-Path $StateDir 'state.json') $state
      Disarm
    }
  }
}finally{if($null -ne $mutex){$mutex.ReleaseMutex();$mutex.Dispose()};if($null -ne $stateLock){$stateLock.Unlock(0,1);$stateLock.Dispose()}}
