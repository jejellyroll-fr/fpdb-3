#!/bin/bash
# FPDB-3 Legacy - Packaging Experimentation Script
# Usage: ./build_experiment.sh [nuitka|briefcase|pyoxidizer]

set -e

BUILDER=$1

if [ -z "$BUILDER" ]; then
    echo "Usage: $0 [nuitka|briefcase|pyoxidizer]"
    exit 1
fi

case "$BUILDER" in
    nuitka)
        echo "=== Building with Nuitka ==="
        # Ensure Nuitka is installed
        if ! python -c "import nuitka" &> /dev/null; then
            echo "Installing Nuitka..."
            uv pip install nuitka
        fi
        
        echo "Running Nuitka compilation..."
        python -m nuitka --mode=app \
            --enable-plugin=pyside6 \
            --include-data-dir=gfx=gfx \
            --include-data-dir=icons=icons \
            --include-data-dir=fonts=fonts \
            --include-data-dir=locale=locale \
            --include-data-files=HUD_config.xml=HUD_config.xml \
            --output-dir=dist-nuitka \
            fpdb_3_legacy/fpdb.pyw
        
        echo "Nuitka build finished! Check dist-nuitka/fpdb.dist/"
        ;;
        
    briefcase)
        echo "=== Building with Briefcase ==="
        # Ensure Briefcase is installed
        if ! command -v briefcase &> /dev/null; then
            echo "Installing Briefcase..."
            uv pip install briefcase
        fi
        
        echo "Initializing Briefcase app..."
        # Briefcase will read [tool.briefcase] from pyproject.toml
        briefcase create
        
        echo "Building Briefcase app..."
        briefcase build
        
        echo "Briefcase build finished! Use 'briefcase run' to run it, or 'briefcase package' to generate installers."
        ;;
        
    pyoxidizer)
        echo "=== Building with PyOxidizer ==="
        # Ensure PyOxidizer is installed
        if ! command -v pyoxidizer &> /dev/null; then
            echo "Installing PyOxidizer..."
            cargo install --locked pyoxidizer || pip install pyoxidizer
        fi
        
        echo "Running PyOxidizer build..."
        pyoxidizer --system-rust build --release
        
        echo "PyOxidizer build finished! Check build/aarch64-apple-darwin/release/install/"
        ;;
        
    *)
        echo "Unknown builder: $BUILDER"
        echo "Supported builders: nuitka, briefcase, pyoxidizer"
        exit 1
        ;;
esac
