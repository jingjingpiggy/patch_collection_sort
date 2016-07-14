#!/usr/bin/python
import os
import json
import subprocess
user_id='jinjingx'
project='vied-viedandr-libcamhal'
patch_list='abc.json'
query_cmd = 'ssh {user}@icggerrit.ir.intel.com -p 29418 gerrit query status:open project:{project} branch:sandbox/yocto_startup_1214 --current-patch-set  --format=JSON > {file}'.format(user=user_id, project=project, file=patch_list)
#os.system(query_cmd)

import ipdb;ipdb.set_trace()
popen = subprocess.Popen(query_cmd, stdout=subprocess.PIPE, shell=True)
for line in popen.stdout.readlines():
    patch = json.loads(line)
    print patch
print popen.returncode
if popen.returncode:
    print "fail"
