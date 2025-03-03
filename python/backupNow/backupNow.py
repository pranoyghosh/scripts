#!/usr/bin/env python
"""BackupNow for python"""

# version 2023.03.29

# version history
# ===============
# 2023.01.10 - enforce sleeptimesecs >= 30 and newruntimeoutsecs >= 720
# 2023.02.17 - implement retry on get protectionJobs - added error code 7
# 2023.03.29 - version bump

# extended error codes
# ====================
# 0: Successful
# 1: Unsuccessful
# 2: connection/authentication error
# 3: Syntax Error
# 4: Timed out waiting for existing run to finish
# 5: Timed out waiting for status update
# 6: Timed out waiting for new run to appear
# 7: Timed out getting job

### usage: ./backupNow.py -v mycluster -u admin -j 'Generic NAS' [-r mycluster2] [-a S3] [-kr 5] [-ka 10] [-e] [-w] [-t kLog]

# import pyhesity wrapper module
from pyhesity import *
from time import sleep
from datetime import datetime
import codecs

# command line arguments
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--vip', type=str, default='helios.cohesity.com')
parser.add_argument('-v2', '--vip2', type=str, default=None)
parser.add_argument('-u', '--username', type=str, default='helios')
parser.add_argument('-d', '--domain', type=str, default='local')
parser.add_argument('-i', '--useApiKey', action='store_true')
parser.add_argument('-p', '--password', type=str, default=None)
parser.add_argument('-np', '--noprompt', action='store_true')
parser.add_argument('-mcm', '--mcm', action='store_true')
parser.add_argument('-c', '--clustername', type=str, default=None)
parser.add_argument('-j', '--jobName', type=str, required=True)
parser.add_argument('-j2', '--jobName2', type=str, default=None)
parser.add_argument('-y', '--usepolicy', action='store_true')
parser.add_argument('-l', '--localonly', action='store_true')
parser.add_argument('-nr', '--noreplica', action='store_true')
parser.add_argument('-na', '--noarchive', action='store_true')
parser.add_argument('-k', '--keepLocalFor', type=int, default=None)
parser.add_argument('-r', '--replicateTo', type=str, default=None)
parser.add_argument('-kr', '--keepReplicaFor', type=int, default=None)
parser.add_argument('-a', '--archiveTo', type=str, default=None)
parser.add_argument('-ka', '--keepArchiveFor', type=int, default=None)
parser.add_argument('-e', '--enable', action='store_true')
parser.add_argument('-w', '--wait', action='store_true')
parser.add_argument('-pr', '--progress', action='store_true')
parser.add_argument('-t', '--backupType', type=str, choices=['kLog', 'kRegular', 'kFull'], default='kRegular')
parser.add_argument('-o', '--objectname', action='append', type=str)
parser.add_argument('-m', '--metadatafile', type=str, default=None)
parser.add_argument('-x', '--abortifrunning', action='store_true')
parser.add_argument('-f', '--logfile', type=str, default=None)
parser.add_argument('-n', '--waitminutesifrunning', type=int, default=60)
parser.add_argument('-cp', '--cancelpreviousrunminutes', type=int, default=0)
parser.add_argument('-nrt', '--newruntimeoutsecs', type=int, default=1800)
parser.add_argument('-debug', '--debug', action='store_true')
parser.add_argument('-ex', '--extendederrorcodes', action='store_true')
parser.add_argument('-s', '--sleeptimesecs', type=int, default=120)
parser.add_argument('-es', '--exitstring', type=str, default=None)
parser.add_argument('-est', '--exitstringtimeoutsecs', type=int, default=120)
parser.add_argument('-sr', '--statusretries', type=int, default=10)

args = parser.parse_args()

