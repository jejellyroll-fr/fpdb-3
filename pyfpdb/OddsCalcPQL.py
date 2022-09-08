import subprocess

class OddsCalcPQL:
    def __init__(self) -> None:
        pass
  
        
       

    def calcBasePQL(self):
        argu2 = r"select /* Start equity stats */avg(riverEquity(PLAYER_1)) as PLAYER_1_equity1,count(winsHi(PLAYER_1)) as PLAYER_1_winsHi1,count(tiesHi(PLAYER_1)) as PLAYER_1_tiesHi1,avg(riverEquity(PLAYER_2)) as PLAYER_2_equity1,count(winsHi(PLAYER_2)) as PLAYER_2_winsHi1,count(tiesHi(PLAYER_2)) as PLAYER_2_tiesHi1/* End equity stats */ from game='omahahi5', syntax='Generic',board='2s5sTs',PLAYER_1='4h6c5c9h9d',PLAYER_2='10%'"
        result = subprocess.check_output(['java', '-cp', './ppt/p2.jar', 'propokertools.cli.RunPQL', argu2])
        result = result.decode().replace(' = ', '\r\n').split('\r\n')
        res_dct = {}
        res_dct['hand Player1'],res_dct['hand Player2'] = '4h6c5c9h9d','10%'
        res_dct2 = {result[i]: result[i + 1] for i in range(0, len(result), 2)}
        res_dct = res_dct|res_dct2
        return res_dct