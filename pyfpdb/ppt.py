import subprocess

argu = str("propokertools.cli.RunPQL \"select avg(riverEquity(p1)) from game='holdem', p1='AK', p2='JT'\"")
subprocess.call(['java', '-jar', './ppt/p2.jar'])
