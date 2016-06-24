#!/usr/bin/env python2.7
"""
TODO: export from utool

        python -m utool.util_inspect check_module_usage --pat="util_git.py"
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
import sys
import os
import re
import six
from six.moves import zip
from os.path import exists, join, dirname, isdir, basename
from utool import util_dev
from utool import util_inject
from utool import util_class
from utool import util_path
print, rrr, profile = util_inject.inject2(__name__, '[git]')


def _syscmd(cmdstr):
    print('RUN> ' + cmdstr)
    os.system(cmdstr)


def _cd(dir_):
    dir_ = util_path.truepath(dir_)
    print('> cd ' + dir_)
    os.chdir(dir_)


@six.add_metaclass(util_class.ReloadingMetaclass)
class RepoManager(util_dev.NiceRepr):
    """
    Batch git operations on multiple repos
    """
    def __init__(rman, repo_urls=None, code_dir=None, userid=None,
                 permitted_repos=None, label=''):
        if userid is None:
            userid = None
        if permitted_repos is None:
            permitted_repos = []
        rman.permitted_repos = permitted_repos
        rman.code_dir = code_dir
        rman.userid = userid
        rman.repos = []
        rman.label = label

        if repo_urls is not None:
            rman.add_repos(repo_urls)

    def union(rman, other):
        new = RepoManager()
        new.userid = rman.userid
        new.code_dir = rman.code_dir
        new.permitted_repos = rman.permitted_repos + other.permitted_repos
        new.repos = rman.repos + other.repos
        return new

    @property
    def repo_urls(rman):
        return [repo.url for repo in rman.repos]

    @property
    def repo_dirs(rman):
        return [repo.url for repo in rman.repos]

    def __nice__(rman):
        return '(num=%d)' % (len(rman.repo_urls))

    def __getitem__(rman, name):
        for repo in rman.repos:
            if name in repo.aliases:
                return repo
        raise KeyError(name)

    def ensure(rman):
        print('Ensuring that respos are checked out')
        for repo in rman.repos:
            if repo.url is not None:
                repo.clone()

    def add_repo(rman, repo):
        repo._fix_url(rman.userid, rman.permitted_repos)
        rman.repos.append(repo)

    def add_repos(rman, repo_urls=None, code_dir=None):
        if code_dir is None:
            code_dir = rman.code_dir
        assert code_dir is not None, 'Must specify the checkout code_dir'
        repos = [Repo(url, code_dir) for url in repo_urls]
        for repo in repos:
            repo._fix_url(rman.userid, rman.permitted_repos)
        rman.repos.extend(repos)

    def issue(rman, command, sudo=False):
        """ Runs a command on all of managed repos """
        print('+------- GG_COMMAND -------')
        print('| sudo=%s' % sudo)
        print('| command=%s' % command)
        for repo in rman.repos:
            if exists(repo.dpath):
                repo.issue(command, sudo=sudo)
            else:
                print('Repo %r not found' % (repo,))
        print('L___ FINISHED GG_COMMAND ___')

    def check_importable(rman):
        import utool as ut
        label = ' %s' % rman.label if rman.label else rman.label
        missing = []
        print('Checking if%s modules are importable' % (label,))
        msg_list = []
        for repo in rman.repos:
            flag, msg = repo.check_importable()
            if not flag:
                msg_list.append('  * !!!%s REPO %s HAS IMPORT ISSUES' % (label.upper(), repo,))
                if ut.VERBOSE:
                    msg_list.append(ut.indent(msg, '    '))
                missing.append(repo)
            else:
                if ut.VERBOSE:
                    msg_list.append(ut.indent(msg, '    '))
        print('\n'.join(msg_list))
        return missing

    def check_installed(rman):
        import utool as ut
        label = ' %s' % rman.label if rman.label else rman.label
        missing = []
        msg_list = []
        print('Checking if%s modules are installed' % (label,))
        for repo in rman.repos:
            flag, msg = repo.check_installed()
            if not flag:
                msg_list.append('  * !!!%s REPO %s NEEDS TO BE INSTALLED' % (label.upper(), repo,))
                if ut.VERBOSE:
                    msg_list.append(ut.indent(msg, '    '))
                missing.append(repo)
            # else:
            #     print('  * found%s module = %s' % (label, repo,))
        print('\n'.join(msg_list))
        return missing

    def check_cpp_build(rman):
        import utool as ut
        label = ' %s' % rman.label if rman.label else rman.label
        missing = []
        print('Checking if%s modules are built' % (label,))
        for repo in rman.repos:
            flag, msg = repo.check_cpp_build()
            if not flag:
                print('  * !!!%s REPO %s NEEDS TO BE BUILT' % (label.upper(), repo,))
                if ut.VERBOSE:
                    print(ut.indent(msg, '    '))
                missing.append(repo)
        return missing

    def custom_build(rman):
        print('Custom Build')
        for repo in rman.repos:
            script = repo.get_script('build')
            if script is not None:
                script.exec_()

    def custom_install(rman):
        print('Custom Install')
        for repo in rman.repos:
            script = repo.get_script('install')
            if script is not None:
                script.exec_()

    def only_with_pysetup(rman):
        rman2 = RepoManager()
        rman2.code_dir = rman.code_dir
        rman2.permitted_repos = rman.permitted_repos
        rman2.code_dir = rman.code_dir
        rman2.userid = rman.userid
        rman2.label = rman.label
        rman2.repos = [repo for repo in rman.repos if repo.dpath and exists(join(repo.dpath, 'setup.py'))]
        return rman2


@six.add_metaclass(util_class.ReloadingMetaclass)
class Repo(util_dev.NiceRepr):
    """
    Handles a Python module repository
    """
    def __init__(repo, url=None, code_dir=None, dpath=None,
                 modname=None):
        import utool as ut
        repo.url = url
        repo._modname = None
        if modname is None:
            modname = []
        repo._modname_hints = ut.ensure_iterable(modname)
        repo.dpath = None
        repo.scripts = {}

        if dpath is None and repo.url is not None and code_dir is not None:
            dpath = join(code_dir, repo.reponame)
        if dpath is not None:
            repo.dpath = util_path.unixpath(dpath)

    @property
    def aliases(repo):
        aliases = []
        if repo._modname is not None:
            aliases.append(repo._modname)
        aliases.extend(repo._modname_hints[:])
        if repo.dpath and exists(repo.dpath):
            reponame = repo._find_modname_from_repo()
            if reponame is not None:
                aliases.append(reponame)
        aliases.append(repo.reponame)
        import utool as ut
        aliases = ut.unique(aliases)
        return aliases

    def __nice__(repo):
        reponame = repo.reponame
        modname = repo.modname
        # if modname is False:
        #     print(repo.__dict__)
        if modname is None or modname == reponame:
            return '(%s)' % (reponame,)
        else:
            return '(%s, %s)' % (reponame, modname)

    @property
    def modname(repo):
        # import utool as ut
        modname = None
        if repo._modname is not None:
            modname = repo._modname
        elif len(repo._modname_hints) == 1:
            modname = repo._modname_hints[0]
        else:
            modname = repo.aliases[0]
        return modname

    @property
    def reponame(repo):
        if repo.dpath is not None:
            reponame = basename(repo.dpath)
        elif repo.url is not None:
            url_parts = re.split('[/:]', repo.url)
            reponame = url_parts[-1].replace('.git', '')
        elif repo._modname_hints:
            reponame = repo._modname_hints[0]
        else:
            raise Exception('No way to infer (or even guess) repository name!')
        return reponame

    def _find_modname_from_repo(repo):
        import utool as ut
        packages = ut.get_submodules_from_dpath(repo.dpath, only_packages=True,
                                                recursive=False)
        if len(packages) == 1:
            modname = ut.get_modname_from_modpath(packages[0])
            return modname

    def add_script(repo, key, script):
        repo.scripts[key] = script

    def clone(repo):
        print('[git] checking repo at %s' % (repo.dpath))
        if not exists(repo.dpath):
            _cd(dirname(repo.dpath))
            _syscmd('git clone ' + repo.url)

    def owner(repo):
        url_parts = re.split('[/:]', repo.url)
        owner = url_parts[-2]
        return owner

    def is_owner(repo, userid):
        return userid is not None and repo.owner.lower() == userid.lower()

    def _fix_url(repo, userid, permitted_repos=[]):
        is_owner = repo.is_owner(userid)
        is_contrib = repo.reponame in permitted_repos
        if is_owner or is_contrib:
            repo._ensure_ssh_format()

    def change_url_format(repo, out_type='ssh'):
        """ Changes the url format for committing """
        url_parts = re.split('[/:]', repo.url)
        in_type = url_parts[0]
        url_fmts = {
            'https': ('.com/', 'https://'),
            'ssh':   ('.com:', 'git@'),
        }
        url_fmts['git'] = url_fmts['ssh']
        new_repo_url = repo.url
        for old, new in zip(url_fmts[in_type], url_fmts[out_type]):
            new_repo_url = new_repo_url.replace(old, new)
        # Inplace change
        repo.url = new_repo_url

    def check_importable(repo):
        import utool as ut
        # import utool as ut
        found = False
        tried = []
        for modname in repo.aliases:
            tried.append(modname)
            try:
                ut.import_modname(modname)
            except ImportError as ex:  # NOQA
                tried[-1] += ' but got ImportError'
                pass
            except AttributeError as ex:  # NOQA
                tried[-1] += ' but got AttributeError'
            else:
                found = True
                tried[-1] += ' and it worked'
                break
        msg = 'tried %s' % (', '.join(tried))
        return found, msg

    def check_installed(repo):
        """
        # http://stackoverflow.com/questions/14050281/how-to-check-if-a-python-module-exists-without-importing-it
        """
        # import utool as ut
        import pkgutil
        found = None
        tried = []
        for modname in repo.aliases:
            tried.append(modname)
            loader = pkgutil.find_loader(modname)
            found = loader is not None
            if found:
                break
            # try:
            #     ut.import_modname(modname)
            # except ImportError:
            #     continue
            # else:
            #     found = modname
            #     break
        # return
        # if flag:
        #     # Change internal name
        #     repo._modname = modname
        msg = 'tried %s' % (', '.join(tried))
        return found, msg

    def check_cpp_build(repo):
        import utool as ut
        script = repo.get_script('build')
        if script.is_fpath_valid():
            if repo.modname == 'pyflann':
                return True, 'cant detect flann cpp'
            # hack, this doesnt quite do it
            pat = '*' + ut.util_cplat.get_pylib_ext()
            dynlibs = ut.glob(repo.dpath + '/' + repo.modname, pat, recursive=True)
            msg = 'Could not find any dynamic libraries'
            flag = len(dynlibs) > 0
        else:
            flag = True
            msg = 'passed, but didnt expect anything'
        return flag, msg

    def get_script(repo, type_):
        class Script(object):
            def __init__(script):
                script.type_ = type_
                script.text = None
                script.fpath = None
                script.cmake = None

            def is_fpath_valid(script):
                return script.fpath is not None and exists(script.fpath)

            def is_valid(script):
                return script.text or script.is_fpath_valid()

            def exec_(script):
                import utool as ut
                print('+**** exec %s script *******' % (script.type_))
                print('repo = %r' % (repo,))
                with ut.ChdirContext(repo.dpath):
                    if script.is_fpath_valid():
                        normbuild_flag = '--no-rmbuild'
                        if ut.get_argflag(normbuild_flag):
                            ut.cmd(script.fpath + ' ' + normbuild_flag)
                        else:
                            ut.cmd(script.fpath)
                    else:
                        print("CANT QUITE EXECUTE THIS YET")
                        ut.print_code(script.text, 'bash')
                #os.system(scriptname)
                print('L**** exec %s script *******' % (script.type_))

        script = Script()
        script.text = repo.scripts.get('build', None)

        if type_ == 'build' and repo.dpath:
            if sys.platform.startswith('win32'):
                # vtool --rebuild-sver didnt work with this line
                #scriptname = './mingw_build.bat'
                fpath = join(repo.dpath, 'mingw_build.bat')
            else:
                fpath = join(repo.dpath, 'unix_build.sh')
            if exists(fpath):
                script.fpath = fpath

            cmake = join(repo.dpath, 'CMakeLists.txt')
            if exists(cmake):
                script.cmake = cmake

        return script

    def has_script(repo, type_):
        return repo.get_script(type_).is_valid()

    def custom_build(repo):
        script = repo.get_script('build')
        if script is not None:
            script.exec_()

    def custom_install(repo):
        script = repo.get_script('install')
        if script is not None:
            script.exec_()
        # TODO:
        # import utool as ut
        # ut.print_code(repo.install_script, 'bash')

    def issue(repo, command, sudo=False):
        """
        issues a command on a repo

        CommandLine:
            python -m utool.util_git --exec-repocmd

        Example:
            >>> # DISABLE_DOCTEST
            >>> from utool.util_git import *  # NOQA
            >>> import utool as ut
            >>> repo = dirname(ut.get_modpath(ut, prefer_pkg=True))
            >>> command = 'git status'
            >>> sudo = False
            >>> result = repocmd(repo, command, sudo)
            >>> print(result)
        """
        import utool as ut
        if ut.WIN32:
            assert not sudo, 'cant sudo on windows'
        command_list = ut.ensure_iterable(command)
        cmdstr = '\n        '.join([cmd_ for cmd_ in command_list])
        print('+--- *** repocmd(%s) *** ' % (cmdstr,))
        print('repo=%s' % ut.color_text(repo.dpath, 'yellow'))
        with ut.ChdirContext(repo.dpath, verbose=False):
            ret = None
            for count, cmd in enumerate(command_list):
                if not sudo or ut.WIN32:
                    ret = os.system(cmd)
                else:
                    out, err, ret = ut.cmd(cmd, sudo=True)
                verbose = True
                if verbose > 1:
                    print('ret(%d) = %r' % (count, ret,))
                if ret != 0:
                    raise Exception('Failed command %r' % (cmd,))
        print('L____')

    def is_gitrepo(repo):
        gitdir = join(repo.dpath, '.git')
        return exists(gitdir) and isdir(gitdir)

    def pull(repo, has_submods=False):
        print('Pulling: ' + repo.dpath)
        _cd(repo.dpath)
        assert repo.is_gitrepo(), 'cannot pull a nongit repo'
        _syscmd('git pull')
        if has_submods:
            _syscmd('git submodule init')
            _syscmd('git submodule update')

    def rename_branch(repo, old_branch_name, new_branch_name, remote='origin'):
        r"""
        References:
            http://stackoverflow.com/questions/1526794/rename?answertab=votes#tab-top
            http://stackoverflow.com/questions/9524933/renaming-a-branch-in-github

        CommandLine:
            python -m utool.util_git --test-rename_branch --old=mymaster --new=ibeis_master

        Example:
            >>> # SCRIPT
            >>> from utool.util_git import *  # NOQA
            >>> repo = ut.get_argval('--repo', str, '.')
            >>> remote = ut.get_argval('--remote', str, 'origin')
            >>> old_branch_name = ut.get_argval('--old', str, None)
            >>> new_branch_name = ut.get_argval('--new', str, None)
            >>> rename_branch(old_branch_name, new_branch_name, repo, remote)
        """
        assert repo.is_gitrepo(), 'cannot pull a nongit repo'
        fmtdict = dict(remote=remote,
                       old_branch_name=old_branch_name,
                       new_branch_name=new_branch_name)
        command_list = [
            'git checkout {old_branch_name}'.format(**fmtdict),
            # rename branch
            'git branch -m {old_branch_name} {new_branch_name}'.format(**fmtdict),
            # delete old branch
            'git push {remote} :{old_branch_name}'.format(**fmtdict),
            # push new branch
            'git push {remote} {new_branch_name}'.format(**fmtdict),
        ]
        repo.issue(command_list)


def git_sequence_editor_squash(fpath):
    """
    squashes wip messages

    CommandLine:
        python -m utool.util_git --exec-git_sequence_editor_squash

    Example:
        >>> # SCRIPT
        >>> import utool as ut
        >>> from utool.util_git import *  # NOQA
        >>> fpath = ut.get_argval('--fpath', str, default=None)
        >>> git_sequence_editor_squash(fpath)

    Ignore:
        text = ut.codeblock(
            '''
            pick 852aa05 better doctest for tips
            pick 3c779b8 wip
            pick 02bc21d wip
            pick 1853828 Fixed root tablename
            pick 9d50233 doctest updates
            pick 66230a5 wip
            pick c612e98 wip
            pick b298598 Fixed tablename error
            pick 1120a87 wip
            pick f6c4838 wip
            pick 7f92575 wip
            ''')

    Ignore:
        def squash_consecutive_commits_with_same_message():
            # http://stackoverflow.com/questions/8226278/git-alias-to-squash-all-commits-with-a-particular-commit-message
            # Can do interactively with this. Can it be done automatically and pay attention to
            # Timestamps etc?
            git rebase --interactive HEAD~40 --autosquash
            git rebase --interactive $(git merge-base HEAD master) --autosquash

            # Lookbehind correct version
            %s/\([a-z]* [a-z0-9]* wip\n\)\@<=pick \([a-z0-9]*\) wip/squash \2 wip/gc

           # THE FULL NON-INTERACTIVE AUTOSQUASH SCRIPT
           # TODO: Dont squash if there is a one hour timedelta between commits

           GIT_EDITOR="cat $1" GIT_SEQUENCE_EDITOR="python -m utool.util_git --exec-git_sequence_editor_squash \
                   --fpath $1" git rebase -i $(git rev-list HEAD | tail -n 1) --autosquash --no-verify
           GIT_EDITOR="cat $1" GIT_SEQUENCE_EDITOR="python -m utool.util_git --exec-git_sequence_editor_squash \
                   --fpath $1" git rebase -i HEAD~10 --autosquash --no-verify

           GIT_EDITOR="cat $1" GIT_SEQUENCE_EDITOR="python -m utool.util_git --exec-git_sequence_editor_squash \
                   --fpath $1" git rebase -i $(git merge-base HEAD master) --autosquash --no-verify

           # 14d778fa30a93f85c61f34d09eddb6d2cafd11e2
           # c509a95d4468ebb61097bd9f4d302367424772a3
           # b0ffc26011e33378ee30730c5e0ef1994bfe1a90
           # GIT_SEQUENCE_EDITOR=<script> git rebase -i <params>
           # GIT_SEQUENCE_EDITOR="echo 'FOOBAR $1' " git rebase -i HEAD~40 --autosquash
           # git checkout master
           # git branch -D tmp
           # git checkout -b tmp
           # option to get the tail commit
           $(git rev-list HEAD | tail -n 1)
           # GIT_SEQUENCE_EDITOR="python -m utool.util_git --exec-git_sequence_editor_squash \
                   --fpath $1" git rebase -i HEAD~40 --autosquash
           # GIT_SEQUENCE_EDITOR="python -m utool.util_git --exec-git_sequence_editor_squash \
                   --fpath $1" git rebase -i HEAD~40 --autosquash --no-verify
           <params>
    """
    # print(sys.argv)
    import utool as ut
    text = ut.read_from(fpath)
    # print('fpath = %r' % (fpath,))
    print(text)
    # Doesnt work because of fixed witdth requirement
    # search = (ut.util_regex.positive_lookbehind('[a-z]* [a-z0-9]* wip\n') + 'pick ' +
    #           ut.reponamed_field('hash', '[a-z0-9]*') + ' wip')
    # repl = ('squash ' + ut.bref_field('hash') + ' wip')
    # import re
    # new_text = re.sub(search, repl, text, flags=re.MULTILINE)
    # print(new_text)
    prev_msg = None
    prev_dt = None
    new_lines = []

    def get_commit_date(hashid):
        out, err, ret = ut.cmd('git show -s --format=%ci ' + hashid, verbose=False, quiet=True, pad_stdout=False)
        # from datetime import datetime
        from dateutil import parser
        # print('out = %r' % (out,))
        stamp = out.strip('\n')
        # print('stamp = %r' % (stamp,))
        dt = parser.parse(stamp)
        # dt = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S %Z')
        # print('dt = %r' % (dt,))
        return dt

    for line in text.split('\n'):
        commit_line = line.split(' ')
        if len(commit_line) < 3:
            prev_msg = None
            prev_dt = None
            new_lines += [line]
            continue
        action = commit_line[0]
        hashid = commit_line[1]
        msg = ' ' .join(commit_line[2:])
        try:
            dt = get_commit_date(hashid)
        except ValueError:
            prev_msg = None
            prev_dt = None
            new_lines += [line]
            continue
        orig_msg = msg
        can_squash = action == 'pick' and msg == 'wip' and prev_msg == 'wip'
        if prev_dt is not None and prev_msg == 'wip':
            tdelta = dt - prev_dt
            # Only squash closely consecutive commits
            threshold_minutes = 45
            td_min = (tdelta.total_seconds() / 60.)
            # print(tdelta)
            can_squash &= td_min < threshold_minutes
            msg = msg + ' -- tdelta=%r' % (ut.get_timedelta_str(tdelta),)
        if can_squash:
            new_line = ' ' .join(['squash', hashid, msg])
            new_lines += [new_line]
        else:
            new_lines += [line]
        prev_msg = orig_msg
        prev_dt = dt
    new_text = '\n'.join(new_lines)

    def get_commit_date(hashid):
        out = ut.cmd('git show -s --format=%ci ' + hashid, verbose=False)
        print('out = %r' % (out,))

    # print('Dry run')
    # ut.dump_autogen_code(fpath, new_text)
    print(new_text)
    ut.write_to(fpath, new_text, n=None)


def std_build_command(repo='.'):
    """
    DEPRICATE
    My standard build script names.

    Calls mingw_build.bat on windows and unix_build.sh  on unix
    """
    import utool as ut
    print('+**** stdbuild *******')
    print('repo = %r' % (repo,))
    if sys.platform.startswith('win32'):
        # vtool --rebuild-sver didnt work with this line
        #scriptname = './mingw_build.bat'
        scriptname = 'mingw_build.bat'
    else:
        scriptname = './unix_build.sh'
    if repo == '':
        # default to cwd
        repo = '.'
    else:
        os.chdir(repo)
    ut.assert_exists(scriptname)
    normbuild_flag = '--no-rmbuild'
    if ut.get_argflag(normbuild_flag):
        scriptname += ' ' + normbuild_flag
    # Execute build
    ut.cmd(scriptname)
    #os.system(scriptname)
    print('L**** stdbuild *******')


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m utool.util_git
        python -m utool.util_git --allexamples
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
