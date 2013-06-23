#
#	synctool.pkg.zypper.py		WJ111
#
#   synctool Copyright 2013 Walter de Jong <walter@heiho.net>
#
#   synctool COMES WITH NO WARRANTY. synctool IS FREE SOFTWARE.
#   synctool is distributed under terms described in the GNU General Public
#   License.
#

import synctool.lib
import synctool.pkgclass


class SyncPkgZypper(synctool.pkgclass.SyncPkg):
	'''package installer class for zypper'''

	def __init__(self):
		super(SyncPkgZypper, self).__init__(self)


	def list(self, pkgs = None):
		super(SyncPkgZypper, self).list(self, pkgs)

		cmd = 'rpm -qa'			# zypper has no 'list-installed' ?

		if pkgs:
			cmd = cmd + ' ' + ' '.join(pkgs)

		synctool.lib.DRY_RUN = False
		synctool.lib.shell_command(cmd)
		synctool.lib.DRY_RUN = self.dryrun


	def install(self, pkgs):
		super(SyncPkgZypper, self).install(self, pkgs)

		cmd = ('zypper --non-interactive install '
			'--auto-agree-with-licenses ' + ' '.join(pkgs))

		synctool.lib.shell_command(cmd)


	def remove(self, pkgs):
		super(SyncPkgZypper, self).remove(self, pkgs)

		cmd = 'zypper --non-interactive remove ' + ' '.join(pkgs)

		synctool.lib.shell_command(cmd)


	def update(self):
		super(SyncPkgZypper, self).update(self)

		synctool.lib.shell_command('zypper --non-interactive refresh')


	def upgrade(self):
		super(SyncPkgZypper, self).upgrade(self)

		if self.dryrun:
			cmd = 'zypper list-updates'
		else:
			cmd = ('zypper --non-interactive update '
				'--auto-agree-with-licenses')

		synctool.lib.DRY_RUN = False
		synctool.lib.shell_command(cmd)
		synctool.lib.DRY_RUN = self.dryrun


	def clean(self):
		super(SyncPkgZypper, self).clean(self)

		synctool.lib.DRY_RUN = False
		synctool.lib.shell_command('zypper clean')
		synctool.lib.DRY_RUN = self.dryrun

# EOB
