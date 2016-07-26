#!/usr/bin/python
import os
import sys
import json
import time
import argparse
import subprocess

class Patch(object):
    """Wrap patch object"""

    def __init__(self, Id, number, current_patch, owner, topic=None):
        self.topic = topic
        self.Id = Id
        self.number = number
        self._currentpatchset = current_patch
        self.owner = owner

        if self._currentpatchset:
            self.ref = self._currentpatchset['ref']
            self.parents = self._currentpatchset['parents']
            self.revision = self._currentpatchset['revision']
            if self._currentpatchset.has_key('approvals'):
                self.approvals = self._currentpatchset['approvals']
            else:
                self.approvals = None

def get_patch_info(user_id, project):
    """Get info of qualified(approver=1) patches from gerrit"""

    patches = []
    query_cmd = 'ssh {user}@icggerrit.corp.intel.com -p 29418 gerrit query status:open project:{project} branch:master --current-patch-set --format=JSON approver=1'.format(user=user_id, project=project)

    popen = subprocess.Popen(query_cmd, stdout=subprocess.PIPE, shell=True)
    for i in popen.stdout.readlines():
        patch = json.loads(i)
        if patch.has_key('rowCount'):
            continue
        if patch.has_key('topic'):
            patchobj = Patch(patch['id'], patch['number'], patch['currentPatchSet'], patch['owner'], patch['topic'])
        else:
            patchobj = Patch(patch['id'], patch['number'], patch['currentPatchSet'], patch['owner'])
        patches.append(patchobj)

    if len(patches) == 0:
        print 'No NEW patches in %s project on master branch, or ssh request fails, please check.' % project
        sys.exit(0)

    return patches

def check_value(approver_patches):
    """Filter patches by code-review and approver"""

    filtered = []

    for i in approver_patches:
        is_approval = False
        if i.approvals:
            for j in i.approvals:
                if j['type'] == "Code-Review" and j['value'] == str(-1):
                    filtered.append(i)
                    break
                if j['type'] == "Approver" and j['value'] == str(-1):
                    filtered.append(i)
                    break
                if j['type'] == "Approver" and j['value'] == str(1):
                    is_approval = True
        else:
            filtered.append(i)

        if not is_approval:
            filtered.append(i)

    for m in filtered:
        if m in approver_patches:
            approver_patches.remove(m)

    return approver_patches

def find_parents(all_deps, patch_l, obj):
    """Resolve patch dependencies according to patch revision"""

    deps_l=[obj]
    f = False

    def get_patch_obj(patch_l, revision):
        for i in patch_l:
            if i.parents[0] == revision:
                return i
        return None

    while obj:
        obj = get_patch_obj(patch_l, obj.revision)
        if obj:
            deps_l.append(obj)

    # all_deps = [[], [], []]
    # all_deps[n]-> deps_l    [[],[,deps_l],[]]
    # deps_l <- all_deps[n]   [[], [deps_l, []], []]
    if all_deps:
        for i in all_deps:
            if i[-1].revision == deps_l[0].parents[0]:
                f = True
                for j in deps_l:
                    i.append(j)
            elif i[0].parents[0] == deps_l[-1].revision:
                f = True
                deps_l.reverse()
                for j in deps_l:
                    i.insert(0, j)

    if not f:
        all_deps.append(deps_l)

    return all_deps, deps_l

def small_bubble(f_list):
    """Sort(small_bubble) patches according to patch number."""

    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i].number > f_list[i+1].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

def find_deps_l(all_deps, num):
    """
    Find patches series from all_deps
    @param all_deps: [[], [],...]
    @return: deps:[], index of deps in all_deps
    """
    for deps in all_deps:
        for patchobj in deps:
            if patchobj.number == num:
                return deps, all_deps.index(deps)
    return None, None

def find_patch(first_deps, topic_patches, all_deps):
    """Find patch obj from first_deps, topic_patches and all_deps"""

    current_head = get_current_head()
    patch_num = []

    def find(deps):
        for dep in deps:
            if patch_num:
                break
            if type(dep) == type([]):
                for i in dep:
                    if i.revision == current_head:
                        patch_num.append(i.number)
                        break
            else:
                if dep.revision == current_head:
                    patch_num.append(dep.number)
                    break

    if first_deps:
        find(first_deps)
    if topic_patches:
        find(topic_patches)
    if all_deps:
        find(all_deps)

    if patch_num:
        return patch_num[0]
    else:
        return None

def exclude_patches(all_deps, exclude_nums):
    """
    Exclude patch from all_deps according to patch num.
    all_deps: [[a,b],[c,d,e],[f,j]]
    Result: [[c,d,e],[f,j]] or [[b],[c,d,e],[f,j]]
    """
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
    """Boost patch priority in all_deps,
    then cherry pick(out) order will be changed"""

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

