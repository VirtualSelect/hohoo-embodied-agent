"""Verify a checkout with LF/CRLF differences without altering frozen evidence."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[2]
evidence = pathlib.Path(sys.argv[1])
if not evidence.is_absolute():
    evidence = root / evidence
manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
audit = json.loads((evidence / "audit.json").read_text(encoding="utf-8"))

def original_bytes(file, expected):
    raw = file.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    for candidate in (raw, lf, lf.replace(b"\n", b"\r\n")):
        if hashlib.sha256(candidate).hexdigest() == expected:
            return candidate
    raise AssertionError("Hash mismatch: " + str(file))

with tempfile.TemporaryDirectory(prefix="hohoo-e5-audit-") as directory:
    temp = pathlib.Path(directory)
    # Audit imports no simulation dependency, and reads the original scene thresholds.
    for relative, digest in manifest["sourceSha256"].items():
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original_bytes(root / relative, digest))
    target_evidence = temp / "evidence" / "run"
    target_evidence.mkdir(parents=True)
    for name in ("manifest.json", "summary.json", "audit.json"):
        shutil.copyfile(evidence / name, target_evidence / name)
    for relative, digest in audit["rawFileSha256"].items():
        target = target_evidence / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original_bytes(evidence / relative, digest))
    subprocess.run([sys.executable, str(temp / "experiments/vl01_recovery_gate/audit.py"), str(target_evidence)], cwd=temp, check=True)
    print("Portable audit passed: only LF/CRLF restoration; source evidence unchanged.")
