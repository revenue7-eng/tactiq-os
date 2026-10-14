#!/usr/bin/env python3
"""
Altered and forged copies of a TactiQ OS release, for testing a checker.

A checker that has only ever been shown genuine files has only ever been agreed with.
This script takes ONE genuine, complete download of a release and builds a set of copies,
each wrong in one stated way: a bit changed, a file removed, a list rewritten, a whole
paper trail re-signed under keys made on the spot. Then it can run a checker over them
and say which copies the checker let through.

Written on 13 October 2026 from the attacks that broke our own two checkers that
day (https://ankr.in/tactiq-verification.html). Built for the layout of v2.1.0-rc14:
the evidence archive listed in the release SHA256SUMS, and the archive's own list signed.

  make   python3 tactiq-altered-sets.py make <genuine-release-dir> <out-dir>
  list   python3 tactiq-altered-sets.py list
  run    python3 tactiq-altered-sets.py run <out-dir> --kind l3|release
             [--reads tarball|unpacked] -- <checker command, {} for the set's directory>

  e.g.   ... run sets --kind l3 --reads tarball -- bash verify-l3-rc14.sh {}
         ... run sets --kind l3 --reads unpacked -- python3 verify-tactiq-l3.py {}
         ... run sets --kind release -- python3 verify-tactiq-release.py {}

  pack   python3 tactiq-altered-sets.py pack <sets-dir> <genuine-release-dir> <pack.tar.gz>
  unpack python3 tactiq-altered-sets.py unpack <pack.tar.gz> <genuine-release-dir> <out-dir>

THE SAME SETS, BYTE FOR BYTE. `make` signs its forged sets with keys it generates, so two
runs give two different forgeries. To hand somebody the very sets a result was obtained
on, `pack` writes only what differs from the genuine release: changed files once each,
a list of changed bytes for a large file that differs in a few, and the SHA-256 of every
file of every set. `unpack` rebuilds the sets from that pack and the recipient's own
genuine download, and refuses a set whose files do not all hash to the list. The pack
holds no private key: the keys are deleted when a forged set has been signed.

WHAT EACH SET IS. A directory holding the release files, the evidence archive, and the
same evidence unpacked under l3/. Unchanged files are hard links to your download, so a
set costs little disk; a changed file is always written new, never edited in place, and
your download is not touched. --kind says which checker a case is aimed at: an L3 checker
is not expected to notice a re-signed SHA256SUMS, and a release checker is not expected
to notice a missing quote. --reads says where the checker takes the evidence from: one
case differs only in the unpacked folder and means nothing to a checker that reads the
archive.

WHAT "PASSED" MEANS HERE. The checker is run once per set and only its exit status is
read. The copy named "genuine" must exit 0. Every other copy aimed at that kind of
checker must NOT exit 0. Why it failed is not judged: a set can be rejected by an outer
check before the inner one it was built for is reached, and this script cannot tell.
Read the checker's output for that.

WHAT THIS IS NOT. It is not a proof that a checker is sound; it is the list of ways ours
were not. A set that fails here says nothing about attacks nobody has thought of. The
forged sets are signed with keys generated in the output directory and worth nothing.

Exit: 0 genuine passed and no altered set got through · 1 an altered set got through, or
      genuine was rejected · 2 refused to start · 3 this script broke, which is no verdict
Needs: Python 3 (standard library), openssl 3, tar.
"""

import base64
import datetime as dt
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

# ── small tools ──────────────────────────────────────────────────────────────

def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def rewrite(path, data):
    """Write a file NEW. A set shares unchanged files with the download by hard link, so
    writing through the old name would change the download too."""
    if os.path.lexists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())