def cherry_and_collect(args, deps, successful_s, conflict_s):
    """
    Cherry pick patch ony by one from deps, sort them out according to
    result of cherry pick.
    @Result: two collect lists
    """

    for i in deps:
        print 'Cherry pick patch: ' + i.ref
        if not cherry_pick(args.name, args.project, i.ref):
            conflict_s.add(i)
            ret = os.system('git reset --hard')
            if ret:
                print "git reset fails"
            break
        else:
            successful_s.add(i)
    return successful_s, conflict_s

def pull_patches(args, topic_patches, first_deps, current_head, successful_s, conflict_s):
    """
    Cherry out(pick) patches from gerrit to local.
    1) topic_patches: based on master---[[check out], [cherry pick]]
                      not based on master --- [[cherry pick],[cherry pick]...]
                      collect result
    2) first_deps: [check out, cherry pick....]
    """

    if topic_patches:
        if topic_patches[0][0].parents[0] == current_head:
            print "Start to check out the topic patches %s." % topic_patches[0][-1].number
            check_out_cmd = 'git fetch ssh://%s@icggerrit.corp.intel.com:29418/%s %s && git checkout FETCH_HEAD' % (args.name, args.project, topic_patches[0][-1].ref)
            ret = os.system(check_out_cmd)
            if ret:
                print "check out topic patches fail"
            else:
                for patch in topic_patches[0]:
                    successful_s.add(patch)
        else:
            for topics in topic_patches:
                successful_s, conflict_s = cherry_and_collect(args, topics, successful_s, conflict_s)

        if topic_patches[1:]:
            for other in topic_patches[1:]:
                successful_s, conflict_s = cherry_and_collect(args, other, successful_s, conflict_s)

    #Only the useful for script running for the first time
    elif first_deps:
        print "Start to check out the first patch %s of first dependent patch series." % first_deps[0].number
        check_out_cmd = 'git fetch ssh://%s@icggerrit.corp.intel.com:29418/%s %s && git checkout FETCH_HEAD' % (args.name, args.project, first_deps[0].ref)
        ret = os.system(check_out_cmd)
        if ret:
            print "check out first patch fail"
        else:
            successful_s.add(first_deps[0])

        if first_deps[1:]:
            print "Start to cherry other patches of first dependent patch series."
            successful_s, conflict_s = cherry_and_collect(args, first_deps[1:], successful_s, conflict_s)

    return successful_s, conflict_s

