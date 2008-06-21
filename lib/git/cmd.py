import os
import subprocess
import re
from utils import *
from method_missing import MethodMissingMixin
from errors import GitCommandError

# Enables debugging of GitPython's git commands
GIT_PYTHON_TRACE = os.environ.get("GIT_PYTHON_TRACE", False)

execute_kwargs = ('istream', 'with_keep_cwd', 'with_extended_output',
                  'with_exceptions', 'with_raw_output')

class Git(MethodMissingMixin):
    """
    The Git class manages communication with the Git binary
    """
    def __init__(self, git_dir=None, bare_repo=False):
        super(Git, self).__init__()
        if git_dir:
            self._location = os.path.abspath(git_dir)
        else:
            self._location = os.getcwd()
        self._is_bare_repo = bare_repo
        self.refresh()

    def refresh(self):
        self._git_dir = None
        self._is_in_repo = not not self.get_git_dir()
        self._work_tree = None
        self._cwd = self._git_dir
        if self._git_dir and not self._is_bare_repo:
            self._cwd = self.get_work_tree()

    def _is_git_dir(self, d):
        """ This is taken from the git setup.c:is_git_directory
            function."""

        if os.path.isdir(d) and \
                os.path.isdir(os.path.join(d, 'objects')) and \
                os.path.isdir(os.path.join(d, 'refs')):
            headref = os.path.join(d, 'HEAD')
            return os.path.isfile(headref) or \
                    (os.path.islink(headref) and
                    os.readlink(headref).startswith('refs'))
        return False

    def get_git_dir(self):
        if not self._git_dir:
            self._git_dir = os.getenv('GIT_DIR')
            if self._git_dir and self._is_git_dir(self._git_dir):
                return self._git_dir
            curpath = self._location
            while curpath:
                if self._is_git_dir(curpath):
                    self._git_dir = curpath
                    break
                gitpath = os.path.join(curpath, '.git')
                if self._is_git_dir(gitpath):
                    self._git_dir = gitpath
                    break
                curpath, dummy = os.path.split(curpath)
                if not dummy:
                    break
        return self._git_dir

    def get_work_tree(self):
        if self._is_bare_repo:
            return None
        if not self._work_tree:
            self._work_tree = os.getenv('GIT_WORK_TREE')
            if not self._work_tree or not os.path.isdir(self._work_tree):
                self._work_tree = os.path.abspath(
                                    os.path.join(self._git_dir, '..'))
        return self._work_tree

    @property
    def get_dir(self):
        return self._git_dir

    def execute(self, command,
                istream=None,
                with_keep_cwd=False,
                with_extended_output=False,
                with_exceptions=True,
                with_raw_output=False,
                ):
        """
        Handles executing the command on the shell and consumes and returns
        the returned information (stdout)

        ``command``
            The command argument list to execute

        ``istream``
            Standard input filehandle passed to subprocess.Popen.

        ``with_keep_cwd``
            Whether to use the current working directory from os.getcwd().
            GitPython uses get_work_tree() as its working directory by
            default and get_git_dir() for bare repositories.

        ``with_extended_output``
            Whether to return a (status, stdout, stderr) tuple.

        ``with_exceptions``
            Whether to raise an exception when git returns a non-zero status.

        ``with_raw_output``
            Whether to avoid stripping off trailing whitespace.

        Returns
            str(output)                     # extended_output = False (Default)
            tuple(int(status), str(output)) # extended_output = True
        """

        if GIT_PYTHON_TRACE and not GIT_PYTHON_TRACE == 'full':
            print ' '.join(command)

        # Allow the user to have the command executed in their working dir.
        if with_keep_cwd:
          cwd = os.getcwd()
        else:
          cwd=self._cwd

        # Start the process
        proc = subprocess.Popen(command,
                                cwd=cwd,
                                stdin=istream,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE
                                )

        # Wait for the process to return
        try:
            stdout_value = proc.stdout.read()
            stderr_value = proc.stderr.read()
            status = proc.wait()
        finally:
            proc.stdout.close()
            proc.stderr.close()

        # Strip off trailing whitespace by default
        if not with_raw_output:
            stdout_value = stdout_value.rstrip()
            stderr_value = stderr_value.rstrip()

        if with_exceptions and status != 0:
            raise GitCommandError(command, status, stderr_value)

        if GIT_PYTHON_TRACE == 'full':
            if stderr_value:
              print "%s -> %d: '%s' !! '%s'" % (command, status, stdout_value, stderr_value)
            elif stdout_value:
              print "%s -> %d: '%s'" % (command, status, stdout_value)
            else:
              print "%s -> %d" % (command, status)

        # Allow access to the command's status code
        if with_extended_output:
            return (status, stdout_value, stderr_value)
        else:
            return stdout_value

    def transform_kwargs(self, **kwargs):
        """
        Transforms Python style kwargs into git command line options.
        """
        args = []
        for k, v in kwargs.items():
            if len(k) == 1:
                if v is True:
                    args.append("-%s" % k)
                elif type(v) is not bool:
                    args.append("-%s%s" % (k, v))
            else:
                if v is True:
                    args.append("--%s" % dashify(k))
                elif type(v) is not bool:
                    args.append("--%s=%s" % (dashify(k), v))
        return args

    def method_missing(self, method, *args, **kwargs):
        """
        Run the given git command with the specified arguments and return
        the result as a String

        ``method``
            is the command

        ``args``
            is the list of arguments

        ``kwargs``
            is a dict of keyword arguments.
            This function accepts the same optional keyword arguments
            as execute().

        Examples
            git.rev_list('master', max_count=10, header=True)

        Returns
            Same as execute()
        """

        # Handle optional arguments prior to calling transform_kwargs
        # otherwise these'll end up in args, which is bad.
        _kwargs = {}
        for kwarg in execute_kwargs:
            try:
                _kwargs[kwarg] = kwargs.pop(kwarg)
            except KeyError:
                pass

        # Prepare the argument list
        opt_args = self.transform_kwargs(**kwargs)
        ext_args = map(str, args)
        args = opt_args + ext_args

        call = ["git", dashify(method)]
        call.extend(args)

        return self.execute(call, **_kwargs)