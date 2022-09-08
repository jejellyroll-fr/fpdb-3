import subprocess

argu = r"select avg(riverEquity(p1)) from game='holdem', p1='AK', p2='JT'"
argu2 = r"select /* Start equity stats */avg(riverEquity(PLAYER_1)) as PLAYER_1_equity1,count(winsHi(PLAYER_1)) as PLAYER_1_winsHi1,count(tiesHi(PLAYER_1)) as PLAYER_1_tiesHi1,avg(riverEquity(PLAYER_2)) as PLAYER_2_equity1,count(winsHi(PLAYER_2)) as PLAYER_2_winsHi1,count(tiesHi(PLAYER_2)) as PLAYER_2_tiesHi1/* End equity stats */ from game='omahahi5', syntax='Generic',board='2s5sTs',PLAYER_1='4h6c5c9h9d',PLAYER_2='10%'"
#subprocess.call(['java', '-jar', './ppt/p2.jar'])
#subprocess.call(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL'])
subprocess.call(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL', argu])
subprocess.call(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL', argu2])