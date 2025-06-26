import re

substitutions = {
    "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",  # legal ISO currency codes
    "LS": r"\$|\xe2\x82\xac|\u20ac|\£|\u20b9|\¥|",  # legal currency symbols - Euro(cp1252, utf-8)
    "PLYR": r"\s?(?P<PNAME>.+?)",
    "CUR": r"(\$|\xe2\x82\xac|\u20ac||\£|\u20b9|\¥|)",
    "BRKTS": r"(\(button\) |\(small blind\) |\(big blind\) |\(button blind\) |\(button\) \(small blind\) |\(small blind\) \(button\) |\(big blind\) \(button\) |\(small blind/button\) |\(button\) \(big blind\) )?",
}
re_WinningRankOne = re.compile(
    r"%(PLYR)s wins the tournament and receives %(CUR)s(?P<AMT>[,\.0-9]+) - congratulations!$"
    % substitutions,
    re.MULTILINE,
)


def test_re_WinningRankOne():
    text = """jeje_sat wins the tournament and receives €0.75 - congratulations!"""
    match = re_WinningRankOne.search(text)
    assert match is not None
    assert match.group("PNAME") == "jeje_sat"
    assert match.group("AMT") == "0.75"