def flip(path, at=None):
    b = bytearray(open(path, "rb").read())
    b[len(b) // 2 if at is None else at] ^= 1
    rewrite(path, bytes(b))


def openssl(*args, **kw):
    r = subprocess.run(["openssl", *args], capture_output=True, **kw)
    if r.returncode != 0:
        raise RuntimeError("openssl " + " ".join(args[:3]) + ": " + r.stderr.decode(errors="replace")[-300:])
    return r.stdout


def sums_read(path):
    return [l.rstrip("\n") for l in open(path)]


def sums_set(path, directory, names, drop=()):
    """Rewrite the lines for `names` to the files' present hashes; remove lines in `drop`."""
    out = []
    for l in sums_read(path):
        parts = l.split(None, 1)
        n = parts[1].lstrip("*").strip() if len(parts) == 2 else None
        if n in drop:
            continue
        out.append(f"{sha256(os.path.join(directory, n))}  {n}" if n in names else l)
    rewrite(path, "\n".join(out) + "\n")


class Set:
    """One copy of the release being built."""

    def __init__(self, src, out, name):
        self.d = os.path.join(out, name)
        os.makedirs(self.d)
        for f in sorted(os.listdir(src)):
            p = os.path.join(src, f)
            if os.path.isfile(p):
                try:
                    os.link(p, os.path.join(self.d, f))
                except OSError:
                    shutil.copy2(p, os.path.join(self.d, f))
        tars = glob.glob(os.path.join(self.d, "l3-evidence-*.tar.gz"))
        if len(tars) != 1:
            raise RuntimeError("expected one l3-evidence-*.tar.gz in the release directory")
        self.tar = tars[0]
        self.ev_name = os.path.basename(self.tar)[:-len(".tar.gz")]
        self.e = os.path.join(self.d, "l3", self.ev_name)
        os.makedirs(self.e)
        with tarfile.open(self.tar, "r:gz") as tf:
            for m in tf.getmembers():           # plain files only, by base name
                if m.isfile():
                    rewrite(os.path.join(self.e, os.path.basename(m.name)), tf.extractfile(m).read())
        recs = sorted(glob.glob(os.path.join(self.e, "registration-*.json")))
        if len(recs) != 1:
            raise RuntimeError("expected one registration record in the evidence archive")
        self.rec = recs[0]
        quotes = sorted(f[:-len(".attest")] for f in os.listdir(self.e) if f.endswith(".attest"))
        if not quotes:
            raise RuntimeError("the genuine evidence archive holds no quote")
        self.quotes = quotes
        self.q = quotes[len(quotes) // 2]

    def ev(self, name):
        return os.path.join(self.e, name)

    def rel(self, name):
        return os.path.join(self.d, name)

    def list_fix(self, names=(), drop=()):
        """The archive's own (signed) list, rewritten to fit what was changed."""
        sums_set(self.ev("SHA256SUMS"), self.e, set(names), set(drop))

    def list_add(self, names):
        lines = sums_read(self.ev("SHA256SUMS")) + [f"{sha256(self.ev(n))}  {n}" for n in names]
        rewrite(self.ev("SHA256SUMS"), "\n".join(lines) + "\n")

    def repack(self, resum=True):
        """Pack the unpacked folder back into the archive, and, as someone who controls the
        release page but holds no key would, put the new hash in the release SHA256SUMS."""
        os.remove(self.tar)
        with tarfile.open(self.tar, "w:gz") as tf:
            tf.add(self.e, arcname=self.ev_name)
        if resum:
            sums_set(self.rel("SHA256SUMS"), self.d, {os.path.basename(self.tar)})

    def quote_files(self, q):
        return [f"{q}.{x}" for x in ("attest", "sig", "msg") if os.path.exists(self.ev(f"{q}.{x}"))]


# ── keys of our own making ───────────────────────────────────────────────────

EKU = {"reg": "2.25.205994972697553183157730487844756597568",
       "ev": "2.25.303991386130890852620485224389791976682",
       "rim": "2.25.1"}


def forged_hierarchy(k):
    """A root, a CA and three signers, all made here. Returns the directory."""
    os.makedirs(k, exist_ok=True)
    cnf = os.path.join(k, "x.cnf")
    rewrite(cnf, "[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n" +
            "".join(f"[{n}]\nextendedKeyUsage=critical,{o}\n" for n, o in EKU.items()))
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{k}/root.key",
            "-subj", "/O=TactiQ/CN=TactiQ Release Root CA", "-days", "3000", "-out", f"{k}/root.pem",
            "-addext", "basicConstraints=critical,CA:TRUE")
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{k}/ca.key",
            "-subj", "/O=TactiQ/CN=TactiQ Release Signing CA", "-out", f"{k}/ca.csr")
    openssl("x509", "-req", "-in", f"{k}/ca.csr", "-CA", f"{k}/root.pem", "-CAkey", f"{k}/root.key",
            "-CAcreateserial", "-days", "900", "-extfile", cnf, "-extensions", "ca", "-out", f"{k}/ca.pem")
    for n in EKU:
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{k}/{n}.key",
                "-subj", f"/O=TactiQ/CN=Forged {n} signer", "-out", f"{k}/{n}.csr")
        openssl("x509", "-req", "-in", f"{k}/{n}.csr", "-CA", f"{k}/ca.pem", "-CAkey", f"{k}/ca.key",
                "-CAcreateserial", "-days", "900", "-extfile", cnf, "-extensions", n, "-out", f"{k}/{n}.pem")
    return k


