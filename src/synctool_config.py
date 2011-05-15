#! /usr/bin/env python
#
#	synctool-config	WJ109
#
#   synctool by Walter de Jong <walter@heiho.net> (c) 2003-2011
#
#   synctool COMES WITH NO WARRANTY. synctool IS FREE SOFTWARE.
#   synctool is distributed under terms described in the GNU General Public
#   License.
#

import os
import sys
import string
import socket
import getopt

VERSION = '5.0-beta'

DEFAULT_CONF = '/var/lib/synctool/synctool.conf'
CONF_FILE = DEFAULT_CONF

ACTION = 0
ACTION_OPTION = None
ARG_NODENAMES = None
ARG_GROUPS = None
ARG_CMDS = None

# these are enums for the "list" command-line options
ACTION_LIST_NODES = 1
ACTION_LIST_GROUPS = 2
ACTION_NODES = 3
ACTION_GROUPS = 4
ACTION_MASTERDIR = 5
ACTION_CMDS = 6
ACTION_NUMPROC = 7
ACTION_VERSION = 8
ACTION_PREFIX = 9
ACTION_NODENAME = 10

# optional: do not list hosts/groups that are ignored
OPT_FILTER_IGNORED = False
# optional: list interface names for the selected nodes
OPT_INTERFACE = False

#
#	config variables
#
MASTERDIR = None
OVERLAY_DIRS = []
DELETE_DIRS = []
TASKS_DIRS = []
SCRIPT_DIR = None
HOSTNAME = None
NODENAME = None

DIFF_CMD = None
PING_CMD = None
SSH_CMD = None
SCP_CMD = None
RSYNC_CMD = None
SYNCTOOL_CMD = None
LOGFILE = None
NUM_PROC = 16				# use sensible default

#
#	default symlink mode
#	Linux makes them 0777 no matter what umask you have ...
#	but how do you like them on a different platform?
#
#	The symlink mode can be set in the config file with keyword symlink_mode
#
SYMLINK_MODE = 0755

ERASE_SAVED = False
IGNORE_DOTFILES = False
IGNORE_DOTDIRS = False
IGNORE_FILES = []
IGNORE_GROUPS = []
ON_UPDATE = {}
ALWAYS_RUN = []

NODES = {}
INTERFACES = {}

GROUP_DEFS = {}

# to be initialized externally ... (see synctool.py)
# these are lists of group names
MY_GROUPS = None
ALL_GROUPS = None

# string length of the 'MASTERDIR' variable
# although silly to keep this in a var, it makes it easier to print messages
MASTER_LEN = 0


def stderr(str):
	sys.stderr.write(str + '\n')


def read_config():
	'''read the config file and set a bunch of globals'''
	
	global MASTERDIR, GROUP_DEFS, NODES, IGNORE_GROUPS
	global OVERLAY_DIRS, DELETE_DIRS, TASKS_DIRS, SCRIPT_DIR
	
	if not os.path.isfile(CONF_FILE):
		stderr("no such config file '%s'" % CONF_FILE)
		sys.exit(-1)
	
	errors = read_config_file(CONF_FILE)
	
	# if missing, set default directories
	if MASTERDIR == None:
		MASTERDIR = '.'			# hmmm ... nice for debugging, but shouldn't this be /var/lib/synctool ?
	
	if not OVERLAY_DIRS:
		OVERLAY_DIRS.append(os.path.join(MASTERDIR, 'overlay'))
		if not os.path.isdir(OVERLAY_DIRS[0]):
			stderr('error: no such directory: %s' % OVERLAY_DIRS[0])
			errors = errors + 1
	
	if not DELETE_DIRS:
		DELETE_DIRS.append(os.path.join(MASTERDIR, 'delete'))
		if not os.path.isdir(DELETE_DIRS[0]):
			stderr('error: no such directory: %s' % DELETE_DIRS[0])
			errors = errors + 1
	
	if not TASKS_DIRS:
		TASKS_DIRS.append(os.path.join(MASTERDIR, 'tasks'))
		if not os.path.isdir(TASKS_DIRS[0]):
			stderr('error: no such directory: %s' % TASKS_DIRS[0])
			errors = errors + 1
	
	if not SCRIPT_DIR:
		SCRIPT_DIR = os.path.join(MASTERDIR, 'scripts')
		if not os.path.isdir(SCRIPT_DIR):
			stderr('error: no such directory: %s' % SCRIPT_DIR)
			errors = errors + 1
	
	if errors > 0:
		sys.exit(-1)
	
	# implicitly add 'nodename' as first group
	for node in get_all_nodes():
		insert_group(node, node)
	
	# implicitly add group 'all'
	if not GROUP_DEFS.has_key('all'):
		GROUP_DEFS['all'] = None
	
	for node in get_all_nodes():
		if not 'all' in NODES[node]:
			NODES[node].append('all')
	
	# implicitly add group 'none'
	if not GROUP_DEFS.has_key('none'):
		GROUP_DEFS['none'] = None
	
	if not 'none' in IGNORE_GROUPS:
		IGNORE_GROUPS.append('none')