vip = args.vip
vip2 = args.vip2
username = args.username
domain = args.domain
useApiKey = args.useApiKey
password = args.password
noprompt = args.noprompt
clustername = args.clustername
mcm = args.mcm
jobName = args.jobName
jobName2 = args.jobName2
keepLocalFor = args.keepLocalFor
replicateTo = args.replicateTo
keepReplicaFor = args.keepReplicaFor
archiveTo = args.archiveTo
keepArchiveFor = args.keepArchiveFor
enable = args.enable
wait = args.wait
backupType = args.backupType
objectnames = args.objectname
usepolicy = args.usepolicy
localonly = args.localonly
noreplica = args.noreplica
noarchive = args.noarchive
metadatafile = args.metadatafile
abortIfRunning = args.abortifrunning
logfile = args.logfile
waitminutesifrunning = args.waitminutesifrunning
cancelpreviousrunminutes = args.cancelpreviousrunminutes
newruntimeoutsecs = args.newruntimeoutsecs
debugger = args.debug
extendederrorcodes = args.extendederrorcodes
sleeptimesecs = args.sleeptimesecs
progress = args.progress
exitstring = args.exitstring
exitstringtimeoutsecs = args.exitstringtimeoutsecs
statusretries = args.statusretries

# enforce sleep time
if sleeptimesecs < 30:
    sleeptimesecs = 30

if newruntimeoutsecs < 720:
    newruntimeoutsecs = 720

if noprompt is True:
    prompt = False
else:
    prompt = None

if enable is True or progress is True:
    wait = True

