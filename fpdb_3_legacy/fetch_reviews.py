from __future__ import annotations

import json
import subprocess


def run_gh_command(command):
    try:
        # unexpected encoding from gh cli on windows sometimes, force utf-8 decoding if possible or ignore errors
        result = subprocess.run(command, capture_output=True, text=False)  # Get bytes
        if result.returncode != 0:
            print(f"Error running command: {command}")
            print(result.stderr.decode("utf-8", errors="replace"))
            return None
        return json.loads(result.stdout.decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"Exception running {command}: {e}")
        return None


def main():
    print("Fetching PR comments...")
    # General issue comments
    issue_comments = run_gh_command(["gh", "api", "repos/jejellyroll-fr/fpdb-new/issues/89/comments"])

    print("Fetching PR review comments (inline)...")
    # Inline review comments
    review_comments = run_gh_command(["gh", "api", "repos/jejellyroll-fr/fpdb-new/pulls/89/comments"])

    all_findings = []

    if issue_comments:
        for c in issue_comments:
            user = c.get("user", {}).get("login", "unknown")
            body = c.get("body", "")
            if "coderabbitai" in user:
                all_findings.append({"type": "general", "body": body, "url": c.get("html_url")})

    if review_comments:
        for c in review_comments:
            user = c.get("user", {}).get("login", "unknown")
            body = c.get("body", "")
            path = c.get("path", "")
            line = c.get("line", "?")
            if "coderabbitai" in user:
                all_findings.append(
                    {"type": "inline", "body": body, "path": path, "line": line, "url": c.get("html_url")}
                )

    print(f"Found {len(all_findings)} comments from CodeRabbit AI.")

    # Save to a file for the agent to read safely
    with open("coderabbit_reviews.json", "w", encoding="utf-8") as f:
        json.dump(all_findings, f, indent=2)

    # Print summary to stdout
    for i, finding in enumerate(all_findings):
        print(f"--- Finding {i + 1} ({finding['type']}) ---")
        if finding["type"] == "inline":
            print(f"File: {finding['path']}:{finding['line']}")
        print(finding["body"][:200] + "..." if len(finding["body"]) > 200 else finding["body"])
        print("-" * 20)


if __name__ == "__main__":
    main()
