#!/usr/bin/python
import os
import sys
import copy
import time
import json
import tempfile
import argparse
import subprocess

class Patch(object):

    def __init__(self, Id, number, current_patch, topic=None):
        self.topic = topic
        self.Id = Id
        self.number = number
        self._currentpatchset = current_patch

        if self._currentpatchset:
            self.ref = self._currentpatchset['ref']
            self.parents = self._currentpatchset['parents']
            self.revision = self._currentpatchset['revision']
            if self._currentpatchset.has_key('approvals'):
                self.approvals = self._currentpatchset['approvals']
            else:
                self.approvals = None

def get_patch_info(user_id, project):
    patches = []
    query_cmd = 'ssh {user}@icggerrit.ir.intel.com -p 29418 gerrit query status:open project:{project} branch:master --current-patch-set  --format=JSON'.format(user=user_id, project=project)

    popen = subprocess.Popen(query_cmd, stdout=subprocess.PIPE, shell=True)
    for i in popen.stdout.readlines():
        patch = json.loads(i)
        if patch.has_key('rowCount'):
            continue
        if patch.has_key('topic'):
            patchobj = Patch(patch['id'], patch['number'], patch['currentPatchSet'], patch['topic'])
        else:
            patchobj = Patch(patch['id'], patch['number'], patch['currentPatchSet'])
        patches.append(patchobj)

    if len(patches) == 0:
        print "No NEW patches in %s project on master branch, or ssh request fails, please check." % project
        sys.exit()

    return patches

def has_approver(patchobjs):
    filtered_patches = []
    for i in patchobjs:
        if i.approvals:
            for j in i.approvals:
                if j['type'] == "Approver":
                    filtered_patches.append(i)
                    break;

    return filtered_patches

def check_value(approver_patches):
    filtered = []

    for i in approver_patches:
        #print i.approvals
        for j in i.approvals:
            if j['type'] == "Code-Review" and j['value'] == str(-1):
                filtered.append(i)
                break
            if j['type'] == "Approver" and j['value'] == str(-1):
                filtered.append(i)
                break
            if j['type'] == "Validation-Android" and j['value'] == str(-1):
                filtered.append(i)
                break
            if j['type'] == "Validation-Linux" and j['value'] == str(-1):
                filtered.append(i)
                break

    for m in filtered:
        if m in approver_patches:
            approver_patches.remove(m)

    return approver_patches

def find_parents(all_deps, patch_l, obj):
    deps_l=[obj]
    f = False

    def get_patch_obj(patch_l, parent_str):
        for i in patch_l:
            if i.revision == parent_str:
                return i
        return None

    while obj:
        obj = get_patch_obj(patch_l, obj.parents)
        if obj:
            deps_l.insert(0, obj)

    if all_deps:
        for i in all_deps:
            if i[-1].revision == deps_l[0].parents:
                f = True
                for j in deps_l:
                    i.append(j)
    if not f:
        all_deps.append(deps_l)

    return all_deps, deps_l

def big_bubble():
    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i].number < f_list[i+1].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

def find_deps_l(all_deps, num):
    for deps in all_deps:
        for patchobj in deps:
            if patchobj.number == num:
                return deps, all_deps.index(deps)
    return None, None

def exclude_patches(all_deps, exclude_nums):
    for num in exclude_nums:
        deps_l, deps_l_index = find_deps_l(all_deps, num)
        if deps_l:
            for index, value in enumerate(deps_l):
                if value.number == num:
                    if index != 0:
                        new_deps_l = deps_l[:index]
                        all_deps.insert(int(deps_l_index), new_deps_l)
                        all_deps.remove(deps_l)
                    else:
                        all_deps.remove(deps_l)
        else:
            print "No patch %s found in dependencies list to be excluded" % num
    return all_deps

def boost_priority(all_deps, num1, num2):

    deps_1l, deps_1l_index = find_deps_l(all_deps, num1)
    deps_2l, deps_2l_index = find_deps_l(all_deps, num2)

    if not deps_1l:
        print "No patch %s found in dependencies list to be boosted" % num1
        sys.exit()

    if not deps_2l:
        print "No patch %s found in dependencies list to be boosted" % num2
        sys.exit()

    all_deps.pop(deps_2l_index)
    all_deps.insert(deps_1l_index, deps_2l)

    return all_deps

def cherry_pick(gerritName, projectName, refs):

    gerritobj = 'ssh://%s@icggerrit.ir.intel.com:29418/%s' % (gerritName, projectName)
    cmd = 'git fetch %s %s && git cherry-pick FETCH_HEAD' % (gerritobj, refs)

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    popen.communicate()[0]

    if popen.returncode:
        time.sleep(2)
        print "The patch that cherry pick fails: %s\n" % refs.split('/')[-2]
        sys.exit()

def parse_args():
    parser = argparse.ArgumentParser(description='Patch collection and sorting')
    parser.add_argument('-n', '--name', required=True, help='Username of gerrit')
    parser.add_argument('-p', '--project', required=True, help='Project name')
    parser.add_argument('-e', '--exclude', help='Number of patches to be excluded')
    parser.add_argument('-P', '--priority', help='Priority of patches number to be boosted')

    return parser.parse_args()

if __name__ == '__main__':
    filtered =[]
    args = parse_args()
    if not args.name or not args.project:
        print "The username of gerrit and project are necessary, please refer to help."
        sys.exit()

    patchObjs = get_patch_info(args.name, args.project)
    #print tmpfile
    #tmpfile = "/tmp/tmpaHh3lV"
    #tmpfile = "/tmp/tmpph3OJl"

    if patchObjs:
        import ipdb;ipdb.set_trace()
        approver_patches = has_approver(patchObjs)
        import ipdb;ipdb.set_trace()
        valued_patches = check_value(approver_patches)

    sorted_patches = big_bubble(valued_patches)

    all_deps = []
    while len(sorted_patches) >= 1:
        all_deps, deps_list = find_parents(all_deps, sorted_patches, sorted_patches[0])
        for i in deps_list:
            sorted_patches.remove(i)

    if args.exclude:
        exclude_nums = args.exclude.split(',')
        all_deps = exclude_patches(all_deps, exclude_nums)

    import ipdb;ipdb.set_trace()
    if args.priority:
        pri_list = args.priority.split(',')
        all_deps = boost_priority(all_deps, pri_list[0], pri_list[1])

    all_deps.reverse()

    for deps in all_deps:
        #import ipdb;ipdb.set_trace()
        for i in deps:
            cherry_pick(args.name, args.project, i.refs)