def cherry_pick(user_id, project, ref):
    conflict_F = False
    unmerged_F = False

    cherry_pick_cmd = 'git fetch ssh://{user}@icggerrit.corp.intel.com:29418/{project} {ref} && git cherry-pick -s FETCH_HEAD'.format(user=user_id, project=project, ref=ref)

    print "Start to cherry pick the patch: %s\n" % ref.split('/')[-2]

    popen = subprocess.Popen(cherry_pick_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output = popen.communicate()
    print output[0]

    if output[1].find('conflicts') != -1:
        conflict_F = True
    if output[1].find('unmerged files') != -1:
        unmerged_F = True

    #Currently, exit in two circumstance
    if popen.returncode:
        print output[1]
        if conflict_F:
            print 'Patch %s cherry pick fails, there is conflictions.' % ref.split('/')[-2]
            return False
        elif unmerged_F:
            print 'Patch %s cherry pick fails, current repo is not clean, please check.' % (ref.split('/')[-2])
            sys.exit(1)
        else:
            print 'Patch %s cherry pick fails, please check reason.' % ref.split('/')[-2]
            sys.exit(1)
    else:
        return True

def push(name, project, topic):
    """Push local patche in series to gerrit with topic name"""

    print "Delete master_backup branch"
    ret = os.system('git branch -D master_backup')
    if ret:
        print "Delete master_backup branch fails."

    print "Create new master_branchup branch"
    ret = os.system("git checkout -b master_backup")
    if ret:
        print "Checkout new master_backup branch fails."

    push_cmd = "git push ssh://%s@icggerrit.corp.intel.com:29418/%s HEAD:refs/for/master/%s" % (name, project, topic)
    print "push_cmd: %s" % push_cmd
    ret = os.system(push_cmd)
    if ret:
        print "Push patches to master branch fail."
        return False

    return True

def review_conflict_patches(user_id, conflict_s, conflict_buf):
    """
    Review confilct patches with comment and code-review -1,
    the head conflict with is current series head"""

    for key, value in conflict_buf.iteritems():
        for obj in conflict_s:
            if obj.number == key:
                review_cmd='ssh %s@icggerrit.corp.intel.com -p 29418 gerrit review %s --code-review -1' % (user_id, obj.revision)
                if value:
                    msg_cmd='ssh %s@icggerrit.corp.intel.com -p 29418 gerrit review %s -m "\'Conflict with patch %s.\'"' % (user_id, obj.revision, value)
                else:
                    msg_cmd='ssh %s@icggerrit.corp.intel.com -p 29418 gerrit review %s -m "\'Conflict with master.\'"' % (user_id, obj.revision)

                print "Give code review -1 onto gerrit for %s" % obj.number
                ret = os.system(review_cmd)
                if ret:
                    print 'Give review comment fails'

                print "Give conflict comment onto gerrit for %s" % obj.number
                ret = os.system(msg_cmd)
                if ret:
                    print 'Give message comment fails'

def get_current_head():
    cmd = "git log --pretty=oneline  -1"
    p = os.popen(cmd)
    for i in p.readlines():
        return i.split(' ')[0]

def find_first_and_topic_deps(all_deps, current_head, topic):
    """
    Find first and topic patch deps from all_deps
    all_deps -> first:[] + topic:[] + rest[]"""

    first_deps = []
    topic_patches_l = []

    for deps in all_deps:
        for patch in deps:
            if patch.topic == topic:
                topic_patches_l.append(deps)
                break

    #Remove topic patches from all_deps
    if topic_patches_l:
        for topic in topic_patches_l:
            all_deps.remove(topic)

    else:
        #Find first deps which include the first patch that depend on the current master
        for deps in all_deps:
            if deps[0].parents[0] == current_head:
                first_deps = deps
                all_deps.remove(deps)
                break

    return first_deps, topic_patches_l, all_deps

def get_current_revision(number):
    cmd = "ssh -p 29418 icggerrit.corp.intel.com gerrit query --current-patch-set --format=JSON %s" % number
    pipe = os.popen(cmd)
    jsonStr = pipe.readlines()
    pipe.close()

    jsonData = json.loads(jsonStr[0])
    revision = jsonData.get("currentPatchSet").get("revision")
    return revision

def autoreview(first, successful_s):
    """Review patches with code-reivew +1 and approver +1 """

    approvers = ['liuxiaoz', 'lyang56']

    def review_action(patches_l):
        for patch in patches_l:
            id_index = 0
            for index,value in enumerate(approvers):
                if value == patch.owner['username']:
                    if index == 0:
                        id_index = index + 1
                    else:
                        pass

            # Because after push function, revision on gerrit has been changed, which isnot the one queried by get_patch_info function
            revision = get_current_revision(patch.number)
            print "revision: %s" % revision
            autoreview_cmd = 'ssh %s@icggerrit.corp.intel.com -p 29418 gerrit review %s --code-review +1 --approver +1' % (approvers[id_index], revision)

            print "autoreview_cmd: %s" % autoreview_cmd
            print "Give code review +1 and approver +1 onto gerrit for patch %s" % patch.number
            ret = os.system(autoreview_cmd)
            if ret:
                print "Autoreview patch %s fails" % patch.number

    review_action(first)
    review_action(successful_s)

def parse_args():
    """Parse command"""

    parser = argparse.ArgumentParser(description='Patch collection and sorting')
    parser.add_argument('-n', '--name', required=True, help='Username of gerrit')
    parser.add_argument('-p', '--project', required=True, help='Project name')
    parser.add_argument('-e', '--exclude', help='Number of patches to be excluded')
    parser.add_argument('-P', '--priority', help='Priority of patches number to be boosted')

    return parser.parse_args()

if __name__ == '__main__':
    topic = 'linux_camhal_preint'
    valued_patches =[]

    args = parse_args()
    if not args.name or not args.project:
        print "The username of gerrit and project are necessary, please refer to help."
        sys.exit(1)

    current_head = get_current_head()

    print "===Wrap patch objects.==="
    patchObjs = get_patch_info(args.name, args.project)

    if patchObjs:
        valued_patches = check_value(patchObjs)
        for patch in valued_patches:
            print patch.number
        if not valued_patches:
            print "No patches need to be rebased..."
            sys.exit(0)

    print "===Sort the patches according to patch number.==="
    num_sorted_patches = small_bubble(valued_patches)

    print "===Resolve dependencies of patches.==="
    all_deps = []

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

    print "===Find first(depend on master patches) or topic patches.==="
    first_deps, topic_patches, all_deps = find_first_and_topic_deps(all_deps, current_head, topic)

    #Avoid of being on other branches(should on master branch)
    print "===Delete maser branch==="
    ret = os.system('git branch -D master')
    if ret:
        print "Delete master branch fails."

    print "===Checkout to master branch==="
    ret = os.system('git checkout -b master')
    if ret:
        print "Checkout to master branch fails."

    #Patch the patches(from gerrit) locally
    successful_s = set()
    conflict_s = set()
    print "===Start to checkout and cherry pick topic or first patches.==="
    successful_s, conflict_s = pull_patches(args, topic_patches, first_deps, current_head, successful_s, conflict_s)

    for deps in all_deps:
        successful_s, conflict_s = cherry_and_collect(args, deps, successful_s, conflict_s)

    print "===Push local patch series to gerrit.==="
    push_result = push(args.name, args.project, topic)

    if push_result:
        time.sleep(5)
        print "===Autoreview for pushed patch series on gerrit .==="
        autoreview(first_deps, successful_s)

        if conflict_s:
            conflict_buf = {}
            print "===Autoreview for conflict patches on gerrit.==="
            patch_num = find_patch(first_deps, topic_patches, all_deps)
            if patch_num:
                conflict_buf[i.number] = patch_num
            else:
                conflict_buf[i.number] = None

            review_conflict_patches(args.name, conflict_s, conflict_buf)

    print ('Done')