def cms_sign(k, who, path):
    openssl("cms", "-sign", "-binary", "-in", path, "-signer", f"{k}/{who}.pem", "-inkey", f"{k}/{who}.key",
            "-certfile", f"{k}/ca.pem", "-outform", "DER", "-md", "sha256", "-out", path + ".p7s.new")
    rewrite(path + ".p7s", open(path + ".p7s.new", "rb").read())
    os.remove(path + ".p7s.new")


def home_signed(s, keep_bundle):
    """One artefact altered, its line rewritten, and SHA256SUMS signed with a certificate
    made here and dated to cover the day of the genuine one."""
    victim = next(n for n in ("manifest-rock5a.txt", "tactiq-release-rock5a", "extlinux-rock5a.conf")
                  if os.path.exists(s.rel(n)))
    rewrite(s.rel(victim), open(s.rel(victim), "rb").read() + b"anything at all\n")
    sums_set(s.rel("SHA256SUMS"), s.d, {victim})
    nb = openssl("x509", "-in", s.rel("SHA256SUMS.workflow.pem"), "-noout", "-startdate").decode().split("=", 1)[1].strip()
    day = dt.datetime.strptime(nb, "%b %d %H:%M:%S %Y %Z")
    with tempfile.TemporaryDirectory() as t:
        openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", f"{t}/k.pem")
        open(f"{t}/index.txt", "w").close()
        rewrite(f"{t}/serial", "01\n")
        rewrite(f"{t}/c.cnf", f"[ca]\ndefault_ca=d\n[d]\ndatabase={t}/index.txt\nserial={t}/serial\n"
                              f"new_certs_dir={t}\ndefault_md=sha256\npolicy=p\n[p]\ncommonName=supplied\n")
        openssl("req", "-new", "-key", f"{t}/k.pem", "-subj", "/CN=nobody in particular", "-out", f"{t}/r.csr")
        openssl("ca", "-batch", "-config", f"{t}/c.cnf", "-selfsign", "-keyfile", f"{t}/k.pem", "-in", f"{t}/r.csr",
                "-startdate", day.strftime("%Y%m%d000000Z"),
                "-enddate", (day + dt.timedelta(days=1)).strftime("%Y%m%d235959Z"), "-out", f"{t}/out.pem")
        rewrite(s.rel("SHA256SUMS.workflow.pem"), openssl("x509", "-in", f"{t}/out.pem"))
        sig = openssl("dgst", "-sha256", "-sign", f"{t}/k.pem", s.rel("SHA256SUMS"))
        rewrite(s.rel("SHA256SUMS.workflow.sig"), base64.b64encode(sig))
    if not keep_bundle and os.path.exists(s.rel("SHA256SUMS.sigstore.json")):
        os.remove(s.rel("SHA256SUMS.sigstore.json"))


def bundle_edit(s, fn):
    p = s.rel("SHA256SUMS.sigstore.json")
    b = json.load(open(p))
    fn(b["verificationMaterial"]["tlogEntries"][0])
    rewrite(p, json.dumps(b))


