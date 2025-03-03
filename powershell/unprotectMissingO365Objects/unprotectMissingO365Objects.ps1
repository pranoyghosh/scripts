### process commandline arguments
[CmdletBinding()]
param (
    [Parameter()][string]$vip = 'helios.cohesity.com',
    [Parameter()][string]$username = 'helios',
    [Parameter()][string]$domain = 'local',  # local or AD domain
    [Parameter()][switch]$useApiKey,
    [Parameter()][string]$password = $null,
    [Parameter()][switch]$mcm,
    [Parameter()][string]$mfaCode = $null,
    [Parameter()][switch]$emailMfaCode,
    [Parameter()][string]$clusterName = $null
)

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

### authenticate
apiauth -vip $vip -username $username -domain $domain -apiKeyAuthentication $useApiKey -mfaCode $mfaCode -sendMfaCode $emailMfaCode -heliosAuthentication $mcm -regionid $region

### select helios/mcm managed cluster
if($USING_HELIOS){
    if($clusterName){
        $thisCluster = heliosCluster $clusterName
    }else{
        write-host "Please provide -clusterName when connecting through helios" -ForegroundColor Yellow
        exit 1
    }
}

if(!$cohesity_api.authorized){
    Write-Host "Not authenticated"
    exit
}

$cluster = api get cluster
if($cluster.clusterSoftwareVersion -gt '6.8'){
    $environment = 'kO365OneDrive'
}else{
    $environment = 'kO365'
}
if($cluster.clusterSoftwareVersion -lt '6.6'){
    $entityTypes = 'kMailbox,kUser,kGroup,kSite,kPublicFolder'
}else{
    $entityTypes = 'kMailbox,kUser,kGroup,kSite,kPublicFolder,kO365Exchange,kO365OneDrive,kO365Sharepoint'
}

# get the protectionJob
$jobs = (api get -v2 "data-protect/protection-groups?environments=kO365")

# build source ID index
$sourceIdIndex = @{}
$lastCursor = 0

foreach($job in $jobs.protectionGroups | Sort-Object -Property name){
    $sourceId = $job.office365Params.sourceId
    if("$sourceId" -notin $sourceIdIndex.Keys){
        $sourceIdIndex["$sourceId"] = @()
        $rootSource = api get "protectionSources/rootNodes?environments=kO365&id=$sourceId"
        $sourceIdIndex[$sourceId] = @($sourceIdIndex[$sourceId] + $rootSource.protectionSource.id)
        $source = api get "protectionSources?id=$($rootSource.protectionSource.id)&excludeOffice365Types=$entityTypes&allUnderHierarchy=false"
        foreach($objectNode in $source.nodes){
            $sourceIdIndex[$sourceId] = @($sourceIdIndex[$sourceId] + $objectNode.protectionSource.id)
            Write-Host "`nDiscovering $($objectNode.protectionSource.office365ProtectionSource.name) from $($rootSource.protectionSource.name)"
            $objects = api get "protectionSources?pageSize=50000&nodeId=$($objectNode.protectionSource.id)&id=$($objectNode.protectionSource.id)&allUnderHierarchy=false&useCachedData=false"
            $cursor = $objects.entityPaginationParameters.beforeCursorEntityId
            while(1){
                foreach($node in $objects.nodes){
                    $sourceIdIndex[$sourceId] = @($sourceIdIndex[$sourceId] + $node.protectionSource.id)
                    $lastCursor = $node.protectionSource.id
                }
                Write-Host "    $(@($sourceIdIndex[$sourceId]).Count)"
                if($cursor){
                    $objects = api get "protectionSources?pageSize=50000&nodeId=$($objectNode.protectionSource.id)&id=$($objectNNode.protectionSource.id)&allUnderHierarchy=false&useCachedData=false&afterCursorEntityId=$cursor"
                    $cursor = $objects.entityPaginationParameters.beforeCursorEntityId
                }else{
                    break
                }
                # patch for 6.8.1
                if($objects.nodes -eq $null){
                    if($cursor -gt $lastCursor){
                        $node = api get protectionSources?id=$cursor
                        $sourceIdIndex[$sourceId] = @($sourceIdIndex[$sourceId] + $node.protectionSource.id)
                        $lastCursor = $node.protectionSource.id
                    }
                }
                if($cursor -eq $lastCursor){
                    break
                }
            }
        }
    }
}
Write-Host "`nReviewing Protection Groups...`n"

# updage protection groups
foreach($job in $jobs.protectionGroups | Sort-Object -Property name){
    $protectedCount = @($job.office365Params.objects).Count
    $job.office365Params.objects = @($job.office365Params.objects | Where-Object {$_.id -in $sourceIdIndex[$sourceId]})
    $newProtectedCount = @($job.office365Params.objects).Count
    if($newProtectedCount -lt $protectedCount){
        Write-Host  "    $($job.name) (updated)" -ForegroundColor Yellow
        $null = api put -v2 "data-protect/protection-groups/$($job.id)" $job
    }else{
        Write-Host "    $($job.name) (unchanged)"
    }
}
Write-Host ""

