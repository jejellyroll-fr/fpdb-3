#!/usr/bin/env bash
# Install Ubuntu packages on a GitHub-hosted runner: apt-install.sh pkg...
#
# The hosted image may include third-party feeds (for example
# packages.microsoft.com) that can return 403 and fail the whole update even
# though these packages come from Ubuntu itself, so only the Ubuntu sources
# are refreshed.
#
# Those sources go through mirror+file:/etc/apt/apt-mirrors.txt, whose first
# entry is azure.archive.ubuntu.com. When that host stops resolving, every apt
# call fails after minutes of timeouts and takes the job down. On failure the
# sources are pointed straight at archive.ubuntu.com and the install is tried
# once more.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 package..." >&2
  exit 2
fi

SOURCES=/etc/apt/sources.list.d/ubuntu.sources
APT_OPTS=(-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)

refresh() {
  if [ -f "$SOURCES" ]; then
    sudo apt-get "${APT_OPTS[@]}" update \
      -o Dir::Etc::sourcelist="sources.list.d/ubuntu.sources" \
      -o Dir::Etc::sourceparts="-" \
      -o APT::Get::List-Cleanup="0"
  else
    # A runner image without the deb822 Ubuntu sources: plain update.
    sudo apt-get "${APT_OPTS[@]}" update
  fi
}

install() {
  sudo apt-get "${APT_OPTS[@]}" install -y "$@"
}

if refresh && install "$@"; then
  exit 0
fi

echo "::warning::The runner's Ubuntu mirror failed; retrying apt with archive.ubuntu.com"
for file in "$SOURCES" /etc/apt/sources.list; do
  if [ -f "$file" ]; then
    sudo sed -i -E \
      -e 's#mirror\+file:/etc/apt/apt-mirrors\.txt#http://archive.ubuntu.com/ubuntu/#g' \
      -e 's#https?://azure\.archive\.ubuntu\.com/ubuntu/?#http://archive.ubuntu.com/ubuntu/#g' \
      "$file"
  fi
done
refresh
install "$@"
