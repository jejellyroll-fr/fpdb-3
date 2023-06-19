import gettext

from Configuration import PYFPDB_PATH

path = f"{PYFPDB_PATH}/locale"

gettext.bindtextdomain('fpdb', path)
gettext.textdomain('fpdb')
_ = gettext.gettext
fr_translation = gettext.translation('fpdb', path, languages=['fr'])
fr_translation.install()

print(_('Confirm deleting and recreating tables'))