def reference_edit(s, fn):
    p = s.rel("pcr-reference-rock5a.json")
    r = json.load(open(p))
    fn(r)
    rewrite(p, json.dumps(r, indent=2, sort_keys=True) + "\n")
    sums_set(s.rel("SHA256SUMS"), s.d, {"pcr-reference-rock5a.json"})


# ── the cases ────────────────────────────────────────────────────────────────
# (name, kinds, reads, what was done, builder). reads: "both", or "unpacked" for a case a
# checker that takes the evidence from the archive cannot see.

def c_genuine(s): pass

def c_quote_sig_bit(s): flip(s.ev(s.q + ".sig"), 20); s.repack()
def c_quote_attest_bit(s): flip(s.ev(s.q + ".attest")); s.repack()
def c_quote_msg_bit(s): flip(s.ev(s.q + ".msg")); s.repack()
def c_record_bit(s): flip(s.rec, 60); s.repack()
def c_rim_bit(s): flip(s.rel("rim-rock5a.json"), 900)
def c_ak_removed(s): os.remove(s.ev("ak.pub")); s.repack()
def c_quote_sig_removed(s): os.remove(s.ev(s.q + ".sig")); s.repack()

def c_quote_dropped(s):
    names = s.quote_files(s.q)
    for n in names: os.remove(s.ev(n))
    s.list_fix(drop=names); s.repack()

def c_no_quotes(s):
    names = [n for q in s.quotes for n in s.quote_files(q)]
    for n in names: os.remove(s.ev(n))
    s.list_fix(drop=names); s.repack()

def c_quote_replayed(s):
    new = "9" * len(s.q)
    for x in ("attest", "sig", "msg"):
        shutil.copyfile(s.ev(f"{s.q}.{x}"), s.ev(f"{new}.{x}"))
    s.list_add([f"{new}.{x}" for x in ("attest", "sig", "msg")]); s.repack()

def c_quote_replayed_unlisted(s):
    new = "9" * len(s.q)
    for x in ("attest", "sig", "msg"):
        shutil.copyfile(s.ev(f"{s.q}.{x}"), s.ev(f"{new}.{x}"))
    s.repack()                                  # the signed list is left exactly as it was

def c_file_planted(s): rewrite(s.ev("planted.txt"), "not listed anywhere\n"); s.repack()
def c_signed_list_removed(s): os.remove(s.ev("SHA256SUMS.p7s")); s.repack()
def c_archive_line_stripped(s): sums_set(s.rel("SHA256SUMS"), s.d, set(), {os.path.basename(s.tar)})

def c_starved(s):
    names = s.quote_files(s.q)
    for n in names: os.remove(s.ev(n))
    os.remove(s.ev("SHA256SUMS.p7s"))
    s.list_fix(drop=names); s.repack(resum=False)
    sums_set(s.rel("SHA256SUMS"), s.d, set(), {os.path.basename(s.tar)})

def c_second_record(s):
    extra = "registration-000.json"
    shutil.copyfile(s.rec, s.ev(extra)); shutil.copyfile(s.rec + ".p7s", s.ev(extra + ".p7s"))
    s.list_add([extra, extra + ".p7s"]); s.repack()

def c_root_swapped(s):
    with tempfile.TemporaryDirectory() as t:
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{t}/k", "-days", "30",
                "-subj", "/O=TactiQ/CN=TactiQ Release Root CA", "-out", f"{t}/r.pem")
        rewrite(s.rel("release-root-r2.pem"), open(f"{t}/r.pem", "rb").read())

