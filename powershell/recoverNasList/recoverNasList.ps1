# usage: ./recoverNasList.ps1 -vip mycluster -username admin -nasList .\nasList.txt

# process commandline arguments
[CmdletBinding()]
param (
    [Parameter()][string]$vip='helios.cohesity.com',
    [Parameter()][string]$username = 'helios',
    [Parameter()][string]$domain = 'local',
    [Parameter()][string]$tenant,
    [Parameter()][switch]$useApiKey,
    [Parameter()][string]$password,
    [Parameter()][switch]$noPrompt,
    [Parameter()][switch]$mcm,
    [Parameter()][string]$mfaCode,
    [Parameter()][switch]$emailMfaCode,
    [Parameter()][string]$clusterName,
    [Parameter()][array]$fullControl,                 # list of users to grant full control
    [Parameter()][array]$readWrite,                   # list of users to grant read/write
    [Parameter()][array]$readOnly,                    # list of users to grant read-only
    [Parameter()][array]$modify,                      # list of users to grant modify
    [Parameter()][string]$nasList = './naslist.txt'
)

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

# authenticate
apiauth -vip $vip -username $username -domain $domain -passwd $password -apiKeyAuthentication $useApiKey -mfaCode $mfaCode -sendMfaCode $emailMfaCode -heliosAuthentication $mcm -regionid $region -tenant $tenant -noPromptForPassword $noPrompt

# select helios/mcm managed cluster
if($USING_HELIOS -and !$region){
    if($clusterName){
        $thisCluster = heliosCluster $clusterName
    }else{
        write-host "Please provide -clusterName when connecting through helios" -ForegroundColor Yellow
        exit 1
    }
}

if(!$cohesity_api.authorized){
    Write-Host "Not authenticated"
    exit 1
}

$cluster = api get cluster

### get AD info
$ads = api get activeDirectory
$sids = @{}


function addPermission($user, $perms){
    if($user -eq 'Everyone'){
        $sid = 'S-1-1-0'
    }elseif($user.contains('\')){
        $workgroup, $user = $user.split('\')
        # find domain
        $adDomain = $ads | Where-Object { $_.workgroup -eq $workgroup -or $_.domainName -eq $workgroup}
        if(!$adDomain){
            write-host "domain $workgroup not found!" -ForegroundColor Yellow
            exit 1
        }else{
            # find domain princlipal/sid
            $domainName = $adDomain.domainName
            $principal = api get "activeDirectory/principals?domain=$($domainName)&includeComputers=true&search=$($user)"
            if(!$principal){
                write-host "user $($user) not found!" -ForegroundColor Yellow
            }else{
                $sid = $principal[0].sid
                $sids[$user] = $sid
            }
        }
    }else{
        # find local or wellknown sid
        $principal = api get "activeDirectory/principals?includeComputers=true&search=$($user)"
        if(!$principal){
            write-host "user $($user) not found!" -ForegroundColor Yellow
        }else{
            $sid = $principal[0].sid
            $sids[$user] = $sid
        }
    }
    #"visible" = $True;
    if($sid){
        $permission = @{       
            "sid" = $sid;
            "type" = "Allow";
            "mode" = "FolderOnly"
            "access" = $perms
        }
        return $permission
    }else{
        Write-Warning "User $user not found"
        exit 1
    }
}


# get input file
$nasListFile = Get-Content $nasList

foreach($shareName in $nasListFile){
    $shareName = [string]$shareName
    if($shareName -eq ''){
        continue
    }
    # find nas share to recover
    $shares = api get restore/objects?search=$shareName
    $exactShares = $shares.objectSnapshotInfo | Where-Object {$_.snapshottedSource.name -ieq $shareName}

    if(! $exactShares){
        write-host "Can't find $shareName - skipping..." -ForegroundColor Yellow
    }else{

        $newViewName = $shareName.split('\')[-1].split('/')[-1]

        # select latest snapshot to recover
        $latestsnapshot = ($exactShares | sort-object -property @{Expression={$_.versions[0].snapshotTimestampUsecs}; Ascending = $False})[0]

        # new view parameters
        $nasRecovery = @{
            "name" = "Recover-$shareName";
            "objects" = @(
                @{
                    "jobId" = $latestsnapshot.jobId;
                    "jobUid" = $latestsnapshot.jobUid;
                    "jobRunId" = $latestsnapshot.versions[0].jobRunId;
                    "startedTimeUsecs" = $latestsnapshot.versions[0].startedTimeUsecs;
                    "protectionSourceId" = $latestsnapshot.snapshottedSource.id
                }
            );
            "type" = "kMountFileVolume";
            "viewName" = $newViewName;
            "restoreViewParameters" = @{
                "qos" = @{
                    "principalName" = "TestAndDev High"
                }
            }
        }

        "Recovering $shareName as view $newViewName"

        # perform the recovery
        $result = api post restore/recover $nasRecovery

        if($result){

            # set post recovery view settings

            # apply share permissions
            $sharePermissionsApplied = $False
            $sharePermissions = @()

            foreach($user in $readWrite){
                $sharePermissionsApplied = $True
                $sharePermissions += addPermission $user 'ReadWrite'
                
            }
            
            foreach($user in $fullControl){
                $sharePermissionsApplied = $True
                $sharePermissions += addPermission $user 'FullControl'
            }
            
            foreach($user in $readOnly){
                $sharePermissionsApplied = $True
                $sharePermissions += addPermission $user 'ReadOnly'
            }
            
            foreach($user in $modify){
                $sharePermissionsApplied = $True
                $sharePermissions += addPermission $user 'Modify'
            }
            
            if($sharePermissionsApplied -eq $False){
                $sharePermissions += addPermission "Everyone" 'FullControl'
            }

            do {
                sleep 2
                $newView = (api get -v2 file-services/views).views | Where-Object { $_.name -eq $newViewName }
            } until ($newView)
            
            $newView | setApiProperty -name category -value 'FileServices'
            delApiProperty -object $newView -name nfsMountPaths
            $newView | setApiProperty -name enableSmbViewDiscovery -value $True
            delApiProperty -object $newView -name versioning
            if($cluster.clusterSoftwareVersion -gt '6.6'){
                $newView.sharePermissions | setApiProperty -name permissions -value $sharePermissions
            }else{
                $newView | setApiProperty -name sharePermissions -value @($sharePermissions)
            }
            if($smbOnly){
                $newView.protocolAccess = @(
                    @{
                        "type" = "SMB";
                        "mode" = "ReadWrite"
                    }
                )
            }
            $null = api put -v2 file-services/views/$($newView.viewId) $newView
        }
    }
}
