#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import json
import sys

try:
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_comments.py <pr_number>")
        sys.exit(1)

    pr_number = sys.argv[1]
    result = subprocess.run(
        ["gh", "pr", "view", pr_number, "--json", "comments"], capture_output=True, text=True, encoding="utf-8"
    )

    if result.returncode != 0:
        print("Error running gh:")
        print(result.stderr)
        sys.exit(result.returncode)

    data = json.loads(result.stdout)
    comments = data.get("comments", [])
    print(f"Found {len(comments)} comments.")
    for i, comment in enumerate(comments):
        print(f"--- Comment {i + 1} by {comment.get('author', {}).get('login', 'Unknown')} ---")
        print(comment.get("body", ""))
        print("\n")
except json.JSONDecodeError as e:
    print(f"JSON decode error: {e}")
    sys.exit(1)
except FileNotFoundError:
    print("Error: 'gh' command not found. Please install GitHub CLI.")
    sys.exit(127)
except Exception as e:
    print(f"Exception: {e}")
    sys.exit(1)