def c_forged_paper_trail(s):
    k = forged_hierarchy(os.path.join(s.d, ".forged-keys"))
    rewrite(s.rel("release-root-r2.pem"), open(f"{k}/root.pem", "rb").read())
    rewrite(s.ev("signing-ca.pem"), open(f"{k}/ca.pem", "rb").read())
    rewrite(s.ev("reg-signer.pem"), open(f"{k}/reg.pem", "rb").read())
    r = json.load(open(s.rec)); r["device_id"] = "SOME-OTHER-DEVICE"; r["registrar"] = "nobody"
    rewrite(s.rec, json.dumps(r, indent=1)); cms_sign(k, "reg", s.rec)
    spki = hashlib.sha256(openssl("pkey", "-pubin", "-outform", "DER",
                                  input=openssl("x509", "-in", f"{k}/root.pem", "-pubkey", "-noout"))).hexdigest()
    rim = json.load(open(s.rel("rim-rock5a.json"))); rim["keys"]["release_root"]["spki_sha256"] = spki
    rewrite(s.rel("rim-rock5a.json"), json.dumps(rim, indent=1)); cms_sign(k, "rim", s.rel("rim-rock5a.json"))
    present = sorted(f for f in os.listdir(s.e) if f not in ("SHA256SUMS", "SHA256SUMS.p7s"))
    rewrite(s.ev("SHA256SUMS"), "".join(f"{sha256(s.ev(n))}  {n}\n" for n in present))
    cms_sign(k, "ev", s.ev("SHA256SUMS"))
    s.repack()
    sums_set(s.rel("SHA256SUMS"), s.d, {"rim-rock5a.json", "rim-rock5a.json.p7s"})
    shutil.rmtree(k)

def c_unpacked_differs(s):
    names = s.quote_files(s.q)
    for n in names: os.remove(s.ev(n))
    s.list_fix(drop=names)                      # the archive itself is left genuine

def c_home_signed(s): home_signed(s, keep_bundle=True)
def c_home_signed_no_bundle(s): home_signed(s, keep_bundle=False)
def c_bundle_removed(s): os.remove(s.rel("SHA256SUMS.sigstore.json"))
def c_entry_time_moved(s): bundle_edit(s, lambda e: e.__setitem__("integratedTime", str(int(e["integratedTime"]) + 60)))

def c_checkpoint_altered(s):
    def f(e):
        c = e["inclusionProof"]["checkpoint"]; lines = c["envelope"].split("\n")
        lines[1] = str(int(lines[1]) + 1); c["envelope"] = "\n".join(lines)
    bundle_edit(s, f)

def c_artefact_bit(s): flip(s.rel("fitImage-rock5a"))
def c_reference_pcr(s): reference_edit(s, lambda r: r["pcr"]["1"].__setitem__("B", r["pcr"]["1"]["A"]))
def c_reference_cmdline(s):
    reference_edit(s, lambda r: r["components"]["slots"]["B"].__setitem__(
        "cmdline", r["components"]["slots"]["B"]["cmdline"] + " init=/bin/sh"))

def c_fit_cmdline(s):
    b = bytearray(open(s.rel("fitImage-rock5a"), "rb").read())
    i = b.rfind(b"rauc.slot=B")
    if i < 0:
        raise RuntimeError("no slot B command line found in the FIT image")
    b[i + 10] = ord("A")
    rewrite(s.rel("fitImage-rock5a"), bytes(b))
    sums_set(s.rel("SHA256SUMS"), s.d, {"fitImage-rock5a"})
    reference_edit(s, lambda r: r["inputs"].__setitem__("fitImage-rock5a", sha256(s.rel("fitImage-rock5a"))))

def c_reference_unknown_format(s): reference_edit(s, lambda r: r.__setitem__("format", "tactiq-pcr-reference/9"))

