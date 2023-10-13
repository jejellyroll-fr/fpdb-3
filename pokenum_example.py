import Pokenum_api_call

response = Pokenum_api_call.run_pokenum(
    method="-mc",
    iterations="10000",
    game="-h",
    hand=['As', 'Ad', '-', 'Ks', 'Qs'],
    board=["--"],
    dead=["/"]
)
print(response)

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-h",
    hand=['As', 'Ad', '-', 'Ks', 'Qs'],
    board=["--"],
    dead=["/"]
)
print(response)

# $ pokenum -o As Kh Qs Jh - 8h 8d 7h 6d:

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-o",
    hand=['As', 'Kh', 'Qs', 'Jh', '-', '8h', '8d', '7h', '6d'],
    board=["--"],
    dead=["/"]
)
print(response)

# $ pokenum -mc 10000 -o As Kh Qs Jh - 8h 8d 7h 6d:

response = Pokenum_api_call.run_pokenum(
    method="-mc",
    iterations="10000",
    game="-o",
    hand=['As', 'Kh', 'Qs', 'Jh', '-', '8h', '8d', '7h', '6d'],
    board=["--"],
    dead=["/"]
)
print(response)

# pokenum -mc 10000 -o85 As Kh Qs Jh Ts - 8h 8d 7h 6d 9c

response = Pokenum_api_call.run_pokenum(
    method="-mc",
    iterations="10000",
    game="-o85",
    hand=['As', 'Kh', 'Qs', 'Jh', 'Ts', '-', '8h', '8d', '7h', '6d', '9c'],
    board=["--"],
    dead=["/"]
)
print(response)

# pokenum  -o As Kh Qs Jh  - 8h 8d 7h 6d  -- 8s Ts Jc

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-o",
    hand=['As', 'Kh', 'Qs', 'Jh',  '8d', '7h', '6d', '9c'],
    board=["--", '8s', 'Ts', 'Jc'],
    dead=["/"]
)
print(response)

# pokenum  -o As Kh Qs Jh  - 8h 8d 7h 6d  -- 8s Ts Jc Ad

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-o",
    hand=['As', 'Kh', 'Qs', 'Jh',  '8d', '7h', '6d', '9c'],
    board=["--", '8s', 'Ts', 'Jc', 'Ad'],
    dead=["/"]
)
print(response)

# pokenum  -o5 As Ad Kh Qs Jh  - 8h 8d 7h 6d 5d -- 8s Ts Jc 

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-o5",
    hand=['As','Ad', 'Kh', 'Qs', 'Jh',  '8d', '7h', '6d', '9c', '5d'],
    board=["--", '8s', 'Ts', 'Jc', ],
    dead=["/"]
)
print(response)

# $ pokenum -7s As Ah Ts Th 8h 8d - Kc Qc Jc Td 3c 2d / 5c 6c 2s Jh

response = Pokenum_api_call.run_pokenum(
    method="",
    iterations="",
    game="-7s",
    hand=['As','Ah', 'Ts', 'Th', '8h', '8d', '-',  'Kc', 'Qc', 'Jc', 'Td', '3c', '2d'],
    board=["--"],
    dead=["/", '5c', '6c', '2s', 'Jh']
)
print(response)