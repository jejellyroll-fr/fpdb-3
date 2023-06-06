try:
    # try to import sys and cdecimal modules
    import sys, cdecimal

    # set the decimal module to use cdecimal
    sys.modules['decimal'] = cdecimal
    from cdecimal import *

# if ImportError occurs, use the built-in decimal module
except ImportError:
    from decimal import *