CASES = [
    ("genuine", {"l3", "release"}, "both", "nothing changed: the control, which must pass", c_genuine),
    ("quote-sig-bit", {"l3"}, "both", "one bit changed in one quote's signature", c_quote_sig_bit),
    ("quote-attest-bit", {"l3"}, "both", "one bit changed in one quote's attested structure", c_quote_attest_bit),
    ("quote-msg-bit", {"l3"}, "both", "one bit changed in one quote's message", c_quote_msg_bit),
    ("record-bit", {"l3"}, "both", "one bit changed in the registration record", c_record_bit),
    ("rim-bit", {"l3"}, "both", "one bit changed in the signed reference (RIM)", c_rim_bit),
    ("ak-removed", {"l3"}, "both", "the attestation key removed from the archive", c_ak_removed),
    ("quote-sig-removed", {"l3"}, "both", "one quote's signature file removed", c_quote_sig_removed),
    ("quote-dropped", {"l3"}, "both", "one quote removed together with its lines in the archive's list", c_quote_dropped),
    ("no-quotes", {"l3"}, "both", "every quote removed together with its lines", c_no_quotes),
    ("quote-replayed", {"l3"}, "both", "one quote copied under a new number, the list extended", c_quote_replayed),
    ("quote-replayed-unlisted", {"l3"}, "both", "one quote copied under a new number and NOT added to the list, whose signature therefore still verifies", c_quote_replayed_unlisted),
    ("file-planted", {"l3"}, "both", "a file added to the archive that no list names", c_file_planted),
    ("second-record", {"l3"}, "both", "a second registration record added, sorting before the first", c_second_record),
    ("signed-list-removed", {"l3"}, "both", "the signature over the archive's list removed", c_signed_list_removed),
    ("archive-line-stripped", {"l3"}, "both", "the archive's line taken out of the release SHA256SUMS", c_archive_line_stripped),
    ("starved", {"l3"}, "both", "a quote and its lines removed, the list's signature removed, the archive's line stripped: nothing left for a new check to look at", c_starved),
    ("root-swapped", {"l3"}, "both", "the release root replaced by a self-signed one of the same name", c_root_swapped),
    ("forged-paper-trail", {"l3"}, "both", "own root, CA and signers; record altered and re-signed; RIM re-signed to name the new root; archive list re-signed; release sums rewritten", c_forged_paper_trail),
    ("unpacked-differs", {"l3"}, "unpacked", "the archive left genuine, a quote removed from the unpacked folder only", c_unpacked_differs),
    ("home-signed", {"release"}, "both", "an artefact altered, its line rewritten, SHA256SUMS signed with a certificate made here; the genuine log bundle left in place", c_home_signed),
    ("home-signed-no-bundle", {"release"}, "both", "the same, with the log bundle removed", c_home_signed_no_bundle),
    ("bundle-removed", {"release"}, "both", "the log bundle removed from an otherwise genuine release", c_bundle_removed),
    ("entry-time-moved", {"release"}, "both", "the log entry's time moved by 60 seconds", c_entry_time_moved),
    ("checkpoint-altered", {"release"}, "both", "the log checkpoint's tree size changed by one", c_checkpoint_altered),
    ("artefact-bit", {"release"}, "both", "one bit changed in the kernel FIT image", c_artefact_bit),
    ("reference-pcr", {"release"}, "both", "slot B's PCR 1 in the reference replaced by slot A's, sums rewritten", c_reference_pcr),
    ("reference-cmdline", {"release"}, "both", "init=/bin/sh appended to slot B's command line in the reference, sums rewritten", c_reference_cmdline),
    ("fit-cmdline", {"release"}, "both", "slot B's command line changed inside the FIT image; sums and the reference's input hash rewritten", c_fit_cmdline),
    ("reference-unknown-format", {"release"}, "both", "the reference given a format name no checker knows, sums rewritten", c_reference_unknown_format),
]


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_list():
    for name, kinds, reads, what, _ in CASES:
        print(f"  {name:26s} {'+'.join(sorted(kinds)):11s} {what}" + ("  [seen only in the unpacked folder]" if reads == "unpacked" else ""))
    return 0


def cmd_make(src, out):
    if not os.path.isfile(os.path.join(src, "SHA256SUMS")):
        print(f"{src} does not look like a release directory (no SHA256SUMS)", file=sys.stderr)
        return 2
    if os.path.exists(out) and os.listdir(out):
        print(f"{out} exists and is not empty; give a new directory", file=sys.stderr)
        return 2
    # the download must itself be whole, or every set inherits a fault nobody put there
    for l in sums_read(os.path.join(src, "SHA256SUMS")):
        want, n = l.split(None, 1)
        p = os.path.join(src, n.strip())
        if not os.path.exists(p) or sha256(p) != want:
            print(f"the download is not complete or not genuine: {n.strip()}", file=sys.stderr)
            return 2
    os.makedirs(out, exist_ok=True)
    manifest = []
    for name, kinds, reads, what, build in CASES:
        s = Set(src, out, name)
        build(s)
        manifest.append({"set": name, "aimed_at": sorted(kinds), "seen_in": reads, "what": what,
                         "must": "pass (exit 0)" if name == "genuine" else "not exit 0"})
        print(f"  built {name}")
    rewrite(os.path.join(out, "MANIFEST.json"), json.dumps(manifest, indent=1) + "\n")
    print(f"\n  {len(manifest)} sets in {out}; MANIFEST.json says what each is and what it must do\n")
    return 0


