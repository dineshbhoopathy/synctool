#! /usr/bin/env python
#
#   synctool_master_pkg.py    WJ111
#
#   synctool Copyright 2013 Walter de Jong <walter@heiho.net>
#
#   synctool COMES WITH NO WARRANTY. synctool IS FREE SOFTWARE.
#   synctool is distributed under terms described in the GNU General Public
#   License.
#

'''This program is dsh-pkg on the master node. It calls synctool-pkg on
the target nodes'''

import os
import sys
import getopt
import shlex
import time
import errno

import synctool.aggr
import synctool.config
import synctool.lib
from synctool.lib import verbose, stderr, unix_out
import synctool.nodeset
import synctool.param
import synctool.unbuffered

NODESET = synctool.nodeset.NodeSet()

OPT_AGGREGATE = False

PASS_ARGS = None
MASTER_OPTS = None


def run_remote_pkg(address_list):
    '''run synctool-pkg on the target nodes'''

    synctool.lib.multiprocess(worker_pkg, address_list)


def worker_pkg(addr):
    '''runs ssh + synctool-pkg to the nodes in parallel'''

    nodename = NODESET.get_nodename_from_address(addr)

    # run 'ssh node pkg_cmd'
    cmd_arr = shlex.split(synctool.param.SSH_CMD)
    cmd_arr.append('--')
    cmd_arr.append(addr)
    cmd_arr.extend(shlex.split(synctool.param.PKG_CMD))
    cmd_arr.extend(PASS_ARGS)

    verbose('running synctool-pkg on node %s' % nodename)
    unix_out(' '.join(cmd_arr))

    synctool.lib.run_with_nodename(cmd_arr, nodename)


def rearrange_options():
    '''rearrange command-line options so that getopt() behaves
    more logical for us'''

    # what this function does is move any arguments given after --list,
    # --install, or --remove to the back so that getopt() will treat them
    # as (loose) arguments
    # This way, you/the user can pass a package list and still append
    # a new option (like -f) at the end

    arglist = sys.argv[1:]

    new_argv = []
    pkg_list = []

    while len(arglist) > 0:
        arg = arglist.pop(0)

        new_argv.append(arg)

        if arg[0] == '-':
            opt = arg[1:]

            if opt in ('l', '-list', 'i', '-install', 'R', '-remove'):
                if len(arglist) <= 0:
                    break

                optional_arg = arglist[0]
                while optional_arg[0] != '-':
                    pkg_list.append(optional_arg)

                    arglist.pop(0)

                    if not len(arglist):
                        break

                    optional_arg = arglist[0]

    new_argv.extend(pkg_list)
    return new_argv


def check_cmd_config():
    '''check whether the commands as given in synctool.conf actually exist'''

    errors = 0

    (ok, synctool.param.SSH_CMD) = synctool.config.check_cmd_config('ssh_cmd',
                                    synctool.param.SSH_CMD)
    if not ok:
        errors += 1

    (ok, synctool.param.PKG_CMD) = synctool.config.check_cmd_config('pkg_cmd',
                                    synctool.param.PKG_CMD)
    if not ok:
        errors += 1

    if errors > 0:
        sys.exit(-1)


def there_can_be_only_one():
    '''print usage information about actions'''

    print '''Specify only one of these options:
  -l, --list   [PACKAGE ...]     List installed packages
  -i, --install PACKAGE [..]     Install package
  -R, --remove  PACKAGE [..]     Uninstall package
  -u, --update                   Update the database of available packages
  -U, --upgrade                  Upgrade all outdated packages
  -C, --clean                    Cleanup caches of downloaded packages'''
    sys.exit(1)


