import xcffib, xcffib.xproto

# Connect to the X server
xconn = xcffib.Connection()
root = xconn.get_setup().roots[xconn.pref_screen].root

def getAtom(name):
    return xconn.core.InternAtom(False, len(name), name).reply().atom

nclatom = getAtom("_NET_CLIENT_LIST")
winatom = getAtom("WINDOW")
wnameatom = getAtom("_NET_WM_NAME")
utf8atom = getAtom("UTF8_STRING")

def get_window_title(window_id):
    reply = xconn.core.GetProperty(False, window_id, wnameatom, utf8atom, 0, (2**32) - 1).reply()
    if reply.value_len > 0:
        return reply.value.to_string()
    else:
        return ""


# Get the client list
reply = xconn.core.GetProperty(False, root, nclatom, winatom, 0, (2**32) - 1).reply()
window_ids = reply.value.to_atoms()

# Iterate over the windows and print their titles
for window_id in window_ids:
    window_title = get_window_title(window_id)
    print(window_title)

# Disconnect from the X server
xconn.disconnect()