def read_config_file(configfile):
	'''read a (included) config file'''
	'''returns 0 on success, or error count on errors'''
	
	global MASTERDIR, MASTER_LEN, DIFF_CMD, PING_CMD, SSH_CMD, SCP_CMD, RSYNC_CMD, SYNCTOOL_CMD
	global LOGFILE, NUM_PROC, SYMLINK_MODE, ERASE_SAVED
	global IGNORE_DOTFILES, IGNORE_DOTDIRS, IGNORE_FILES, IGNORE_GROUPS
	global ON_UPDATE, ALWAYS_RUN
	global NODES, INTERFACES, GROUP_DEFS
	global OVERLAY_DIRS, DELETE_DIRS, TASKS_DIRS, SCRIPT_DIR
	
	try:
		f = open(configfile, 'r')
	except IOError, reason:
		stderr("failed to read config file '%s' : %s" % (configfile, reason))
		return 1

	lineno = 0
	errors = 0

	#
	#	read lines from the config file
	#	variable tmp_line is used to be able to do multi-line reads (backslash terminated)
	#
	line = ''
	while True:
		tmp_line = f.readline()
		if not tmp_line:
			break

		lineno = lineno + 1

		n = string.find(tmp_line, '#')
		if n >= 0:
			tmp_line = tmp_line[:n]		# strip comment

		tmp_line = string.strip(tmp_line)
		if not tmp_line:
			continue

		if tmp_line[-1] == '\\':
			tmp_line = string.strip(tmp_line[:-1])
			line = line + ' ' + tmp_line
			continue

		line = line + ' ' + tmp_line
		tmp_line = ''

		arr = string.split(line)

		line = ''	# <-- line is being reset here; use arr[] from here on

		if len(arr) <= 1:
			stderr('%s:%d: syntax error ; expected key/value pair' % (configfile, lineno))
			errors = errors + 1
			continue

		keyword = string.lower(arr[0])

		#
		#	keyword: include
		#
		if keyword == 'include':
			# recursively read the given config file
			errors = errors + read_config_file(arr[1])
			continue

		#
		#	keyword: masterdir
		#
		if keyword == 'masterdir':
			if MASTERDIR != None:
				stderr("%s:%d: redefinition of masterdir" % (configfile, lineno))
				errors = errors + 1
				continue
			
			if not os.path.isdir(arr[1]):
				stderr('%s:%d: no such directory for masterdir' % (configfile, lineno))
				errors = errors + 1
				continue
			
			MASTERDIR = arr[1]
			MASTER_LEN = len(MASTERDIR) + 1
			continue

		#
		#	keyword: overlaydir
		#
		if keyword == 'overlaydir':
			if arr[1] in OVERLAY_DIRS:
				stderr("%s:%d: already in overlaydir" % (configfile, lineno))
				errors = errors + 1
				continue
			
			if not os.path.isdir(arr[1]):
				stderr('%s:%d: no such directory for overlaydir' % (configfile, lineno))
				errors = errors + 1
				continue
			
			OVERLAY_DIRS.append(arr[1])
			continue
		
		#
		#	keyword: deletedir
		#
		if keyword == 'deletedir':
			if arr[1] in DELETE_DIRS:
				stderr("%s:%d: already in deletedir" % (configfile, lineno))
				errors = errors + 1
				continue
			
			if not os.path.isdir(arr[1]):
				stderr('%s:%d: no such directory for deletedir' % (configfile, lineno))
				errors = errors + 1
				continue
			
			DELETE_DIRS.append(arr[1])
			continue
		
		#
		#	keyword: tasksdir
		#
		if keyword == 'tasksdir':
			if arr[1] in TASKS_DIRS:
				stderr("%s:%d: already in tasksdir" % (configfile, lineno))
				errors = errors + 1
				continue
			
			if not os.path.isdir(arr[1]):
				stderr('%s:%d: no such directory for tasksdir' % (configfile, lineno))
				errors = errors + 1
				continue
			
			TASKS_DIRS.append(arr[1])
			continue
		
		#
		#	keyword: scriptdir
		#
		if keyword == 'scriptdir':
			if SCRIPT_DIR != None:
				stderr("%s:%d: redefinition of scriptdir" % (configfile, lineno))
				errors = errors + 1
				continue
			
			if not os.path.isdir(arr[1]):
				stderr('%s:%d: no such directory for scriptdir' % (configfile, lineno))
				errors = errors + 1
				continue
			
			SCRIPT_DIR = arr[1]
			continue
		
		#
		#	keyword: symlink_mode
		#
		if keyword == 'symlink_mode':
			try:
				mode = int(arr[1], 8)
			except ValueError:
				stderr("%s:%d: invalid argument for symlink_mode" % (configfile, lineno))
				errors = errors + 1
				continue

			SYMLINK_MODE = mode
			continue

		#
		#	keyword: erase_saved
		#
		if keyword == 'erase_saved':
			if arr[1] in ('1', 'on', 'yes'):
				ERASE_SAVED = True
			
			elif arr[1] in ('0', 'off', 'no'):
				ERASE_SAVED = False
			
			else:
				stderr("%s:%d: invalid argument for erase_saved" % (CONF_FILE, lineno))
				errors = errors + 1
			continue

		#
		#	keyword: ignore_dotfiles
		#
		if keyword == 'ignore_dotfiles':
			if arr[1] in ('1', 'on', 'yes'):
				IGNORE_DOTFILES = True

			elif arr[1] in ('0', 'off', 'no'):
				IGNORE_DOTFILES = False

			else:
				stderr("%s:%d: invalid argument for ignore_dotfiles" % (configfile, lineno))
				errors = errors + 1
			continue

		#
		#	keyword: ignore_dotdirs
		#
		if keyword == 'ignore_dotdirs':
			if arr[1] in ('1', 'on', 'yes'):
				IGNORE_DOTDIRS = True

			elif arr[1] in ('0', 'off', 'no'):
				IGNORE_DOTDIRS = False

			else:
				stderr("%s:%d: invalid argument for ignore_dotdirs" % (configfile, lineno))
				errors = errors + 1
			continue

		#
		#	keyword: ignore
		#
		if keyword in ('ignore', 'ignore_file', 'ignore_files', 'ignore_dir', 'ignore_dirs'):
			if len(arr) < 2:
				stderr("%s:%d: 'ignore' requires at least 1 argument: the file or directory to ignore" % (configfile, lineno))
				errors = errors + 1
				continue

			IGNORE_FILES.extend(arr[1:])
			continue

		#
		#	keyword: group
		#
		if keyword == 'group':
			if len(arr) < 3:
				stderr("%s:%d: 'group' requires at least 2 arguments: the compound group name and at least 1 member group" % (configfile, lineno))
				errors = errors + 1
				continue
			
			group = arr[1]
			
			if GROUP_DEFS.has_key(group):
				stderr("%s:%d: redefiniton of group %s" % (configfile, lineno, group))
				errors = errors + 1
				continue
			
			if NODES.has_key(group):
				stderr("%s:%d: %s was previously defined as a node" % (configfile, lineno, group))
				errors = errors + 1
				continue
			
			try:
				GROUP_DEFS[group] = expand_grouplist(arr[2:])
			except RuntimeError, e:
				stderr("%s:%d: compound groups can not contain node names" % (configfile, lineno))
				errors = errors + 1
				continue
			
			continue

		#
		#	keyword: host / node
		#
		if keyword == 'host' or keyword == 'node':
			if len(arr) < 2:
				stderr("%s:%d: '%s' requires at least 1 argument: the nodename" % (configfile, lineno, keyword))
				errors = errors + 1
				continue

			node = arr[1]
			groups = arr[2:]

			if NODES.has_key(node):
				stderr("%s:%d: redefinition of node %s" % (configfile, lineno, node))
				errors = errors + 1
				continue

			if GROUP_DEFS.has_key(node):
				stderr("%s:%d: %s was previously defined as a group" % (configfile, lineno, node))
				errors = errors + 1
				continue
			
			if len(groups) >= 1 and groups[-1][:10] == 'interface:':
				interface = groups[-1][10:]
				groups = groups[:-1]

				if INTERFACES.has_key(node):
					stderr("%s:%d: redefinition of interface for node %s" % (configfile, lineno, node))
					errors = errors + 1
					continue

				INTERFACES[node] = interface

			try:
				NODES[node] = expand_grouplist(groups)
			except RuntimeError, e:
				stderr("%s:%d: a group list can not contain node names" % (configfile, lineno))
				errors = errors + 1
				continue
			
			continue

		#
		#	keyword: ignore_host / ignore_node
		#
		if keyword == 'ignore_host' or keyword == 'ignore_node':
			if len(arr) < 2:
				stderr("%s:%d: '%s' requires 1 argument: the nodename to ignore" % (configfile, lineno, keyword))
				errors = errors + 1
				continue

			IGNORE_GROUPS.append(arr[1])
			continue

		#
		#	keyword: ignore_group
		#
		if keyword == 'ignore_group':
			if len(arr) < 2:
				stderr("%s:%d: 'ignore_group' requires at least 1 argument: the group to ignore" % (configfile, lineno))
				errors = errors + 1
				continue

			IGNORE_GROUPS.extend(arr[1:])
			
			# add any (yet) unknown group names to the group_defs dict
			for elem in arr[1:]:
				if not GROUP_DEFS.has_key(elem):
					GROUP_DEFS[elem] = None
			
			continue

		#
		#	keyword: on_update
		#
		if keyword == 'on_update':
			if len(arr) < 3:
				stderr("%s:%d: 'on_update' requires at least 2 arguments: filename and shell command to run" % (configfile, lineno))
				errors = errors + 1
				continue

			file = arr[1]
			cmd = string.join(arr[2:])

			#
			#	check if the script exists
			#
			if arr[2][0] != '/':
				master = '.'
				if MASTERDIR != None:
					master = MASTERDIR
				else:
					stderr("%s:%d: note: masterdir not defined, using current working directory" % (configfile, lineno))

				scripts = os.path.join(master, 'scripts')
				full_cmd = os.path.join(scripts, arr[2])
			else:
				full_cmd = arr[2]

			if not os.path.isfile(full_cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, full_cmd))
				errors = errors + 1
				continue

			ON_UPDATE[file] = cmd
			continue

		#
		#	keyword: always_run
		#
		if keyword == 'always_run':
			if len(arr) < 2:
				stderr("%s:%d: 'always_run' requires an argument: the shell command to run" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = string.join(arr[1:])

			if cmd in ALWAYS_RUN:
				stderr("%s:%d: same command defined again: %s" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			#
			#	check if the script exists
			#
			if arr[1][0] != '/':
				master = '.'
				if MASTERDIR != None:
					master = MASTERDIR
				else:
					stderr("%s:%d: note: masterdir not defined, using current working directory" % (configfile, lineno))

				scripts = os.path.join(master, 'scripts')
				full_cmd = os.path.join(scripts, arr[1])
			else:
				full_cmd = arr[1]

			if not os.path.isfile(full_cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, full_cmd))
				errors = errors + 1
				continue

			ALWAYS_RUN.append(cmd)
			continue

		#
		#	keyword: diff_cmd
		#
		if keyword == 'diff_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'diff_cmd' requires an argument: the full path to the 'diff' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			DIFF_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: ping_cmd
		#
		if keyword == 'ping_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'ping_cmd' requires an argument: the full path to the 'ping' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			PING_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: ssh_cmd
		#
		if keyword == 'ssh_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'ssh_cmd' requires an argument: the full path to the 'ssh' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			SSH_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: scp_cmd
		#
		if keyword == 'scp_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'scp_cmd' requires an argument: the full path to the 'scp' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			SCP_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: rsync_cmd
		#
		if keyword == 'rsync_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'rsync_cmd' requires an argument: the full path to the 'rsync' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			RSYNC_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: synctool_cmd
		#
		if keyword == 'synctool_cmd':
			if len(arr) < 2:
				stderr("%s:%d: 'synctool_cmd' requires an argument: the full path to the remote 'synctool' command" % (configfile, lineno))
				errors = errors + 1
				continue

			cmd = arr[1]
			if not os.path.isfile(cmd):
				stderr("%s:%d: no such command '%s'" % (configfile, lineno, cmd))
				errors = errors + 1
				continue

			SYNCTOOL_CMD = string.join(arr[1:])
			continue

		#
		#	keyword: logfile
		#
		if keyword == 'logfile':
			if len(arr) < 2:
				stderr("%s:%d: 'logfile' requires an argument: the full path to the file to write log messages to" % (configfile, lineno))
				errors = errors + 1
				continue

			LOGFILE = string.join(arr[1:])
			continue

		#
		#	keyword: num_proc
		#
		if keyword == 'num_proc':
			try:
				num_proc = int(arr[1])
			except ValueError:
				stderr("%s:%d: invalid argument for num_proc" % (configfile, lineno))
				errors = errors + 1
				continue

			if num_proc < 1:
				stderr("%s:%d: invalid argument for num_proc" % (configfile, lineno))
				errors = errors + 1
				continue

			NUM_PROC = num_proc
			continue

		stderr("%s:%d: unknown keyword '%s'" % (configfile, lineno, keyword))
		errors = errors + 1

	f.close()
	return errors


def expand_grouplist(grouplist):
	'''expand a list of (compound) groups recursively
	Returns the expanded group list
'''
	global GROUP_DEFS
	
	groups = []
	
	for elem in grouplist:
		groups.append(elem)
		
		if GROUP_DEFS.has_key(elem):
			compound_groups = GROUP_DEFS[elem]
			
			# mind that GROUP_DEFS[group] can be None
			# for any groups that have no subgroups
			if compound_groups != None:
				groups.extend(compound_groups)
		else:
			# node names are often treated in the code as groups too ...
			# but they are special groups, and can not be in a compound group just
			# to prevent odd things from happening
			if NODES.has_key(elem):
				raise RuntimeError, 'node %s can not be part of compound group list' % elem
			
			GROUP_DEFS[elem] = None
	
	# remove duplicates
	# this looks pretty lame ... but Python sets are not usable here;
	# sets mess around with the order (probably because the elements are string values)
	
	expanded_grouplist = []
	for elem in groups:
		if not elem in expanded_grouplist:
			expanded_grouplist.append(elem)
	
	return expanded_grouplist


def add_myhostname():
	'''add the hostname of the current host to the configuration, so that it can be used'''
	'''also determine the nodename of the current host'''

	global NODENAME, HOSTNAME

	#
	#	get my hostname
	#
	HOSTNAME = hostname = socket.gethostname()

	arr = string.split(hostname, '.')
	short_hostname = arr[0]

	all_nodes = get_all_nodes()

	if hostname != short_hostname and hostname in all_nodes and short_hostname in all_nodes:
		stderr("%s: conflict; node %s and %s are both defined" % (CONF_FILE, hostname, arr[0]))
		sys.exit(-1)

	nodename = None

	if short_hostname in all_nodes:
		nodename = short_hostname

	elif hostname in all_nodes:
		nodename = hostname

	else:
		# try to find a node that has the (short) hostname listed as interface
		# or as a group
		for node in all_nodes:
			iface = get_node_interface(node)
			if iface == short_hostname or iface == hostname:
				nodename = node
				break

			groups = get_groups(node)
			if short_hostname in groups or hostname in groups:
				nodename = node
				break

	NODENAME = nodename

	if nodename != None:
		# implicitly add hostname as first group
		insert_group(nodename, hostname)
		insert_group(nodename, short_hostname)
		insert_group(nodename, nodename)


# remove ignored groups from all hosts
def remove_ignored_groups():
	for host in NODES.keys():
		changed = False
		groups = NODES[host]
		for ignore in IGNORE_GROUPS:
			if ignore in groups:
				groups.remove(ignore)
				changed = True

		if changed:
			NODES[host] = groups


def insert_group(node, group):
	'''add group to node definition'''

	if NODES.has_key(node):
		if group in NODES[node]:
			NODES[node].remove(group)		# this is to make sure it comes first

		NODES[node].insert(0, group)
	else:
		NODES[node] = [group]


def get_all_nodes():
	return NODES.keys()


def get_node_interface(node):
	if INTERFACES.has_key(node):
		return INTERFACES[node]
	
	return node


def list_all_nodes():
	nodes = get_all_nodes()
	nodes.sort()

	if IGNORE_GROUPS != None:
		ignore_nodes = get_nodes_in_groups(IGNORE_GROUPS)
	else:
		ignore_nodes = []

	for host in nodes:
		if host in ignore_nodes:
			if OPT_INTERFACE:
				host = get_node_interface(host)

			if not OPT_FILTER_IGNORED:
				print '%s (ignored)' % host
		else:
			if OPT_INTERFACE:
				host = get_node_interface(host)

			print host


def make_all_groups():
	'''make a list of all possible groups
	This is a set of all group names plus all node names
'''

	arr = GROUP_DEFS.keys()
	arr.extend(NODES.keys())

#	older versions of python do not support sets BUT that doesn't matter ...
#	all groups + nodes should have no duplicates anyway
#	return list(set(arr))
	return arr


def list_all_groups():
	groups = GROUP_DEFS.keys()
	groups.sort()

	for group in groups:
		if group in IGNORE_GROUPS:
			if not OPT_FILTER_IGNORED:
				print '%s (ignored)' % group
		else:
			print group


def get_groups(nodename):
	'''returns the groups for the node'''

	if NODES.has_key(nodename):
		return NODES[nodename]

	return []


def get_my_groups():
	'''returns the groups for this node'''

	if NODES.has_key(NODENAME):
		return NODES[NODENAME]

	return []


def list_nodes(nodenames):
	groups = []

	for nodename in nodenames:
		if not NODES.has_key(nodename):
			stderr("no such node '%s' defined" % nodename)
			sys.exit(1)

		for group in get_groups(nodename):
			if not group in groups:
				groups.append(group)

#	groups.sort()							# group order is important

	for group in groups:
		if group in IGNORE_GROUPS:
			if not OPT_FILTER_IGNORED:
				print '%s (ignored)' % group
		else:
			print group


def get_nodes_in_groups(nodegroups):
	'''returns the nodes that are in [groups]'''

	arr = []

	nodes = NODES.keys()

	for nodegroup in nodegroups:
		for node in nodes:
			if nodegroup in NODES[node] and not node in arr:
				arr.append(node)

	return arr


def list_nodegroups(nodegroups):
	all_groups = make_all_groups()

	for nodegroup in nodegroups:
		if not nodegroup in all_groups:
			stderr("no such nodegroup '%s' defined" % nodegroup)
			sys.exit(1)

	arr = get_nodes_in_groups(nodegroups)
	arr.sort()

	for node in arr:
		if node in IGNORE_GROUPS:
			if OPT_INTERFACE:
				node = get_node_interface(node)

			if not OPT_FILTER_IGNORED:
				print '%s (ignored)' % node
		else:
			if OPT_INTERFACE:
				node = get_node_interface(node)

			print node


def list_commands(cmds):
	'''display command setting'''

	for cmd in cmds:
		if cmd == 'diff':
			print DIFF_CMD

		elif cmd == 'ssh':
			print SSH_CMD

		elif cmd == 'rsync':
			print RSYNC_CMD

		elif cmd == 'synctool':
			print SYNCTOOL_CMD

		else:
			stderr("no such command '%s' available in synctool" % cmd)


def set_action(a, opt):
	global ACTION, ACTION_OPTION

	if ACTION > 0:
		stderr('the options %s and %s can not be combined' % (ACTION_OPTION, opt))
		sys.exit(1)

	ACTION = a
	ACTION_OPTION = opt


def usage():
	print 'usage: %s [options] [<argument>]' % os.path.basename(sys.argv[0])
	print 'options:'
	print '  -h, --help               Display this information'
	print '  -c, --conf=dir/file      Use this config file'
	print '                           (default: %s)' % DEFAULT_CONF
	print '  -l, --list-nodes         List all configured nodes'
	print '  -L, --list-groups        List all configured groups'
	print '  -n, --node=nodelist      List all groups this node is in'
	print '  -g, --group=grouplist    List all nodes in this group'
	print '  -i, --interface          List selected nodes by interface'
	print '  -f, --filter-ignored     Do not list ignored nodes and groups'
	print
	print '  -C, --command=command    Display setting for command'
	print '  -p, --numproc            Display numproc setting'
	print '  -m, --masterdir          Display the masterdir setting'
	print '      --prefix             Display installation prefix'
	print '      --nodename           Display my nodename'
	print '  -v, --version            Display synctool version'
	print
	print 'A node/group list can be a single value, or a comma-separated list'
	print 'A command is a list of these: diff, ssh, rsync, synctool'
	print
	print 'synctool-config by Walter de Jong <walter@heiho.net> (c) 2009-2011'


def get_options():
	global CONF_FILE, ARG_NODENAMES, ARG_GROUPS, ARG_CMDS
	global OPT_FILTER_IGNORED, OPT_INTERFACE

	progname = os.path.basename(sys.argv[0])

	if len(sys.argv) <= 1:
		usage()
		sys.exit(1)

	try:
		opts, args = getopt.getopt(sys.argv[1:], 'hc:mlLn:g:ifC:pv',
			['help', 'conf=', 'masterdir', 'list-nodes', 'list-groups',
			'node=', 'group=', 'interface', 'filter-ignored', 'command',
			'numproc', 'version', 'prefix', 'nodename'])

	except getopt.error, (reason):
		print
		print '%s: %s' % (progname, reason)
		print
		usage()
		sys.exit(1)

	except getopt.GetoptError, (reason):
		print
		print '%s: %s' % (progname, reason)
		print
		usage()
		sys.exit(1)

	except:
		usage()
		sys.exit(1)

	if args != None and len(args) > 0:
		stderr('error: excessive arguments on command-line')
		sys.exit(1)

	errors = 0

	for opt, arg in opts:
		if opt in ('-h', '--help', '-?'):
			usage()
			sys.exit(1)

		if opt in ('-c', '--conf'):
			CONF_FILE=arg
			continue

		if opt in ('-m', '--masterdir'):
			set_action(ACTION_MASTERDIR, '--masterdir')
			continue

		if opt in ('-l', '--list-nodes'):
			set_action(ACTION_LIST_NODES, '--list-nodes')
			continue

		if opt in ('-L', '--list-groups'):
			set_action(ACTION_LIST_GROUPS, '--list-groups')
			continue

		if opt in ('-n', '--node'):
			set_action(ACTION_NODES, '--node')
			ARG_NODENAMES = string.split(arg, ',')
			continue

		if opt in ('-g', '--group'):
			set_action(ACTION_GROUPS, '--group')
			ARG_GROUPS = string.split(arg, ',')
			continue

		if opt in ('-i', '--interface'):
			OPT_INTERFACE = True
			continue

		if opt in ('-f', '--filter-ignored'):
			OPT_FILTER_IGNORED = True
			continue

		if opt in ('-C', '--command'):
			set_action(ACTION_CMDS, '--command')
			ARG_CMDS = string.split(arg, ',')
			continue

		if opt in ('-p', '--numproc'):
			set_action(ACTION_NUMPROC, '--numproc')
			continue

		if opt in ('-v', '--version'):
			set_action(ACTION_VERSION, '--version')
			continue

		if opt == '--prefix':
			set_action(ACTION_PREFIX, '--prefix')
			continue

		if opt == '--nodename':
			set_action(ACTION_NODENAME, '--nodename')
			continue

		stderr("unknown command line option '%s'" % opt)
		errors = errors + 1

	if errors:
		usage()
		sys.exit(1)

	if not ACTION:
		usage()
		sys.exit(1)


if __name__ == '__main__':
	get_options()

	if ACTION == ACTION_VERSION:
		print VERSION
		sys.exit(0)

	read_config()

	if ACTION == ACTION_LIST_NODES:
		list_all_nodes()

	elif ACTION == ACTION_LIST_GROUPS:
		list_all_groups()

	elif ACTION == ACTION_NODES:
		if not ARG_NODENAMES:
			stderr("option '--node' requires an argument; the node name")
			sys.exit(1)

		list_nodes(ARG_NODENAMES)

	elif ACTION == ACTION_GROUPS:
		if not ARG_GROUPS:
			stderr("option '--node-group' requires an argument; the node group name")
			sys.exit(1)

		list_nodegroups(ARG_GROUPS)

	elif ACTION == ACTION_MASTERDIR:
		print MASTERDIR

	elif ACTION == ACTION_CMDS:
		list_commands(ARG_CMDS)

	elif ACTION == ACTION_NUMPROC:
		print NUM_PROC

	elif ACTION == ACTION_PREFIX:
		print os.path.abspath(os.path.dirname(sys.argv[0]))

	elif ACTION == ACTION_NODENAME:
		add_myhostname()
		
		if NODENAME == None:
			stderr('unable to determine my nodename, please check %s' % CONF_FILE)
			sys.exit(1)
		
		if NODENAME in IGNORE_GROUPS:
			if not OPT_FILTER_IGNORED:
				if OPT_INTERFACE:
					print 'none (%s ignored)' % get_node_interface(NODENAME)
				else:
					print 'none (%s ignored)' % NODENAME
			
			sys.exit(0)
		
		if OPT_INTERFACE:
			print get_node_interface(NODENAME)
		else:
			print NODENAME
	
	else:
		raise RuntimeError, 'bug: unknown ACTION %d' % ACTION

# EOB