def usage():
    '''print usage information'''

    print 'usage: %s [options] [package [..]]' % os.path.basename(sys.argv[0])
    print 'options:'
    print '  -h, --help                     Display this information'
    print '  -c, --conf=FILE                Use this config file'
    print ('                                 (default: %s)' %
           synctool.param.DEFAULT_CONF)

    print '''  -n, --node=LIST                Execute only on these nodes
  -g, --group=LIST               Execute only on these groups of nodes
  -x, --exclude=LIST             Exclude these nodes from the selected group
  -X, --exclude-group=LIST       Exclude these groups from the selection
  -l, --list   [PACKAGE ...]     List installed packages
  -i, --install PACKAGE [..]     Install package
  -R, --remove  PACKAGE [..]     Uninstall package
  -u, --update                   Update the database of available packages
  -U, --upgrade                  Upgrade all outdated packages
  -C, --clean                    Cleanup caches of downloaded packages
  -N, --numproc=NUM              Set number of concurrent procs
  -z, --zzz=NUM                  Sleep NUM seconds between each run
      --unix                     Output actions as unix shell commands
  -v, --verbose                  Be verbose
  -a, --aggregate                Condense output
  -f, --fix                      Perform upgrade (otherwise, do dry-run)
  -m, --manager PACKAGE_MANAGER  (Force) select this package manager

Supported package managers are:'''

    # print list of supported package managers
    # format it at 78 characters wide
    print ' ',
    n = 2
    for pkg in synctool.param.KNOWN_PACKAGE_MANAGERS:
        if n + len(pkg) + 1 <= 78:
            n = n + len(pkg) + 1
            print pkg,
        else:
            n = 2 + len(pkg) + 1
            print
            print ' ', pkg,

    print '''

The package list must be given last
Note that --upgrade does a dry run unless you specify --fix
'''


def get_options():
    '''parse command-line options'''

    global MASTER_OPTS, PASS_ARGS, OPT_AGGREGATE

    if len(sys.argv) <= 1:
        usage()
        sys.exit(1)

    # getopt() assumes that all options given after the first non-option
    # argument are all arguments (this is standard UNIX behavior, not GNU)
    # but in this case, I like the GNU way better, so re-arrange the options
    # This has odd consequences when someone gives a 'stale' --install or
    # --remove option without any argument, but hey ...

    arglist = rearrange_options()

    try:
        opts, args = getopt.getopt(arglist, 'hc:n:g:x:X:iRluUCm:fN:z:vqa',
            ['help', 'conf=', 'node=', 'group=', 'exclude=', 'exclude-group=',
            'list', 'install', 'remove', 'update', 'upgrade', 'clean',
            'cleanup', 'manager=', 'numproc=', 'zzz=',
            'fix', 'verbose', 'quiet', 'unix', 'aggregate'])
    except getopt.GetoptError as reason:
        print '%s: %s' % (os.path.basename(sys.argv[0]), reason)