def cmd_run(out, kind, reads, command):
    mp = os.path.join(out, "MANIFEST.json")
    if not os.path.exists(mp):
        print(f"no MANIFEST.json in {out}; run make first", file=sys.stderr)
        return 2
    if not any("{}" in c for c in command):
        print("the checker command needs {} where the set's directory goes", file=sys.stderr)
        return 2
    through, rejected, genuine_ok = [], 0, None
    for m in json.load(open(mp)):
        if kind not in m["aimed_at"]:
            continue
        if m["seen_in"] == "unpacked" and reads == "tarball":
            print(f"  --    {m['set']:26s} not run: it differs only in the unpacked folder")
            continue
        d = os.path.join(out, m["set"])
        r = subprocess.run([c.replace("{}", d) for c in command], capture_output=True)
        if m["set"] == "genuine":
            genuine_ok = r.returncode == 0
            print(f"  {'ok  ' if genuine_ok else 'FAIL'}  {m['set']:26s} exit {r.returncode}  (the control: must be 0)")
        elif r.returncode == 0:
            through.append(m["set"])
            print(f"  HOLE  {m['set']:26s} exit 0  — {m['what']}")
        else:
            rejected += 1
            print(f"  ok    {m['set']:26s} exit {r.returncode}")
    print()
    if genuine_ok is not True:
        print("  The genuine copy was NOT accepted, so nothing above is a verdict on the altered ones:")
        print("  a checker that rejects everything rejects them too.\n")
        return 1
    print(f"  genuine accepted; {rejected} altered set(s) rejected; {len(through)} got through"
          + (": " + ", ".join(through) if through else "") + "\n")
    return 1 if through else 0


def _tree(d):
    """relative path -> sha256, for every file of one set."""
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, d)] = sha256(p)
    return out


def cmd_pack(sets, src, dest):
    mp = os.path.join(sets, "MANIFEST.json")
    if not os.path.exists(mp) or not os.path.isfile(os.path.join(src, "SHA256SUMS")):
        print("need a sets directory made by `make` and the genuine release directory", file=sys.stderr)
        return 2
    genuine = {f: sha256(os.path.join(src, f)) for f in os.listdir(src) if os.path.isfile(os.path.join(src, f))}
    index = {"format": "tactiq-altered-sets-pack/1", "manifest": json.load(open(mp)),
             "genuine": genuine, "sets": {}, "patches": {}}
    blobs = {}
    for m in index["manifest"]:
        d = os.path.join(sets, m["set"])
        tree = _tree(d)
        index["sets"][m["set"]] = tree
        for rel, h in tree.items():
            if genuine.get(rel) == h or h in blobs or h in index["patches"]:
                continue
            p = os.path.join(d, rel)
            # a large file that differs from its genuine namesake in a few bytes travels
            # as those bytes, not as another copy of the vendor's image
            if rel in genuine and os.path.getsize(p) > 4 << 20 and os.path.getsize(p) == os.path.getsize(os.path.join(src, rel)):
                a, b = open(os.path.join(src, rel), "rb").read(), open(p, "rb").read()
                diff = [[i, b[i]] for i in range(len(a)) if a[i] != b[i]] if a != b else []
                if len(diff) <= 4096:
                    index["patches"][h] = {"of": rel, "bytes": diff}
                    continue
            blobs[h] = p
    with tarfile.open(dest, "w:gz") as tf:
        with tempfile.TemporaryDirectory() as t:
            ip = os.path.join(t, "index.json")
            rewrite(ip, json.dumps(index, indent=1) + "\n")
            tf.add(ip, arcname="index.json")
        for h, p in sorted(blobs.items()):
            tf.add(p, arcname="blobs/" + h)
    print(f"\n  {len(index['sets'])} sets packed into {dest}: {len(blobs)} changed file(s), "
          f"{len(index['patches'])} byte patch(es), {os.path.getsize(dest)} bytes\n")
    return 0


