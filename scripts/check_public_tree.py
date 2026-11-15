#!/usr/bin/env python3
"""Check source and optional distribution archives without printing matched values."""
import argparse
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "build", "dist", ".pytest_cache"}
PRIVATE_FILES = {"config.json", "credentials.json", "credentials.env", "secrets.json",
                 "smtp_password", "password", ".env", ".DS_Store"}
PRIVATE_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".eml", ".log", ".pem", ".key", ".p12", ".pfx")
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+")
UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
TOKEN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def inspect(name, raw):
    path = Path(name)
    failures=[]
    if path.name in PRIVATE_FILES or path.name.startswith('.env.') or path.name.endswith(PRIVATE_SUFFIXES):
        failures.append("private/runtime file")
    if ".sqlite" in path.name or ".db-" in path.name:
        failures.append("database sidecar")
    text=raw.decode("utf-8",errors="ignore")
    for label,pattern in (("personal absolute home path",HOME_PATH),
                          ("literal session UUID",UUID),("credential-like value",TOKEN)):
        if pattern.search(text):failures.append(label)
    for match in EMAIL.finditer(text):
        domain=match[1].lower()
        if not (domain in {"example.com","example.net","example.org","example.test"}
                or domain.endswith((".example.com",".example.net",".example.org",".test",".invalid",".localhost"))):
            failures.append("non-example email address")
            break
    return [f"{name}: {reason}" for reason in dict.fromkeys(failures)]


def check(root, archives=False):
    failures=[]
    checked=0
    candidates=set()
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if any(part in SKIP_DIRS or part.endswith('.egg-info') for part in relative.parts):continue
        if path.is_symlink():
            failures.append(str(relative)+": symlink in public tree")
        elif path.is_file():candidates.add(path)
    if (root/'.git').is_dir():
        result=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True)
        for item in result.stdout.split(b'\0'):
            if item:
                path=root/item.decode()
                if path.is_file():candidates.add(path)
    for path in sorted(candidates):
        failures.extend(inspect(str(path.relative_to(root)),path.read_bytes()))
        checked+=1
    if archives:
        files=sorted((root/'dist').glob('*'))
        if not files:failures.append("dist: no distribution archives to inspect")
        for path in files:
            if path.suffix=='.whl':
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if not name.endswith('/'):
                            failures.extend(inspect(path.name+'!'+name,archive.read(name)))
                            checked+=1
            elif path.name.endswith('.tar.gz'):
                with tarfile.open(path,'r:gz') as archive:
                    for member in archive.getmembers():
                        if member.issym() or member.islnk():
                            failures.append(path.name+'!'+member.name+": symlink in source archive")
                        elif member.isfile():
                            stream=archive.extractfile(member)
                            failures.extend(inspect(path.name+'!'+member.name,stream.read()))
                            checked+=1
    return checked,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',action='store_true')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    checked,failures=check(args.root.resolve(),args.archives)
    for item in failures:print(item)
    print(f"Checked {checked} files/archive entries; findings: {len(failures)}")
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
