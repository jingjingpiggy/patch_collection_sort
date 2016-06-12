#!/usr/bin/python
import os
import linecache
import subprocess
import tempfile

def get_patch_info_from_gerrit(gerritName, projectName):

    def dump_patch_info(output, suffix='', prefix='tmp', dirn=None):
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

    popen = subprocess.Popen(subprocess.list2cmdline(cmd), stdout=subprocess.PIPE, shell=True)

    output = popen.communicate()[0]
    if popen.returncode:
        raise

    return dump_patch_info(output)

def cherry_pick(gerritName, projectName, refs):

    gerritobj = 'ssh://%s@icggerrit.ir.intel.com:29418/%s' % (gerritName, projectName)
#    cmd = 'git fetch %s %s && git cherry-pick FETCH_HEAD' % (gerritobj, refs)
    cmd = 'git fetch %s %s && git checkout FETCH_HEAD' % (gerritobj, refs)

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    output = popen.communicate()[0]

    if popen.returncode:
        print "The patch cherry pick fails: %s\n" % refs.split('/')[-2]
        print output.stderr

class Parse(object):

    def __init__(self, filename):
        self.tmpfile = filename
        self.url = None
        self.refs = None
        self.parents = None
        self.revision = None
        self.project = None
        self.branch = None
        self.changeId = None
        self.number = None
        self.approvals = []

    def __parse_approvals(self, num1, num2):
        approvals = []
        approvals_cmd = ["awk", '/approvals:/{print NR}']
        approvals_cmd.append(self.tmpfile)

        approvals_linenum = subprocess.check_output(approvals_cmd)
        approvals_linenum = approvals_linenum.splitlines()

        def func(approvals_list):
            approval = {}
            for n in approvals_list:
                if n.find("type") != -1:
                    approval[n.split(':')[0]] = n.split(':')[1].lstrip()
                if n.find("value") != -1:
                    approval[n.split(':')[0]] = n.split(':')[1].lstrip()
            return approval

        for index, value in enumerate(approvals_linenum):
            with open(self.tmpfile, 'r') as fd3:
                if int(value) > num1 and int(value) < num2:
                    if  value != approvals_linenum[-1]:
                        approvals_list = [line.strip() for line in fd3.readlines()[int(index):int(approvals_linenum[index+1])]]
                    else:
                        approvals_list = [line.strip() for line in fd3.readlines()[int(index): num2]]
                    approvals.append(func(approvals_list))
        return approvals

    def __parse_patchsets(self, num2):

        patchSets_cmd = ["awk", '/patchSets:/{print NR}']
        patchSets_cmd.append(self.tmpfile)
        patchSets_linenum = subprocess.check_output(patchSets_cmd)
        patchSets_linenum = patchSets_linenum.splitlines()

        def func(patchSet_list, num1, num2):
            for y in patchSet_list:
                    if y.find("revision") != -1:
                        self.revision = y.split(':')[1].lstrip()
                    if y.find("parents") != -1 and patchSet_list[patchSet_list.index(y)+1].find("refs") == -1:
                        self.parents = patchSet_list[patchSet_list.index(y)+1].lstrip('[').rstrip(']')
                    if y.find("refs") != -1:
                        self.refs = y.split(':')[1].lstrip()
                        self.number = self.refs.split('/')[-2]
                    if y.find("approvals:") != -1:
                        self.approvals = self.__parse_approvals(num1, num2)


        for index, value in enumerate(patchSets_linenum):
            with open(self.tmpfile, 'r') as fd2:
                if int(value) > num2:
                    patchSet_list = [line.strip() for line in fd2.readlines()[int(patchSets_linenum[index-1]):num2]]
                    func(patchSet_list, int(patchSets_linenum[index-1]), num2)
                elif int(value) < num2 and value == patchSets_linenum[-1]:
                    patchSet_list = [line.strip() for line in fd2.readlines()[int(value):num2]]
                    func(patchSet_list, int(value), num2)

    def _parse_changes(self, num1, num2):

        with open(self.tmpfile, 'r') as fd:
            change_line = linecache.getline(self.tmpfile, num1)
            self.changeId = change_line.split(' ')[1]
            patchlist = [line.strip() for line in fd.readlines()[num1:num2]]
            for j in patchlist:
                if j.find("project") != -1:
                    self.project = j.split(':')[1].lstrip()
                if j.find("branch") != -1:
                    self.branch = j.split(':')[1].lstrip()
                if j.find("url") != -1:
                    self.url = ":".join(j.split(':')[1:]).lstrip()
                if j.find("patchSet") != -1:
                    self.__parse_patchsets(num2)

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

def big_bubble_sorted(f_list):
    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i].number < f_list[i+1].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

def small_bubble_sorted(f_list):
    for j in xrange(len(f_list)-1,-1,-1):
        for i in xrange(j):
            if(f_list[i][0].number > f_list[i+1][0].number):
                f_list[i],f_list[i+1] = f_list[i+1],f_list[i]
    return f_list

if __name__ == '__main__':
    patchObjs = []
    filtered =[]
    #tmpfile = get_patch_info_from_gerrit('jinjingx', 'vied-viedandr-libcamhal')
    #print tmpfile
    #tmpfile = "/tmp/tmp1"
    tmpfile = "/tmp/tmpyFGEz3"

    change_cmd = ["awk", '/change /{print NR}']
    change_cmd.append(tmpfile)

    changeline_num = subprocess.check_output(change_cmd)
    changeline_num = changeline_num.splitlines()

    lastline_cmd = ["awk", '/type: stats/{print NR}']
    lastline_cmd.append(tmpfile)
    lastline_num = subprocess.check_output(lastline_cmd).strip()

    for index, value in enumerate(changeline_num):
        patchobj = Parse(tmpfile)
        if value != changeline_num[-1]:
             patchobj._parse_changes(int(value), int(changeline_num[index+1]))
        else:
            patchobj._parse_changes(int(value), int(lastline_num)-1)
        patchObjs.append(patchobj)

    if patchObjs:
        #import ipdb;ipdb.set_trace()
        patchObjs = has_approval(patchObjs)
        filtered = check_value(patchObjs)

    big_sorted_l = big_bubble_sorted(filtered)

    all_deps = []
    while len(big_sorted_l) >= 1:
        for i in big_sorted_l:
            deps_list = find_parents(big_sorted_l, i)
            all_deps.append(deps_list)
            for j in deps_list:
                big_sorted_l.remove(j)

    small_sorted_l = small_bubble_sorted(all_deps)

    for m in small_sorted_l:
        #cherry_pick(name, project, m[0][0].refs)
        import ipdb;ipdb.set_trace()
        cherry_pick('jinjingx', 'vied-viedandr-libcamhal', m[0].refs)
