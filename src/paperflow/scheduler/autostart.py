"""Current-user Windows login task for the windowless Core process."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def task_name(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:12]
    return f"PaperFlow-Core-{digest}"


def task_xml(root: Path, pythonw: Path, user: str, *, standalone: bool = False) -> bytes:
    root, pythonw = root.resolve(), pythonw.resolve()
    ET.register_namespace("", NS)
    task = ET.Element(f"{{{NS}}}Task", version="1.2")
    def node(parent, name, text=None):
        element = ET.SubElement(parent, f"{{{NS}}}{name}")
        if text is not None:
            element.text = str(text)
        return element
    info = node(task, "RegistrationInfo")
    node(info, "Description", "PaperFlow Core: current-user login, local scheduling and Zotero bridge")
    trigger = node(node(task, "Triggers"), "LogonTrigger")
    node(trigger, "Enabled", "true")
    node(trigger, "UserId", user)
    node(trigger, "Delay", "PT20S")
    principal = node(node(task, "Principals"), "Principal")
    principal.set("id", "CurrentUser")
    node(principal, "UserId", user)
    node(principal, "LogonType", "InteractiveToken")
    node(principal, "RunLevel", "LeastPrivilege")
    settings = node(task, "Settings")
    for name, value in {"MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
                        "StopIfGoingOnBatteries": "false", "StartWhenAvailable": "true",
                        "Enabled": "true", "Hidden": "true", "ExecutionTimeLimit": "PT0S"}.items():
        node(settings, name, value)
    restart = node(settings, "RestartOnFailure")
    node(restart, "Interval", "PT1M")
    node(restart, "Count", "3")
    actions = node(task, "Actions")
    actions.set("Context", "CurrentUser")
    action = node(actions, "Exec")
    node(action, "Command", pythonw)
    node(action, "Arguments", subprocess.list2cmdline([
        "-m", "paperflow.cli", "zotero", "service", "serve",
        "--data-root" if standalone else "--vault", str(root),
    ]))
    node(action, "WorkingDirectory", root)
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def manage_autostart(root: Path, *, apply: bool = False, remove: bool = False,
                     standalone: bool = False) -> dict:
    if os.name != "nt":
        raise ValueError("login autostart currently supports Windows only")
    if apply and remove:
        raise ValueError("choose apply or remove")
    name = task_name(root)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    def run(args):
        return subprocess.run(["schtasks.exe", *args], capture_output=True, timeout=20, creationflags=flags)
    if remove:
        result = run(["/Delete", "/TN", name, "/F"])
        if result.returncode:
            raise ValueError("could not remove login task: " + result.stderr.decode(errors="replace"))
        return {"status": "removed", "task_name": name}
    if apply:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.is_file():
            raise ValueError("pythonw.exe not found beside this Python; use the vault virtual environment")
        identity = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                                  capture_output=True, check=True, timeout=10, creationflags=flags)
        import csv
        user = next(csv.reader(identity.stdout.decode(errors="replace").splitlines()))[1]
        from paperflow.zotero.store import runtime_root
        xml_path = runtime_root(root) / "core-login-task.xml"
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_bytes(task_xml(root, pythonw, user, standalone=standalone))
        result = run(["/Create", "/TN", name, "/XML", str(xml_path), "/F"])
        if result.returncode:
            raise ValueError("could not register current-user login task: " + result.stderr.decode(errors="replace"))
    query = run(["/Query", "/TN", name, "/XML"])
    return {"status": "enabled" if query.returncode == 0 else "not-installed", "task_name": name,
            "windowless": True, "account": "current-user", "restart_on_failure": 3}
