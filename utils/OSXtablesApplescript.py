import sys
import subprocess

# AppleScript 
script = '''
    tell application "System Events"
        set window_list to ""
        set process_list to processes where background only is false
        repeat with proc in process_list
            set proc_name to name of proc
            set proc_id to unix id of proc
            try
                set window_names to name of every window of proc
                set window_sizes to size of every window of proc
                set window_positions to position of every window of proc
                repeat with i from 1 to count of window_names
                    set win_name to item i of window_names
                    set win_size to item i of window_sizes
                    set win_position to item i of window_positions
                    -- Construire une chaîne pour chaque fenêtre
                    set win_info to proc_name & "||" & proc_id & "||" & win_name & "||" & (item 1 of win_size) & "," & (item 2 of win_size) & "||" & (item 1 of win_position) & "," & (item 2 of win_position)
                    if window_list is equal to "" then
                        set window_list to win_info
                    else
                        set window_list to window_list & ";;" & win_info
                    end if
                end repeat
            end try
        end repeat
        return window_list
    end tell
'''

print("Exécution du script AppleScript...")

# Execute AppleScript
proc = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
output, error = proc.communicate()

# Verify errors
if error:
    print(f"Erreur AppleScript: {error.decode('utf-8')}")
    sys.exit(1)

# Decode output 
output_decode = output.decode('utf-8').strip()

# show output
print("Sortie brute de l'AppleScript :")
print(output_decode)

# Split output into entries
window_entries = output_decode.split(';;')

liste_fenetres = []

for entry in window_entries:
    fields = entry.split('||')
    if len(fields) == 5:
        proc_name, pid, win_name, size_str, position_str = fields
        width, height = map(int, size_str.split(','))
        x, y = map(int, position_str.split(','))
        liste_fenetres.append({
            "proc": proc_name,
            "pid": int(pid),
            "name": win_name,
            "size": {"width": width, "height": height},
            "position": {"x": x, "y": y}
        })
    else:
        print(f"Entrée mal formatée : {entry}")

# Show structured output
print("\nSortie structurée :")
for fenetre in liste_fenetres:
    print(fenetre)
