import subprocess
import platform

argu = r"select avg(riverEquity(p1)) from game='holdem', p1='AK', p2='JT'"
argu2 = r"select /* Start equity stats */avg(riverEquity(PLAYER_1)) as PLAYER_1_equity1,count(winsHi(PLAYER_1)) as PLAYER_1_winsHi1,count(tiesHi(PLAYER_1)) as PLAYER_1_tiesHi1,avg(riverEquity(PLAYER_2)) as PLAYER_2_equity1,count(winsHi(PLAYER_2)) as PLAYER_2_winsHi1,count(tiesHi(PLAYER_2)) as PLAYER_2_tiesHi1/* End equity stats */ from game='omahahi5', syntax='Generic',board='2s5sTs',PLAYER_1='4h6c5c9h9d',PLAYER_2='10%'"
#subprocess.call(['java', '-jar', './ppt/p2.jar'])
#subprocess.call(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL'])
#subprocess.call(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL', argu])
result = subprocess.check_output(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL', argu2])
print(result)
if platform.system() == 'Windows':
    result = result.decode().replace(' = ', '\r\n').split('\r\n')
else:
    result = result.decode().replace(' = ', '\n').split('\n')
print(result)
print(type(result))
res_dct, res_dct2= {}, {}
res_dct['hand Player1'] = '4h6c5c9h9d'
res_dct2['hand Player2'] = '10%'

res_dct3 = {result[i]: result[i + 1] for i in range(0, len(result), 2)}
d2 = dict(list(res_dct3.items())[len(res_dct3)//2:])
d1 = dict(list(res_dct3.items())[:len(res_dct3)//2])

print(res_dct2)
res_dct.update(d1)
res_dct2.update(d2)
print(res_dct)
print(res_dct2)
res_dct.update(res_dct2)
print(res_dct)