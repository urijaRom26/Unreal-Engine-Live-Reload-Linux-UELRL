#!/usr/bin/env python3
"""Enable the LiveReload plugin in a C++ Unreal Engine project (Linux).

  ue_live_reload_setup.py <project-dir-or-uproject> [--local] [--dry-run]
                          [--engine /path/to/UnrealEngine]

What it does, idempotently:

  1. makes the plugin reachable from the project
       default ("shared"): adds this repo's directory to
         "AdditionalPluginDirectories" in the .uproject, so ONE copy of the
         plugin serves every project on the machine.
       --local: copies the plugin to <Project>/Plugins/LiveReload instead.
  2. enables the "LiveReload" plugin in the .uproject
  3. patches the primary game module so it returns
         SupportsDynamicReloading() == false
     Without step 3 the first reload SIGSEGVs the editor inside
     TDeferredRegistry::AddRegistration (see docs/how-it-works.md).

Then rebuild the project once so the plugin module is compiled, and reopen
the editor. Blueprint-only projects have no game module to reload - skip them.

Engine root is taken from --engine, else $UE_ROOT, else /opt/unreal-engine.
"""
import json
import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_NAME = "LiveReload"
PLUGIN_SRC = os.path.join(REPO_ROOT, PLUGIN_NAME)

IMPL_RE = re.compile(
    r'IMPLEMENT_PRIMARY_GAME_MODULE\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*"([^"]+)"\s*\)\s*;?'
)

SKIP_DIRS = {"Binaries", "Intermediate", "Saved", "__pycache__", ".git"}


def find_uproject(arg):
    path = os.path.abspath(arg)
    if path.endswith(".uproject"):
        return path
    if not os.path.isdir(path):
        sys.exit("not a directory: %s" % path)
    candidates = [f for f in sorted(os.listdir(path)) if f.endswith(".uproject")]
    if len(candidates) != 1:
        sys.exit("expected exactly one .uproject in %s, found %s" % (path, candidates))
    return os.path.join(path, candidates[0])


def load_uproject(uproject):
    with open(uproject, encoding="utf-8-sig") as fh:
        return json.loads(fh.read())


def save_uproject(uproject, data):
    with open(uproject, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent="\t")
        fh.write("\n")


def copy_plugin(project_dir):
    dest = os.path.join(project_dir, "Plugins", PLUGIN_NAME)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(
        PLUGIN_SRC, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.so", "*.debug", "*.sym")
    )
    return dest


def patch_uproject(uproject, project_dir, local, dry_run):
    data = load_uproject(uproject)
    changed = []

    dirs = data.get("AdditionalPluginDirectories", [])
    if local:
        if dirs:
            data["AdditionalPluginDirectories"] = dirs = []
            changed.append("AdditionalPluginDirectories cleared (local install)")
    else:
        rel = os.path.relpath(REPO_ROOT, project_dir).replace(os.sep, "/")
        if rel not in dirs:
            dirs.append(rel)
            data["AdditionalPluginDirectories"] = dirs
            changed.append("AdditionalPluginDirectories += %s" % rel)

    plugins = data.setdefault("Plugins", [])
    entry = next((p for p in plugins if p.get("Name") == PLUGIN_NAME), None)
    if entry is None:
        plugins.append({"Name": PLUGIN_NAME, "Enabled": True})
        changed.append("plugin %s enabled" % PLUGIN_NAME)
    elif not entry.get("Enabled"):
        entry["Enabled"] = True
        changed.append("plugin %s re-enabled" % PLUGIN_NAME)

    if not changed:
        print("  .uproject already configured")
        return
    if dry_run:
        print("  would: " + "; ".join(changed))
        return
    save_uproject(uproject, data)
    print("  " + "; ".join(changed))


def patch_module(project_dir, dry_run):
    source_root = os.path.join(project_dir, "Source")
    if not os.path.isdir(source_root):
        print("  no Source/ - blueprint-only project, this plugin is useless there")
        return
    for root, dirs, files in os.walk(source_root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if not name.endswith(".cpp"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8-sig") as fh:
                text = fh.read()
            match = IMPL_RE.search(text)
            if not match:
                continue
            rel = os.path.relpath(path, project_dir)
            if "SupportsDynamicReloading" in text:
                print("  %s already opts out of dynamic unloading" % rel)
                return
            impl, module, module_string = match.groups()
            replacement = (
                "class F%sModule : public FDefaultGameModuleImpl\n"
                "{\n"
                "public:\n"
                "\tvirtual bool SupportsDynamicReloading() override { return false; }\n"
                "};\n"
                'IMPLEMENT_PRIMARY_GAME_MODULE(F%sModule, %s, "%s");'
                % (module, module, module, module_string)
            )
            new_text = text[: match.start()] + replacement + text[match.end() :]
            if '#include "Modules/ModuleManager.h"' not in new_text:
                new_text = '#include "Modules/ModuleManager.h"\n' + new_text
            if dry_run:
                print("  would patch %s (%s)" % (rel, impl))
                return
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
            print("  patched %s (%s -> F%sModule)" % (rel, impl, module))
            return
    print("  WARNING: no IMPLEMENT_PRIMARY_GAME_MODULE found under Source/")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Enable the LiveReload plugin in a C++ Unreal Engine project."
    )
    parser.add_argument("project", help="project directory or .uproject")
    parser.add_argument(
        "--local", action="store_true", help="copy the plugin into <Project>/Plugins instead of sharing it"
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument(
        "--engine", default=os.environ.get("UE_ROOT", "/opt/unreal-engine"), help="Unreal Engine root"
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    local = args.local
    engine = args.engine

    if not os.path.isdir(PLUGIN_SRC):
        sys.exit("plugin not found at %s - run this script from the repository" % PLUGIN_SRC)

    uproject = find_uproject(args.project)
    project_dir = os.path.dirname(uproject)
    name = os.path.splitext(os.path.basename(uproject))[0]

    print(uproject)
    if local and not dry_run:
        print("  plugin copied to %s" % os.path.relpath(copy_plugin(project_dir), project_dir))
    patch_uproject(uproject, project_dir, local, dry_run)
    patch_module(project_dir, dry_run)

    if dry_run:
        print("\n  dry run - nothing written")
        return

    build = os.path.join(engine, "Engine/Build/BatchFiles/Linux/Build.sh")
    lib = os.path.join(project_dir, "Binaries/Linux/libUnrealEditor-%s.so" % name)
    print(
        "\n  next: build once so the plugin module is compiled for this project\n"
        "\n"
        "    cd \"%s\"\n"
        "    rm -f \"%s\"      # unlink only if the editor is open right now\n"
        "    \"%s\" %sEditor Linux Development -Project=\"%s\" -WaitMutex > Saved/build.log 2>&1\n"
        "    grep -E \"error:|Result:\" Saved/build.log\n"
        "\n"
        "  then reopen the editor and check the toolset is there:\n"
        "\n"
        "    python3 \"%s\" --status\n"
        % (project_dir, lib, build, name, uproject, os.path.join(REPO_ROOT, "scripts/ue_live_reload.py"))
    )


if __name__ == "__main__":
    main()