#        usage()
        sys.exit(1)

    PASS_ARGS = []
    MASTER_OPTS = [ sys.argv[0] ]

    # first read the config file
    for opt, arg in opts:
        if opt in ('-h', '--help', '-?'):
            usage()
            sys.exit(1)

        if opt in ('-c', '--conf'):
            synctool.param.CONF_FILE = arg
            PASS_ARGS.append(opt)
            PASS_ARGS.append(arg)
            continue

    synctool.config.read_config()
    check_cmd_config()

    # then process all the other options
    #
    # Note: some options are passed on to synctool-pkg on the node, while
    #       others are not. Therefore some 'continue', while others don't

    action = 0
    needs_package_list = False

    for opt, arg in opts:
        if opt:
            MASTER_OPTS.append(opt)

        if arg:
            MASTER_OPTS.append(arg)

        if opt in ('-h', '--help', '-?', '-c', '--conf'):
            # already done
            continue

        if opt in ('-n', '--node'):
            NODESET.add_node(arg)
            continue

        if opt in ('-g', '--group'):
            NODESET.add_group(arg)
            continue

        if opt in ('-x', '--exclude'):
            NODESET.exclude_node(arg)
            continue

        if opt in ('-X', '--exclude-group'):
            NODESET.exclude_group(arg)
            continue

        if opt in ('-i', '--install'):
            action += 1
            needs_package_list = True

        if opt in ('-R', '--remove'):
            action += 1
            needs_package_list = True

        if opt in ('-l', '--list'):
            action += 1

        if opt in ('-u', '--update'):
            action += 1

        if opt in ('-U', '--upgrade'):
            action += 1

        if opt in ('-C', '--clean', '--cleanup'):
            action += 1

        if opt in ('-m', '--manager'):
            if not arg in synctool.param.KNOWN_PACKAGE_MANAGERS:
                stderr("error: unknown or unsupported package manager '%s'" %
                       arg)
                sys.exit(1)

            synctool.param.PACKAGE_MANAGER = arg

        if opt in ('-f', '--fix'):
            synctool.lib.DRY_RUN = False

        if opt in ('-N', '--numproc'):
            try:
                synctool.param.NUM_PROC = int(arg)
            except ValueError:
                print ("%s: option '%s' requires a numeric value" %
                       (os.path.basename(sys.argv[0]), opt))
                sys.exit(1)

            if synctool.param.NUM_PROC < 1:
                print ('%s: invalid value for numproc' %
                       os.path.basename(sys.argv[0]))
                sys.exit(1)

            continue

        if opt in ('-z', '--zzz'):
            try:
                synctool.param.SLEEP_TIME = int(arg)
            except ValueError:
                print ("%s: option '%s' requires a numeric value" %
                       (os.path.basename(sys.argv[0]), opt))
                sys.exit(1)

            if synctool.param.SLEEP_TIME < 0:
                print ('%s: invalid value for sleep time' %
                       os.path.basename(sys.argv[0]))
                sys.exit(1)

            if not synctool.param.SLEEP_TIME:
                # (temporarily) set to -1 to indicate we want
                # to run serialized
                # synctool.lib.multiprocess() will use this
                synctool.param.SLEEP_TIME = -1

            continue

        if opt in ('-q', '--quiet'):
            synctool.lib.QUIET = True

        if opt in ('-v', '--verbose'):
            synctool.lib.VERBOSE = True

        if opt == '--unix':
            synctool.lib.UNIX_CMD = True

        if opt in ('-a', '--aggregate'):
            OPT_AGGREGATE = True
            continue

        if opt:
            PASS_ARGS.append(opt)

        if arg:
            PASS_ARGS.append(arg)

    # enable logging at the master node
    PASS_ARGS.append('--masterlog')

    if args != None:
        MASTER_OPTS.extend(args)
        PASS_ARGS.extend(args)
    else:
        if needs_package_list:
            stderr('error: options --install and --remove require '
                   'a package name')
            sys.exit(1)

    if not action:
        usage()
        sys.exit(1)

    if action > 1:
        there_can_be_only_one()


def main():
    '''run the program'''

    synctool.param.init()

    sys.stdout = synctool.unbuffered.Unbuffered(sys.stdout)
    sys.stderr = synctool.unbuffered.Unbuffered(sys.stderr)

    try:
        get_options()
    except synctool.range.RangeSyntaxError as err:
        print 'error:', err
        sys.exit(1)

    if OPT_AGGREGATE:
        if not synctool.aggr.run(MASTER_OPTS):
            sys.exit(-1)

        sys.exit(0)

    synctool.config.init_mynodename()

    if synctool.param.MASTER != synctool.param.HOSTNAME:
        verbose('master %s != hostname %s' % (synctool.param.MASTER,
                                              synctool.param.HOSTNAME))
        stderr('error: not running on the master node')
        sys.exit(-1)

    synctool.lib.openlog()

    address_list = NODESET.addresses()
    if not address_list:
        print 'no valid nodes specified'
        sys.exit(1)

    run_remote_pkg(address_list)

    synctool.lib.closelog()


if __name__ == '__main__':
    try:
        main()

        # workaround exception in QueueFeederThread at exit
        # which is a Python bug, really
        time.sleep(0.01)
    except IOError as ioerr:
        if ioerr.errno == errno.EPIPE:  # Broken pipe
            pass
        else:
            print ioerr.strerror

    except KeyboardInterrupt:        # user pressed Ctrl-C
        print

# EOB
