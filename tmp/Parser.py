#!/usr/bin/python
import linecache
import subprocess

class Parser(object):

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

    def _parse_approvals(self, num1, num2):
        approvals = []
        approvals_cmd = ["awk", '/approvals:/{print NR}']
        approvals_cmd.append(self.tmpfile)

        approvals_linenum = subprocess.check_output(approvals_cmd)
        approvals_linenum = approvals_linenum.splitlines()

        def func(approvals_list):
            approval = {}
            for i in approvals_list:
                if i.find("type") != -1:
                    approval[i.split(':')[0]] = i.split(':')[1].lstrip()
                if i.find("value") != -1:
                    approval[i.split(':')[0]] = i.split(':')[1].lstrip()
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

    def _parse_patchsets(self, num2):

        patchSets_cmd = ["awk", '/patchSets:/{print NR}']
        patchSets_cmd.append(self.tmpfile)
        patchSets_linenum = subprocess.check_output(patchSets_cmd)
        patchSets_linenum = patchSets_linenum.splitlines()

        def func(patchSet_list, num1, num2):
            for i in patchSet_list:
                    if i.find("revision") != -1:
                        self.revision = i.split(':')[1].lstrip()
                    if i.find("parents") != -1 and patchSet_list[patchSet_list.index(i)+1].find("refs") == -1:
                        self.parents = patchSet_list[patchSet_list.index(i)+1].lstrip('[').rstrip(']')
                    if i.find("refs") != -1:
                        self.refs = i.split(':')[1].lstrip()
                        self.number = self.refs.split('/')[-2]
                    if i.find("approvals:") != -1:
                        self.approvals = self._parse_approvals(num1, num2)


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
            for i in patchlist:
                if i.find("project") != -1:
                    self.project = i.split(':')[1].lstrip()
                if i.find("branch") != -1:
                    self.branch = i.split(':')[1].lstrip()
                if i.find("url") != -1:
                    self.url = ":".join(i.split(':')[1:]).lstrip()
                if i.find("patchSet") != -1:
                    self._parse_patchsets(num2)