def cmd_unpack(pack, src, out):
    if os.path.exists(out) and os.listdir(out):
        print(f"{out} exists and is not empty; give a new directory", file=sys.stderr)
        return 2
    with tarfile.open(pack, "r:gz") as tf:
        index = json.load(tf.extractfile("index.json"))
        if index.get("format") != "tactiq-altered-sets-pack/1":
            print("not a pack this script knows", file=sys.stderr)
            return 2
        # the recipient's download must be the release the pack was made from
        for f, h in index["genuine"].items():
            p = os.path.join(src, f)
            if not os.path.exists(p) or sha256(p) != h:
                print(f"your download is not the release this pack was made from: {f}", file=sys.stderr)
                return 2
        blobs = {}
        for m in tf.getmembers():
            if m.isfile() and m.name.startswith("blobs/"):
                data = tf.extractfile(m).read()
                if hashlib.sha256(data).hexdigest() != os.path.basename(m.name):
                    print(f"the pack is damaged: {m.name}", file=sys.stderr)
                    return 2
                blobs[os.path.basename(m.name)] = data
    os.makedirs(out, exist_ok=True)
    for name, tree in index["sets"].items():
        if os.path.basename(name) != name or name.startswith("."):
            print(f"refusing a set named {name!r}", file=sys.stderr)
            return 2
        d = os.path.join(out, name)
        for rel, h in tree.items():
            p = os.path.normpath(os.path.join(d, rel))
            if not p.startswith(d + os.sep):
                print(f"refusing a path that leaves the set: {rel!r}", file=sys.stderr)
                return 2
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if index["genuine"].get(rel) == h:
                try:
                    os.link(os.path.join(src, rel), p)
                except OSError:
                    shutil.copy2(os.path.join(src, rel), p)
            elif h in blobs:
                rewrite(p, blobs[h])
            elif h in index["patches"]:
                pt = index["patches"][h]
                b = bytearray(open(os.path.join(src, pt["of"]), "rb").read())
                for i, v in pt["bytes"]:
                    b[i] = v
                rewrite(p, bytes(b))
            else:
                print(f"the pack does not hold {name}/{rel}", file=sys.stderr)
                return 2
        if _tree(d) != tree:
            print(f"set {name} did NOT rebuild to the files the pack lists", file=sys.stderr)
            return 1
        print(f"  rebuilt {name}: {len(tree)} files, every one hashes to the pack's list")
    rewrite(os.path.join(out, "MANIFEST.json"), json.dumps(index["manifest"], indent=1) + "\n")
    print(f"\n  {len(index['sets'])} sets in {out}, byte for byte the sets that were packed\n")
    return 0


def main(a):
    if len(a) >= 1 and a[0] == "list":
        return cmd_list()
    if len(a) == 4 and a[0] == "pack":
        return cmd_pack(a[1], a[2], a[3])
    if len(a) == 4 and a[0] == "unpack":
        return cmd_unpack(a[1], a[2], a[3])
    if len(a) == 3 and a[0] == "make":
        return cmd_make(a[1], a[2])
    if len(a) >= 2 and a[0] == "run" and "--" in a:
        i = a.index("--")
        opts, command = a[2:i], a[i + 1:]
        kind = opts[opts.index("--kind") + 1] if "--kind" in opts and opts.index("--kind") + 1 < len(opts) else None
        reads = opts[opts.index("--reads") + 1] if "--reads" in opts and opts.index("--reads") + 1 < len(opts) else "unpacked"
        if kind in ("l3", "release") and reads in ("tarball", "unpacked") and command:
            return cmd_run(a[1], kind, reads, command)
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except BaseException as e:
        print(f"\n  THIS SCRIPT BROKE: {type(e).__name__}: {e}\n  That is not a verdict on any checker.", file=sys.stderr)
        sys.exit(3)
