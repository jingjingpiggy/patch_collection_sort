#!/usr/bin/python
from Parser import Parser
import sys
import tempfile
import argparse
import subprocess

def get_patch_info_and_dump(gerritName, projectName):

    def dump(output, suffix='', prefix='tmp', dirn=None):
        tmpfile = tempfile.mkstemp(suffix, prefix, dirn)
        print tmpfile
        with open(tmpfile[1], 'w') as fobj:
            fobj.write(output)

        return tmpfile[1]

    gerritobj = '%s@icggerrit.ir.intel.com' % gerritName
    project = 'project:%s' % projectName
    #cmd = ['ssh', '-p', '29418', 'gerrit', 'query','status:NEW',
    #       'branch:sandbox/yocto_startup_1214', '--all-approvals']
    cmd = ['ssh', '-p', '29418', 'gerrit', 'query','status:NEW',
           'branch:master', '--all-approvals']
    cmd.insert(1, gerritobj)
    cmd.insert(6, project)

    output = ''
    popen = subprocess.Popen(subprocess.list2cmdline(cmd), stdout=subprocess.PIPE, shell=True)
    output = popen.communicate()[0]

    if not output:
        print "No unmerged patches on master branch in %s project." % projectName
        sys.exit()

    if popen.returncode:
        print "Get patches info from gerrit fail, please double check!"
        sys.exit()

    return dump(output)

def has_approval(patchobj_list):
    filtered_list = []
    for i in patchobj_list:
        if i.approvals:
            print i.approvals
            for j in i.approvals:
                if j['type'] == "Approver":
                    filtered_list.append(i)
                    break;

    return filtered_list

def check_value(patchobj_list):
    filtered_list = []

    for i in patchobj_list:
        print i.approvals
        for j in i.approvals:
            if j['type'] == "Code-Review" and j['value'] == str(-1):
                filtered_list.append(i)
                break
            if j['type'] == "Approver" and j['value'] == str(-1):
                filtered_list.append(i)
                break
            if j['type'] == "Validation-Android" and j['value'] == str(-1):
                filtered_list.append(i)
                break
            if j['type'] == "Validation-Linux" and j['value'] == str(-1):
                filtered_list.append(i)
                break

    for m in filtered_list:
        if m in patchobj_list:
            patchobj_list.remove(m)

    return patchobj_list

def find_parents(patch_l, obj):
    deps_l = [obj]
    def get_patch_obj(patch_l, parent_str):
        for i in patch_l:
            if i.revision == parent_str:
                return i
        return None

    while obj:
        obj = get_patch_obj(patch_l, obj.parents)
        if obj:
            deps_l.append(obj)
    return deps_l

def big_bubble(f_list):
    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i].number < f_list[i+1].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

def exclude_patches(all_l, num):

    def find_deps(all_l, num):
        for deps in all_l:
            for patchobj in deps:
                if patchobj.num == num:
                    return deps, all_l.index(deps)
        return None

    deps_l, deps_l_index = find_deps(all_l, num)
    if not deps_l:
        for index, value in enumerate(deps_l):
            if value == num:
                if index != 0:
                    new_deps_l = deps_l[:index]
                    all_l.insert(int(deps_l_index), new_deps_l)
                    all_l.remove(deps_l)
                else:
                    all_l.remove(deps_l)
    else:
        print "No patch %s found in dependencies list" % num
    return all_l


def cherry_pick(gerritName, projectName, refs):

    gerritobj = 'ssh://%s@icggerrit.ir.intel.com:29418/%s' % (gerritName, projectName)
    cmd = 'git fetch %s %s && git cherry-pick FETCH_HEAD' % (gerritobj, refs)

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    popen.communicate()[0]

    if popen.returncode:
        print "The patch that cherry pick fails: %s\n" % refs.split('/')[-2]
        #print popen.stderr
        sys.exit()

def parse_args():
    parser = argparse.ArgumentParser(description='Patch collection and sorting')
    parser.add_argument('-n', '--name', required=True, help='Username of gerrit')
    parser.add_argument('-p', '--project', required=True, help='Project name')
    parser.add_argument('-e', '--exclude', action='store_true', help='Number of patches to be excluded')
    parser.add_argument('-P', '--priority', action='store_true', help='Boost the priority of patches')

    return parser.parse_args()

if __name__ == '__main__':
    patchObjs = []
    filtered =[]
    args = parse_args()
    if not args.name or not args.project:
        print "The username of gerrit and project are necessary, please refer to help."
        sys.exit()
    tmpfile = get_patch_info_and_dump(args.name, args.project)
    #print tmpfile
    #tmpfile = "/tmp/tmp1"
    tmpfile = "/tmp/tmpaHh3lV"

    change_cmd = ["awk", '/change /{print NR}']
    change_cmd.append(tmpfile)

    changeline_num = subprocess.check_output(change_cmd)
    changeline_num = changeline_num.splitlines()

    lastline_cmd = ["awk", '/type: stats/{print NR}']
    lastline_cmd.append(tmpfile)
    lastline_num = subprocess.check_output(lastline_cmd).strip()

    for index, value in enumerate(changeline_num):
        patchobj = Parser(tmpfile)
        if value != changeline_num[-1]:
             patchobj._parse_changes(int(value), int(changeline_num[index+1]))
        else:
            patchobj._parse_changes(int(value), int(lastline_num)-1)
        patchObjs.append(patchobj)

    if patchObjs:
        #import ipdb;ipdb.set_trace()
        patchObjs = has_approval(patchObjs)
        filtered = check_value(patchObjs)

    big_sorted_l = big_bubble(filtered)

    all_deps = []
    while len(big_sorted_l) >= 1:
        deps_list = find_parents(big_sorted_l, big_sorted_l[0])
        all_deps.append(deps_list)
        for j in deps_list:
            big_sorted_l.remove(j)

    if args.exclude:
        all_deps = exclude_patches(all_deps, args.exclude)

    all_deps.reverse()

    for deps in all_deps:
        deps.reverse()
        #import ipdb;ipdb.set_trace()
        for i in deps:
            cherry_pick(args.name, args.projct, i.refs)
