# pyoxidizer.bzl configuration for FPDB-3
# See https://pyoxidizer.readthedocs.io/ for documentation.

def make_dist():
    # PyOxidizer 0.24 cannot read the latest python-build-standalone v8
    # archives. These 2024 distributions are still v7-compatible and avoid
    # depending on PyOxidizer's much older bundled 2022 Python.
    distributions = {
        "aarch64-apple-darwin": [
            "https://github.com/astral-sh/python-build-standalone/releases/download/20240713/cpython-3.11.9%2B20240713-aarch64-apple-darwin-pgo%2Blto-full.tar.zst",
            "4cb03ac8b12366038059045aa8405794b96d9b3c73919c157a98f73e21b13031",
        ],
        "x86_64-pc-windows-msvc": [
            "https://github.com/astral-sh/python-build-standalone/releases/download/20240713/cpython-3.11.9%2B20240713-x86_64-pc-windows-msvc-shared-pgo-full.tar.zst",
            "126ddab6d6f6fbfe2f3e73176476fdf306d3ccfac67f8542d12ce0c998142644",
        ],
        "x86_64-unknown-linux-gnu": [
            "https://github.com/astral-sh/python-build-standalone/releases/download/20240713/cpython-3.11.9%2B20240713-x86_64-unknown-linux-gnu-pgo-full.tar.zst",
            "3c60c8df9722f64138a3e5103dc7df12eacb9c16fdf4e172537f878c2425ea19",
        ],
    }
    if BUILD_TARGET_TRIPLE not in distributions:
        fail("unsupported PyOxidizer build target: " + BUILD_TARGET_TRIPLE)

    distribution = distributions[BUILD_TARGET_TRIPLE]
    return PythonDistribution(
        url=distribution[0],
        sha256=distribution[1],
    )

def has_prefix(value, prefix):
    return value[:len(prefix)] == prefix

def keep_pip_resource(resource):
    name = resource.name
    if has_prefix(name, "PySide6.scripts."):
        return False
    if has_prefix(name, "PySide6.support."):
        return False
    return True

def make_exe(dist):
    policy = dist.make_python_packaging_policy()
    # Classify Python files/resources so PyOxidizer can embed what it supports,
    # while falling back to filesystem resources for the legacy .pyw launcher.
    policy.set_resource_handling_mode("classify")
    policy.resources_location = "filesystem-relative:lib"
    policy.resources_location_fallback = None
    
    config = dist.make_python_interpreter_config()
    config.filesystem_importer = True
    config.oxidized_importer = False
    config.module_search_paths = [
        "$ORIGIN/lib",
        "$ORIGIN",
        "$ORIGIN/fpdb_3_legacy",
        # macOS .app layout: only the launcher may live in Contents/MacOS
        # (codesign refuses to seal a bundle whose MacOS directory holds
        # non-code), so the payload sits in Contents/Resources next to it.
        "$ORIGIN/../Resources/lib",
        "$ORIGIN/../Resources",
        "$ORIGIN/../Resources/fpdb_3_legacy",
    ]
    config.run_command = "\n".join([
        "import os",
        "import runpy",
        "import sys",
        "sys.frozen = 'pyoxidizer'",
        "root = os.path.dirname(sys.executable)",
        "bundle_resources = os.path.join(os.path.dirname(root), 'Resources')",
        "if os.path.isdir(os.path.join(bundle_resources, 'fpdb_3_legacy')):",
        "    root = bundle_resources",
        "legacy_dir = os.path.join(root, 'fpdb_3_legacy')",
        "sys.path.insert(0, root)",
        "sys.path.insert(0, legacy_dir)",
        "os.chdir(root)",
        "if len(sys.argv) > 1 and sys.argv[1] == '--hud':",
        "    sys.argv.pop(1)",
        "    runpy.run_path(os.path.join(legacy_dir, 'HUD_main.pyw'), run_name='__main__')",
        "else:",
        # Helper processes cannot use "python -m" here: this binary is their
        # interpreter. dispatch_run_module is the shared --run-module escape
        # hatch; using it (rather than inlining runpy) keeps the line-buffering
        # the capture log tail depends on identical to the PyInstaller path.
        "    from fpdb_3_legacy.subprocess_launch import dispatch_run_module",
        "    if not dispatch_run_module():",
        "        runpy.run_path(os.path.join(legacy_dir, 'fpdb.pyw'), run_name='__main__')",
    ])
    
    exe = dist.to_python_executable(
        name="fpdb",
        packaging_policy=policy,
        config=config,
    )
    if BUILD_TARGET_TRIPLE == "x86_64-pc-windows-msvc":
        exe.windows_subsystem = "windows"
        exe.windows_runtime_dlls_mode = "when-present"
    
    # Read resources from python packages and include them
    pip_resources = []
    for resource in exe.pip_install([CWD]):
        if keep_pip_resource(resource):
            pip_resources.append(resource)
    exe.add_python_resources(pip_resources)
    exe.add_python_resources(exe.read_package_root(
        path=CWD,
        packages=["fpdb_3_legacy", "fpdb"],
    ))
    
    # Add external files/assets
    # Note: assets like gfx, locale, fonts might need to be copied relative to the executable at runtime
    return exe

def make_embedded_resources(exe):
    return exe.to_embedded_resources()

def make_install(exe):
    files = FileManifest()
    files.add_python_resource(".", exe)
    files.add_manifest(glob(
        include=[
            CWD + "/fpdb_3_legacy/**/*.py",
            CWD + "/fpdb_3_legacy/**/*.pyw",
            CWD + "/fpdb_3_legacy/**/*.toml",
            CWD + "/fpdb_3_legacy/**/*.xml",
            CWD + "/fpdb_3_legacy/**/*.sql",
            CWD + "/fpdb_3_legacy/**/*.md",
            CWD + "/fpdb_3_legacy/**/*.sh",
            CWD + "/gfx/**/*.png",
            CWD + "/gfx/**/*.svg",
            CWD + "/gfx/**/*.jpg",
            CWD + "/gfx/**/*.ico",
            CWD + "/gfx/**/*.icns",
            CWD + "/gfx/**/*.eps",
            CWD + "/icons/**/*.png",
            CWD + "/icons/**/*.svg",
            CWD + "/icons/**/*.jpg",
            CWD + "/icons/**/*.ico",
            CWD + "/icons/**/*.icns",
            CWD + "/fonts/**/*.ttf",
            CWD + "/locale/**/*.po",
            CWD + "/locale/**/*.mo",
            CWD + "/HUD_config.xml",
        ],
        exclude=[
            "**/__pycache__/**",
            "**/*.pyc",
            "**/.DS_Store",
        ],
        strip_prefix=CWD + "/",
    ))
    files.add_file(
        FileContent(path=CWD + "/HUD_config.xml.example"),
        path="pyfpdb/HUD_config.xml.example",
    )
    return files

register_target("dist", make_dist)
register_target("exe", make_exe, depends=["dist"])
register_target("resources", make_embedded_resources, depends=["exe"], default_build_script=True)
register_target("install", make_install, depends=["exe"], default=True)
resolve_targets()
