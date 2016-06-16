#!/usr/bin/python
import os
import sys
import json
import argparse
import subprocess

class Color_Print(object):

    @staticmethod
    def red(cls):
        print "\033[1;31;40m%s \033[0m" % cls

    @staticmethod
    def green(cls):
        print "\033[1;32;40m%s \033[0m" % cls

    @staticmethod
    def yellow(cls):
        print "\033[1;33;40m%s \033[0m" % cls

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
    query_cmd = 'ssh {user}@icggerrit.ir.intel.com -p 29418 gerrit query '\
                'status:open project:{project} branch:master '\
                '--current-patch-set --format=JSON'.format(user=user_id, project=project)

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
        s ='No NEW patches in %s project on master branch, or ssh request '\
           'fails, please check.' % project
        Color_Print.red(s)
        sys.exit(1)

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

    def get_patch_obj(patch_l, parent):
        for i in patch_l:
            #print i.revision, parent[0]
            if i.revision == parent[0]:
                return i
        return None

    while obj:
        obj = get_patch_obj(patch_l, obj.parents)
        if obj:
            deps_l.insert(0, obj)

    if all_deps:
        for i in all_deps:
            if i[-1].revision == deps_l[0].parents[0]:
                f = True
                for j in deps_l:
                    i.append(j)
    if not f:
        all_deps.append(deps_l)

    return all_deps, deps_l

def big_bubble(f_list):
    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i].number < f_list[i+1].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

def search_topic(all_deps, num_sorted_patches, topic):
    topic_patches = []

    for i in num_sorted_patches:
        if i.topic == topic:
            topic_patches.append(i)

    if topic_patches:
        for j in topic_patches:
            num_sorted_patches.remove(i)

        all_deps, _ = find_parents(all_deps, topic_patches, topic_patches[0])
    return all_deps, num_sorted_patches

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
            s = "No patch %s found in dependencies list to be excluded" % num
            Color_Print.yellow(s)
    return all_deps

def boost_priority(all_deps, num1, num2):

    deps_1l, deps_1l_index = find_deps_l(all_deps, num1)
    deps_2l, deps_2l_index = find_deps_l(all_deps, num2)

    if not deps_1l:
        s = "No patch %s found in dependencies list to be boosted" % num1
        Color_Print.red(s)
        sys.exit(1)

    if not deps_2l:
        s = "No patch %s found in dependencies list to be boosted" % num2
        Color_Print.red(s)
        sys.exit(1)

    all_deps.pop(deps_2l_index)
    all_deps.insert(deps_1l_index, deps_2l)

    return all_deps

def cherry_pick(user_id, project, ref, prior_deps=None):
    conflict_F = False
    unmerged_F = False

    def get_prior_deps_num(prior_deps):
        prior_deps_num = []
        for i in prior_deps:
            prior_deps_num.append(i.number)
        return prior_deps_num

    cherry_pick_cmd = 'git fetch '\
            'ssh://{user}@icggerrit.ir.intel.com:29418/{project} {ref} && git '\
            'cherry-pick -s FETCH_HEAD'.format(user=user_id, project=project, ref=ref)

    s = "Start to cherry pick the patch: %s\n" % ref.split('/')[-2]
    Color_Print.green(s)

    popen = subprocess.Popen(cherry_pick_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output = popen.communicate()
    print output[0]

    if output[1].find('conflicts') != -1:
        conflict_F = True
    if output[1].find('unmerged files') != -1:
        unmerged_F = True

    if popen.returncode:
        Color_Print.yellow(output[1])
        if conflict_F:
            if prior_deps:
                prior_deps_num = get_prior_deps_num(prior_deps)
                s = 'Patch %s cherry pick fails, which conflicts with patches: '\
                    '%s  ' % (ref.split('/')[-2], prior_deps_num)
                Color_Print.red(s)
                sys.exit(1)
            else:
                s = 'Patch %s cherry pick fails, which conflicts with merged patches'
                Color_Print.red(s)
                sys.exit(1)
        elif unmerged_F:
            s = 'Patch %s cherry pick fails, current repo is not clean, please '\
                 'check.' % (ref.split('/')[-2])
            Color_Print.red(s)
            sys.exit(1)
        else:
            s = 'Patch %s cherry pick fails, please check reason.' % ref.split('/')[-2]
            Color_Print.red(s)
            sys.exit(1)

def push(topic):

    push_cmd = "git push origin HEAD:refs/for/master/%s" % topic
    ret = os.system(push_cmd)
    if ret:
        s = "Push patches to master branch fail."
        Color_Print.red(s)
        sys.exit(1)

def parse_args():
    parser = argparse.ArgumentParser(description='Patch collection and sorting')
    parser.add_argument('-n', '--name', required=True, help='Username of gerrit')
    parser.add_argument('-p', '--project', required=True, help='Project name')
    parser.add_argument('-e', '--exclude', help='Number of patches to be excluded')
    parser.add_argument('-P', '--priority', help='Priority of patches number to be boosted')

    return parser.parse_args()

if __name__ == '__main__':
    topic = 'linuxpatch'
    valued_patches =[]

    args = parse_args()
    if not args.name or not args.project:
        s = "The username of gerrit and project are necessary, please refer to help."
        Color_Print.red(s)
        sys.exit(1)

    patchObjs = get_patch_info(args.name, args.project)

    #if patchObjs:
    #    approver_patches = has_approver(patchObjs)
    #    valued_patches = check_value(approver_patches)
    #    #valued_patches = check_value(patchObjs)

    #num_sorted_patches = big_bubble(valued_patches)
    num_sorted_patches = big_bubble(patchObjs)

    all_deps = []
    all_deps, num_sorted_patches = search_topic(all_deps, num_sorted_patches, topic)

    while len(num_sorted_patches) >= 1:
        all_deps, deps_list = find_parents(all_deps, num_sorted_patches, num_sorted_patches[0])
        for i in deps_list:
            num_sorted_patches.remove(i)

    if args.exclude:
        exclude_nums = args.exclude.split(',')
        all_deps = exclude_patches(all_deps, exclude_nums)

    if args.priority:
        pri_list = args.priority.split(',')
        all_deps = boost_priority(all_deps, pri_list[0], pri_list[1])

    all_deps.reverse()

    for index, value in enumerate(all_deps):
        #import ipdb;ipdb.set_trace()
        for i in value:
            if index != 0:
                cherry_pick(args.name, args.project, i.ref, all_deps[index-1])
            else:
                cherry_pick(args.name, args.project, i.ref)


    #push(topic)
    Color_Print.green('Done')

