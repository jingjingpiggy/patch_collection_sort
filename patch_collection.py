#!/usr/bin/python
import os
import sys
import json
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
#    query_cmd = 'ssh {user}@icggerrit.ir.intel.com -p 29418 gerrit query '\
#                'status:open project:{project} branch:master '\
#                '--current-patch-set --format=JSON'.format(user=user_id, project=project)

    query_cmd = 'ssh {user}@icggerrit.ir.intel.com -p 29418 gerrit query '\
                'status:open project:{project} branch:sandbox/yocto_startup_1214 '\
                '--current-patch-set --format=JSON approver=1'.format(user=user_id, project=project)

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
        print 'No NEW patches in %s project on master branch, or ssh request '\
           'fails, please check.' % project
        sys.exit(1)

    return patches

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
            print "No patch %s found in dependencies list to be excluded" % num
    return all_deps

def boost_priority(all_deps, num1, num2):

    deps_1l, deps_1l_index = find_deps_l(all_deps, num1)
    deps_2l, deps_2l_index = find_deps_l(all_deps, num2)

    if not deps_1l:
        print "No patch %s found in dependencies list to be boosted" % num1
        sys.exit(1)

    if not deps_2l:
        print "No patch %s found in dependencies list to be boosted" % num2
        sys.exit(1)

    all_deps.pop(deps_2l_index)
    all_deps.insert(deps_1l_index, deps_2l)

    return all_deps

def cherry_pick(user_id, project, ref):
    conflict_F = False
    unmerged_F = False

    cherry_pick_cmd = 'git fetch '\
            'ssh://{user}@icggerrit.ir.intel.com:29418/{project} {ref} && git '\
            'cherry-pick -s FETCH_HEAD'.format(user=user_id, project=project, ref=ref)

    print "Start to cherry pick the patch: %s\n" % ref.split('/')[-2]

    popen = subprocess.Popen(cherry_pick_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output = popen.communicate()
    print output[0]

    if output[1].find('conflicts') != -1:
        conflict_F = True
    if output[1].find('unmerged files') != -1:
        unmerged_F = True

    if popen.returncode:
        print output[1]
        if conflict_F:
            print 'Patch %s cherry pick fails, there is conflictions.' % ref.split('/')[-2]
            return ref.split('/')[-2]
        elif unmerged_F:
            print 'Patch %s cherry pick fails, current repo is not clean, please '\
                 'check.' % (ref.split('/')[-2])
            sys.exit(1)
        else:
            print 'Patch %s cherry pick fails, please check reason.' % ref.split('/')[-2]
            sys.exit(1)

    return None

def push(topic):

    #push_cmd = "git push origin HEAD:refs/for/master/%s" % topic
    push_cmd = "git push origin HEAD:refs/for/sandbox/yocto_startup_1214/%s" % topic
    ret = os.system(push_cmd)
    if ret:
        print "Push patches to master branch fail."
        sys.exit(1)

def review_conflict_patches(user_id, conflict_patches, num):
    conflict_msg = 'Conflict with patch %s.' % num
    for i in conflict_patches:
        for j in i:
            review_cmd='ssh %s@icggerrit.ir.intel.com -p 29418 gerrit review %s -m "%s"' % (user_id, j.revision, conflict_msg)
            ret = os.system(review_cmd)
            if ret:
                print 'Give review comment fails'

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
        print "The username of gerrit and project are necessary, please refer to help."
        sys.exit(1)

    patchObjs = get_patch_info(args.name, args.project)

    if patchObjs:
        valued_patches = check_value(patchObjs)

    num_sorted_patches = big_bubble(valued_patches)

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

    conflict_patches = []
    for index, value in enumerate(all_deps):
        import ipdb;ipdb.set_trace()
        for i in value:
            conflict_p = cherry_pick(args.name, args.project, i.ref)
            if conflict_p:
                deps, index = find_deps_l(all_deps, conflict_p)
                conflict_patches.append(deps)
                ret = os.system('git reset --hard')
                if ret:
                    print "git reset fails"
                    sys.exit(1)
                break


    push(topic)
    if conflict_patches:
        review_conflict_patches(args.name, conflict_patches, value[-1].number)

    print ('Done')