if logfile is not None:
    try:
        log = codecs.open(logfile, 'w', 'utf-8')
        log.write('%s: Script started\n\n' % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        log.write('Command line parameters:\n\n')
        for arg, value in sorted(vars(args).items()):
            log.write("    %s: %s\n" % (arg, value))
        log.write('\n')
    except Exception:
        print('Unable to open log file %s' % logfile)
        exit(1)


def out(message, quiet=False):
    if quiet is not True:
        print(message)
    if logfile is not None:
        log.write('%s\n' % message)


def bail(code=0):
    if logfile is not None:
        log.close()
    exit(code)


if 'api_version' not in globals() or api_version < '2022.09.13':
    out('this script requires pyhesity.py version 2022.09.13 or later')
    if extendederrorcodes is True:
        bail(3)
    else:
        bail(1)

# authenticate
if mcm:
    apiauth(vip=vip, username=username, domain=domain, password=password, useApiKey=useApiKey, helios=True, prompt=prompt)
else:
    apiauth(vip=vip, username=username, domain=domain, password=password, useApiKey=useApiKey, prompt=prompt)

# if connected to helios or mcm, select to access cluster
if mcm or vip.lower() == 'helios.cohesity.com':
    if clustername is not None:
        heliosCluster(clustername)
    else:
        print('-clustername is required when connecting to Helios or MCM')
        exit()

if LAST_API_ERROR() != 'OK':
    out(LAST_API_ERROR(), quiet=True)
    if vip2 is None:
        if extendederrorcodes is True:
            bail(2)
        else:
            bail(1)

if apiconnected() is False and vip2 is not None:
    out('\nFailed to connect to %s. Trying %s...' % (vip, vip2))
    apiauth(vip=vip2, username=username, domain=domain, password=password, useApiKey=useApiKey)
    if jobName2 is not None:
        jobName = jobName2
    if LAST_API_ERROR() != 'OK':
        out(LAST_API_ERROR(), quiet=True)
        if extendederrorcodes is True:
            bail(2)
        else:
            bail(1)

if apiconnected() is False:
    out('\nFailed to connect to Cohesity cluster')
    if extendederrorcodes is True:
        bail(2)
    else:
        bail(1)

sources = {}
cluster = api('get', 'cluster')


# get object ID
def getObjectId(objectName):

    d = {'_object_id': None}

    def get_nodes(node):
        if 'name' in node:
            if node['name'].lower() == objectName.lower():
                d['_object_id'] = node['id']
                exit
        if 'protectionSource' in node:
            if node['protectionSource']['name'].lower() == objectName.lower():
                d['_object_id'] = node['protectionSource']['id']
                exit
        if 'nodes' in node:
            for node in node['nodes']:
                if d['_object_id'] is None:
                    get_nodes(node)
                else:
                    exit

    for source in sources:
        if d['_object_id'] is None:
            get_nodes(source)

    return d['_object_id']


def cancelRunningJob(job, durationMinutes):
    if durationMinutes > 0:
        durationUsecs = durationMinutes * 60000000
        nowUsecs = dateToUsecs(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cancelTime = nowUsecs - durationUsecs
        runningRuns = api('get', 'protectionRuns?jobId=%s&numRuns=10000&excludeTasks=true' % job['id'])
        if runningRuns is not None and len(runningRuns) > 0:
            for run in runningRuns:
                if 'backupRun' in run and 'status' in run['backupRun']:
                    if run['backupRun']['status'] not in finishedStates and 'stats' in run['backupRun'] and 'startTimeUsecs' in run['backupRun']['stats']:
                        if run['backupRun']['stats']['startTimeUsecs'] < cancelTime:
                            result = api('post', 'protectionRuns/cancel/%s' % job['id'], {"jobRunId": run['backupRun']['jobRunId']})
                            out('Canceling previous job run')


# find protectionJob
jobs = None
jobRetries = 0
while jobs is None:
    jobs = api('get', 'protectionJobs')
    if jobs is None or 'error' in jobs:
        jobs = None
        jobRetries += 1
        if jobRetries == 3:
            out('Timed out getting job!')
            if extendederrorcodes is True:
                bail(7)
            else:
                bail(1)
        else:
            sleep(15)

job = [job for job in jobs if job['name'].lower() == jobName.lower() and ('isActive' not in job or job['isActive'] is not False)]

if not job:
    out("Job '%s' not found" % jobName)
    if extendederrorcodes is True:
        bail(3)
    else:
        bail(1)
else:
    job = job[0]
    v2JobId = '%s:%s:%s' % (cluster['id'], cluster['incarnationId'], job['id'])
    environment = job['environment']
    if environment == 'kPhysicalFiles':
        environment = 'kPhysical'
    if environment not in ['kOracle', 'kSQL'] and backupType == 'kLog':
        out('BackupType kLog not applicable to %s jobs' % environment)
        if extendederrorcodes is True:
            bail(3)
        else:
            bail(1)
    if objectnames is not None:
        if environment in ['kOracle', 'kSQL']:
            backupJob = api('get', '/backupjobs/%s' % job['id'])
            backupSources = api('get', '/backupsources?allUnderHierarchy=false&entityId=%s&excludeTypes=5&includeVMFolders=true' % backupJob[0]['backupJob']['parentSource']['id'])
        if 'kAWS' in environment:
            sources = api('get', 'protectionSources?environments=kAWS')
        else:
            sources = api('get', 'protectionSources?environments=%s' % environment)

# handle run now objects
sourceIds = []
selectedSources = []
runNowParameters = []
if objectnames is not None:
    for objectname in objectnames:
        if environment == 'kSQL' or environment == 'kOracle':
            parts = objectname.split('/')
            if environment == 'kSQL':
                if len(parts) == 3:
                    (server, instance, db) = parts
                elif len(parts) == 2:
                    (server, instance) = parts
                    db = None
                else:
                    server = parts[0]
                    instance = None
                    db = None
            else:
                if len(parts) == 2:
                    (server, instance) = parts
                else:
                    server = parts[0]
                    instance = None
                    db = None

            serverObjectId = getObjectId(server)
            if serverObjectId is not None:
                if serverObjectId not in job['sourceIds']:
                    out("%s not protected by %s" % (server, jobName))
                    if extendederrorcodes is True:
                        bail(3)
                    else:
                        bail(1)
                if len([obj for obj in runNowParameters if obj['sourceId'] == serverObjectId]) == 0:
                    runNowParameters.append(
                        {
                            "sourceId": serverObjectId
                        }
                    )
                    selectedSources.append(serverObjectId)
                if instance is not None or db is not None:
                    if environment == 'kOracle' or environment == 'kSQL':  # and job['environmentParameters']['sqlParameters']['backupType'] in ['kSqlVSSFile', 'kSqlNative']):
                        for runNowParameter in runNowParameters:
                            if runNowParameter['sourceId'] == serverObjectId:
                                if 'databaseIds' not in runNowParameter:
                                    runNowParameter['databaseIds'] = []
                        if 'backupSourceParams' in backupJob[0]['backupJob']:
                            backupJobSourceParams = [p for p in backupJob[0]['backupJob']['backupSourceParams'] if p['sourceId'] == serverObjectId]
                            if backupJobSourceParams is not None and len(backupJobSourceParams) > 0:
                                backupJobSourceParams = backupJobSourceParams[0]
                            else:
                                backupJobSourceParams = None
                        else:
                            backupJobSourceParams = None
                        serverSource = [c for c in backupSources['entityHierarchy']['children'] if c['entity']['id'] == serverObjectId][0]
                        if environment == 'kSQL':
                            instanceSource = [i for i in serverSource['auxChildren'] if i['entity']['displayName'].lower() == instance.lower()][0]
                            if db is None:
                                dbSource = [c for c in instanceSource['children']]
                            else:
                                dbSource = [c for c in instanceSource['children'] if c['entity']['displayName'].lower() == '%s/%s' % (instance.lower(), db.lower())]
                            if dbSource is not None and len(dbSource) > 0:
                                for db in dbSource:
                                    if backupJobSourceParams is None or db['entity']['id'] in backupJobSourceParams['appEntityIdVec'] or instanceSource['entity']['id'] in backupJobSourceParams['appEntityIdVec']:
                                        runNowParameter['databaseIds'].append(db['entity']['id'])
                                    else:
                                        out('%s not protected by %s' % (objectname, jobName))
                                        if extendederrorcodes is True:
                                            bail(3)
                                        else:
                                            bail(1)
                            else:
                                out('%s not protected by %s' % (objectname, jobName))
                                if extendederrorcodes is True:
                                    bail(3)
                                else:
                                    bail(1)
                        else:
                            dbSource = [c for c in serverSource['auxChildren'] if c['entity']['displayName'].lower() == instance.lower()]
                            if dbSource is not None and len(dbSource) > 0:
                                for db in dbSource:
                                    if backupJobSourceParams is None or db['entity']['id'] in backupJobSourceParams['appEntityIdVec']:
                                        runNowParameter['databaseIds'].append(db['entity']['id'])
                            else:
                                out('%s not protected by %s' % (objectname, jobName))
                                if extendederrorcodes is True:
                                    bail(3)
                                else:
                                    bail(1)
                    else:
                        out("Job is Volume based. Can not selectively backup instances/databases")
                        if extendederrorcodes is True:
                            bail(3)
                        else:
                            bail(1)
            else:
                out('Object %s not found (server name)' % server)
                if extendederrorcodes is True:
                    bail(3)
                else:
                    bail(1)
        else:
            sourceId = getObjectId(objectname)
            if sourceId is not None:
                sourceIds.append(sourceId)
                selectedSources.append(sourceId)
            else:
                out('Object %s not found!' % objectname)
                if extendederrorcodes is True:
                    bail(3)
                else:
                    bail(1)

finishedStates = ['kCanceled', 'kSuccess', 'kFailure', 'kWarning', 'kCanceling', '3', '4', '5', '6', 'Canceled', 'Succeeded', 'Failed', 'SucceededWithWarning']

# job parameters (base)
jobData = {
    "copyRunTargets": [
        {
            "type": "kLocal",
            "daysToKeep": keepLocalFor
        }
    ],
    "sourceIds": [],
    "runType": backupType
}

# add objects (non-DB)
if sourceIds is not None:
    if metadatafile is not None:
        jobData['runNowParameters'] = []
        for sourceId in sourceIds:
            jobData['runNowParameters'].append({"sourceId": sourceId, "physicalParams": {"metadataFilePath": metadatafile}})
    else:
        jobData['sourceIds'] = sourceIds

# add objects (DB)
if len(runNowParameters) > 0:
    jobData['runNowParameters'] = runNowParameters

# use base retention and copy targets from policy
policy = api('get', 'protectionPolicies/%s' % job['policyId'])
if keepLocalFor is None:
    jobData['copyRunTargets'][0]['daysToKeep'] = policy['daysToKeep']

# replication
if localonly is not True and noreplica is not True:
    if 'snapshotReplicationCopyPolicies' in policy and replicateTo is None:
        for replica in policy['snapshotReplicationCopyPolicies']:
            if replica['target'] not in [p.get('replicationTarget', None) for p in jobData['copyRunTargets']]:
                if keepReplicaFor is not None:
                    replica['daysToKeep'] = keepReplicaFor
                jobData['copyRunTargets'].append({
                    "daysToKeep": replica['daysToKeep'],
                    "replicationTarget": replica['target'],
                    "type": "kRemote"
                })
# archival
if localonly is not True and noarchive is not True:
    if 'snapshotArchivalCopyPolicies' in policy and archiveTo is None:
        for archive in policy['snapshotArchivalCopyPolicies']:
            if archive['target'] not in [p.get('archivalTarget', None) for p in jobData['copyRunTargets']]:
                if keepArchiveFor is not None:
                    archive['daysToKeep'] = keepArchiveFor
                jobData['copyRunTargets'].append({
                    "archivalTarget": archive['target'],
                    "daysToKeep": archive['daysToKeep'],
                    "type": "kArchival"
                })

# use copy targets specified at the command line
if replicateTo is not None:
    if keepReplicaFor is None:
        out("--keepReplicaFor is required")
        if extendederrorcodes is True:
            bail(3)
        else:
            bail(1)
    remote = [remote for remote in api('get', 'remoteClusters') if remote['name'].lower() == replicateTo.lower()]
    if len(remote) > 0:
        remote = remote[0]
        jobData['copyRunTargets'].append({
            "type": "kRemote",
            "daysToKeep": keepReplicaFor,
            "replicationTarget": {
                "clusterId": remote['clusterId'],
                "clusterName": remote['name']
            }
        })
    else:
        out("Remote Cluster %s not found!" % replicateTo)
        if extendederrorcodes is True:
            bail(3)
        else:
            bail(1)

if archiveTo is not None:
    if keepArchiveFor is None:
        out("--keepArchiveFor is required")
        if extendederrorcodes is True:
            bail(3)
        else:
            bail(1)
    vault = [vault for vault in api('get', 'vaults') if vault['name'].lower() == archiveTo.lower()]
    if len(vault) > 0:
        vault = vault[0]
        jobData['copyRunTargets'].append({
            "archivalTarget": {
                "vaultId": vault['id'],
                "vaultName": vault['name'],
                "vaultType": "kCloud"
            },
            "daysToKeep": keepArchiveFor,
            "type": "kArchival"
        })
    else:
        out("Archive target %s not found!" % archiveTo)
        if extendederrorcodes is True:
            bail(3)
        else:
            bail(1)

# get last run ID
runs = api('get', 'data-protect/protection-groups/%s/runs?numRuns=1&includeObjectDetails=false' % v2JobId, v=2)
if runs is not None and 'runs' in runs and len(runs['runs']) > 0:
    newRunId = lastRunId = runs['runs'][0]['protectionGroupInstanceId']
else:
    newRunId = lastRunId = 1

# run protectionJob
now = datetime.now()
nowUsecs = dateToUsecs(now.strftime("%Y-%m-%d %H:%M:%S"))
startUsecs = dateToUsecs(now.strftime("%Y-%m-%d %H:%M:%S"))
waitUntil = nowUsecs + (waitminutesifrunning * 60000000)
reportWaiting = True
if debugger:
    print(':DEBUG: waiting for new run to be accepted')
runNow = api('post', "protectionJobs/run/%s" % job['id'], jobData, quiet=True)
while runNow != "":
    if cancelpreviousrunminutes > 0:
        cancelRunningJob(job, cancelpreviousrunminutes)
    if reportWaiting is True:
        if abortIfRunning:
            out('job is already running')
            bail(0)
        out('Waiting for existing run to finish')
        reportWaiting = False
    now = datetime.now()
    nowUsecs = dateToUsecs(now.strftime("%Y-%m-%d %H:%M:%S"))
    if nowUsecs >= waitUntil:
        out('Timed out waiting for existing run')
        if extendederrorcodes is True:
            bail(4)
        else:
            bail(1)
    sleep(sleeptimesecs)
    if debugger:
        runNow = api('post', "protectionJobs/run/%s" % job['id'], jobData)
    else:
        runNow = api('post', "protectionJobs/run/%s" % job['id'], jobData, quiet=True)
out("Running %s..." % jobName)

# wait for new job run to appear
if wait is True:
    timeOutUsecs = dateToUsecs(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    while newRunId <= lastRunId:
        sleep(15)
        if len(selectedSources) > 0:
            runs = api('get', 'data-protect/protection-groups/%s/runs?numRuns=10&includeObjectDetails=true' % v2JobId, v=2)
            if runs is not None and 'runs' in runs and len(runs['runs']) > 0:
                runs = [r for r in runs['runs'] if selectedSources[0] in [o['object']['id'] for o in r['objects']]]
        else:
            runs = api('get', 'data-protect/protection-groups/%s/runs?numRuns=1&includeObjectDetails=false' % v2JobId, v=2)
            if runs is not None and 'runs' in runs and len(runs['runs']) > 0:
                runs = runs['runs']
        if runs is not None and len(runs) > 0:
            newRunId = runs[0]['protectionGroupInstanceId']
            v2RunId = runs[0]['id']
        if debugger:
            print(':DEBUG: Previous Run ID: %s' % lastRunId)
            print(':DEBUG:   Latest Run ID: %s\n' % newRunId)
        # timeout waiting for new run to appear
        nowUsecs = dateToUsecs(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if (timeOutUsecs + (newruntimeoutsecs * 1000000)) < nowUsecs:
            out("Timed out waiting for new run to appear")
            if extendederrorcodes is True:
                bail(6)
            else:
                bail(1)
        if newRunId > lastRunId:
            break
        sleep(sleeptimesecs)
    out("New Job Run ID: %s" % v2RunId)

# wait for job run to finish and report completion
if wait is True:
    status = 'unknown'
    lastProgress = -1
    statusRetryCount = 0
    while status not in finishedStates:
        x = 0
        s = 0
        sleep(15)
        try:
            if exitstring:
                run = api('get', 'data-protect/protection-groups/%s/runs/%s?includeObjectDetails=true' % (v2JobId, v2RunId), v=2)
            else:
                run = api('get', 'data-protect/protection-groups/%s/runs/%s?includeObjectDetails=false' % (v2JobId, v2RunId), v=2)
            status = run['localBackupInfo']['status']
            if exitstring:
                while x < len(run['objects']) and s < exitstringtimeoutsecs:
                    sleep(15)
                    s += 15
                    if s > exitstringtimeoutsecs:
                        break
                    x = 0
                    try:
                        progressPath = run['localBackupInfo']['progressTaskId']
                        taskMon = api('get', '/progressMonitors?taskPathVec=%s' % progressPath)
                        sources = taskMon['resultGroupVec'][0]['taskVec'][0]['subTaskVec']
                        for source in sources:
                            if source['taskPath'] != 'post_processing':
                                # get pulse log messages
                                eventmsgs = source['progress']['eventVec']
                                foundkeystring = False
                                # check for key string in event messages
                                for eventmsg in eventmsgs:
                                    if exitstring in eventmsg['eventMsg']:
                                        foundkeystring = True
                                if foundkeystring is True:
                                    x += 1
                                else:
                                    preprocessFinished = False
                    except Exception:
                        pass
                    if x >= len(run['objects']):
                        print('*** SUCCESSFUL STRING MATCH')
                        exit(0)
                if x < len(run['objects']):
                    print('*** TIMED OUT WAITING FOR STRING MATCH')
                    exit(1)
            if progress and lastProgress < 100 and 'progressTaskId' in run['localBackupInfo']:
                sleep(15)
                progressPath = run['localBackupInfo']['progressTaskId']
                progressMonitor = api('get', '/progressMonitors?taskPathVec=%s&excludeSubTasks=true&includeFinishedTasks=false' % progressPath)
                progressTotal = progressMonitor['resultGroupVec'][0]['taskVec'][0]['progress']['percentFinished']
                percentComplete = int(round(progressTotal))
                if percentComplete > lastProgress:
                    out('%s%% completed' % percentComplete)
                    lastProgress = percentComplete
            statusRetryCount = 0
        except Exception:
            statusRetryCount += 1
            if debugger:
                ":DEBUG: error getting updated status"
            else:
                pass
            if statusRetryCount > statusretries:
                out("Timed out waiting for status update")
                if extendederrorcodes is True:
                    bail(5)
                else:
                    bail(1)
        if status not in finishedStates:
            sleep(sleeptimesecs)
    out("Job finished with status: %s" % run['localBackupInfo']['status'])
    if run['localBackupInfo']['status'] == 'Failed':
        out('Error: %s' % run['localBackupInfo']['messages'][0])
    if run['localBackupInfo']['status'] == 'SucceededWithWarning':
        out('Warning: %s' % run['localBackupInfo']['messages'][0])

# return exit code
if wait is True:
    if logfile is not None:
        try:
            log.write('Backup ended %s\n' % usecsToDate(run['localBackupInfo']['endTimeUsecs']))
        except Exception:
            log.write('Backup ended')
    if run['localBackupInfo']['status'] == 'Succeeded' or run['localBackupInfo']['status'] == 'SucceededWithWarning':
        bail(0)
    else:
        bail(1)
else:
    bail(0)
