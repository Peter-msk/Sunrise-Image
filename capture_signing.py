"""Capture-style Windows code signing: certreq/certutil/signtool, no PowerShell cmdlets.

Private keys never leave the Windows CurrentUser\\My store. No .venv, no persistent
policy changes, no TrustedRoot changes and no required timestamp service.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, locale, os, re, shutil, struct, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit

SUBJECT = 'CN=Sunrise Group'
CERT_FILE = 'SunriseGroup_SelfSigned_CodeSigning.cer'


def _find_program(name):
    path = shutil.which(name)
    if path:
        return Path(path)
    if name.lower() != 'signtool.exe':
        raise RuntimeError(f'Missing Windows system command: {name}')
    candidates = []
    for key in ('ProgramFiles(x86)', 'ProgramFiles'):
        base = os.environ.get(key)
        if base:
            root = Path(base) / 'Windows Kits' / '10' / 'bin'
            if root.is_dir():
                candidates.extend(root.glob('*/x64/signtool.exe'))
                candidates.extend(root.glob('*/signtool.exe'))
    if candidates:
        return sorted(candidates, reverse=True)[0]
    raise RuntimeError('Windows SDK signtool.exe unavailable. Install Windows SDK Signing Tools.')


def _prepare_utf8_log_streams():
    """Ensure the parent build's UTF-8 log remains writable on CP949 Windows.

    Redirected Python stdout commonly defaults to the local ANSI codepage.
    It must not fail when a native tool emits Unicode replacement characters
    or when the working folder contains Korean names. This affects this
    process's logs only; it does not change Windows console or system locale.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')


def _decode_native_output(raw: bytes) -> str:
    """Decode native Windows command output without inventing U+FFFD chars.

    `certreq`, `certutil` and `signtool` may emit ANSI/OEM output (CP949 on
    Korean Windows), whereas CI runners may emit UTF-8. The output bytes are
    not guaranteed to match Python's redirected stdout encoding.
    """
    if not raw:
        return ''
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16', errors='backslashreplace')
    encodings = ('utf-8-sig', locale.getencoding(), 'mbcs', 'cp949', 'cp437')
    for encoding in dict.fromkeys(encodings):
        try:
            return raw.decode(encoding, errors='strict')
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='backslashreplace')


def _run(argv, cwd):
    _prepare_utf8_log_streams()
    cmd = [str(x) for x in argv]
    print('[sign cmd] ' + subprocess.list2cmdline(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=100, check=False)
    out = _decode_native_output(r.stdout)
    if out:
        print(out.rstrip(), flush=True)
    if r.returncode:
        raise RuntimeError(f'Code-signing tool {Path(cmd[0]).name} failed with exit {r.returncode}')
    return out


def _registered_sha1_fingerprint(installation_output: str) -> str | None:
    """Extract SHA1 from THIS certutil -addstore call, with no locale-specific label.

    Windows certutil translates the words before ``(sha1)``. English reports
    ``Cert Hash(sha1):``; Korean reports ``인증서 해시(sha1):``. A single clear
    fingerprint tied to this registration is the only acceptable fallback.
    """
    candidates = []
    for line in installation_output.splitlines():
        match = re.fullmatch(
            r'(?i)\s*[^:\r\n]{0,100}?\(\s*sha\s*-?\s*1\s*\)\s*:\s*([0-9a-f]{40})\s*',
            line,
        )
        if match:
            candidates.append(match.group(1).upper())
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        raise RuntimeError('Conflicting SHA1 fingerprints in this new certificate registration')
    return unique[0] if unique else None


def _new_certificate_der(certificate: Path) -> bytes | None:
    """Read the new *X.509 certificate* bytes independently of Windows locale.

    Windows certreq -new with RequestType=Cert can label a real certificate
    ``-----BEGIN NEW CERTIFICATE REQUEST-----`` even though the decoded body
    is an X.509 certificate (as in the submitted Korean Windows failure).
    Never SHA1 the PEM text; the SignTool /sha1 value is SHA1 of the DER body.
    """
    raw = certificate.read_bytes()
    if raw[:1] == b'\x30' and len(raw) >= 128:
        return raw
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        try:
            text = raw.decode('utf-16')
        except UnicodeError:
            return None
    match = re.fullmatch(
        r'-----BEGIN (?P<label>CERTIFICATE|NEW CERTIFICATE REQUEST)-----\s+'
        r'(?P<body>[A-Za-z0-9+/=\s]+)-----END (?P=label)-----',
        text.strip(),
    )
    if not match:
        return None
    try:
        der = base64.b64decode(''.join(match.group('body').split()), validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return der if len(der) >= 128 and der[:1] == b'\x30' else None


def _fresh_certificate_thumbprint(certificate: Path, installation_output: str = '') -> str:
    """Use ONLY the newly issued certificate, never enumerate older certs.

    Prefer the SHA1 of its own DER X.509 data; cross-check the new certutil
    registration's (sha1) field when available, regardless of language.
    """
    registration_thumb = _registered_sha1_fingerprint(installation_output)
    der = _new_certificate_der(certificate)
    if der is not None:
        file_thumb = hashlib.sha1(der).hexdigest().upper()
        if registration_thumb and registration_thumb != file_thumb:
            raise RuntimeError('New certificate DER SHA1 disagrees with certutil registration')
        return file_thumb
    if registration_thumb:
        return registration_thumb
    raise RuntimeError(
        'Cannot determine SHA1 of newly issued certificate from DER/PEM or certutil '
        '(both English and localized SHA1 output supported); public prefix='
        + certificate.read_bytes()[:20].hex()
    )


def _create_certificate(certreq, certutil, audit, root):
    work=audit/'cert_provisioning';work.mkdir(parents=True,exist_ok=True)
    inf=work/'SunriseGroup_CodeSigning.inf'
    cert=work/CERT_FILE
    inf.write_text('\n'.join([
        '[Version]', 'Signature="$Windows NT$"', '', '[NewRequest]',
        f'Subject = "{SUBJECT}"',
        'KeySpec = 2', 'KeyLength = 3072', 'Exportable = FALSE',
        'MachineKeySet = FALSE', 'SMIME = FALSE',
        'PrivateKeyArchive = FALSE', 'UserProtected = FALSE',
        'UseExistingKeySet = FALSE',
        'ProviderName = "Microsoft Software Key Storage Provider"',
        'ProviderType = 0', 'RequestType = Cert', 'KeyUsage = 0x80',
        'HashAlgorithm = sha256', 'ValidityPeriod = Years',
        'ValidityPeriodUnits = 5', '', '[Extensions]',
        '2.5.29.37 = "{text}1.3.6.1.5.5.7.3.3"', ''
    ]),encoding='utf-8')
    cert.unlink(missing_ok=True)
    _run([certreq,'-q','-new',inf,cert],root)
    if not cert.is_file():
        raise RuntimeError('certreq did not produce a public certificate')
    installation_output = _run([certutil,'-user','-f','-addstore','My',cert],root)
    issued_thumbprint = _fresh_certificate_thumbprint(cert, installation_output)
    return cert, issued_thumbprint


def _pe_certificate_table(path):
    with path.open('rb') as f:
        f.seek(0,2);size=f.tell()
        if size<512:return False
        f.seek(0);hdr=f.read(64)
        if hdr[:2]!=b'MZ':return False
        pe=struct.unpack_from('<I',hdr,0x3c)[0]
        if pe+260>size:return False
        f.seek(pe);head=f.read(268)
        if head[:4]!=b'PE\0\0':return False
        magic=struct.unpack_from('<H',head,24)[0]
        offset=24+(112 if magic==0x20b else 96 if magic==0x10b else 0)
        if offset==24 or offset+8*5>len(head):return False
        pos,count=struct.unpack_from('<II',head,offset+8*4)
        return pos>0 and count>=8 and pos+count<=size


def _sha(path):
    h=hashlib.sha256()
    with path.open('rb') as s:
        for chunk in iter(lambda:s.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def sign(exe:Path, audit:Path, root:Path):
    if sys.platform != 'win32':
        raise RuntimeError('Actual Authenticode signing requires Windows')
    if not exe.is_file():
        raise RuntimeError('EXE missing for signing')
    certreq=_find_program('certreq.exe')
    certutil=_find_program('certutil.exe')
    signtool=_find_program('signtool.exe')
    # User policy: ALWAYS issue a new certificate on every signing invocation.
    # Do not enumerate, select, reuse, pin, remove or replace earlier keys.
    print('[sign] Creating a NEW Sunrise Group certificate for this build; existing certificates are not inspected.',flush=True)
    newcert, fresh_thumbprint = _create_certificate(certreq,certutil,audit,root)
    if not re.fullmatch(r'[0-9A-F]{40}',fresh_thumbprint):
        raise RuntimeError('New certificate has an invalid SHA1 thumbprint.')
    # Exact-fingerprint selection avoids ambiguity even when many certificates
    # have the same Subject CN=Sunrise Group.
    args=[signtool,'sign','/sha1',fresh_thumbprint,'/fd','SHA256','/v']
    timestamp=os.environ.get('SUNRISE_TIMESTAMP_URL','').strip()
    if timestamp:
        parsed=urlsplit(timestamp)
        if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:
            raise RuntimeError('Provided timestamp URL must be HTTPS without credentials')
        args+=['/tr',timestamp,'/td','SHA256']
    before=_sha(exe)
    _run([*args,exe],root)
    if not _pe_certificate_table(exe):
        raise RuntimeError('SignTool did not embed a valid PE certificate table')
    after=_sha(exe)
    if before==after:
        raise RuntimeError('Signing did not modify executable bytes')
    # The just-issued public certificate is the only certificate exported.
    # Private keys/PFX never leave CurrentUser\My and no old certs are changed.
    public=audit/CERT_FILE
    shutil.copy2(newcert, public)
    report={
      'signing_mode':'CAPTURE_STYLE_SELF_SIGNED_AUTHENTICODE',
      'signer_subject':SUBJECT,
      'signer_thumbprint':fresh_thumbprint,
      'eligible_signing_identity_pinned':False,
      'certificate_selection_policy':'ALWAYS_NEW_PER_SIGNING',
      'signature_type':'Authenticode',
      'windows_signature_status':'SignedCertificateTablePresent',
      'certificate_created':True,
      'timestamped':bool(timestamp),
      'public_trust_claimed':False,
      'verification_scope':'SignTool success + PE certificate table; not trusted root chain',
      'executable_sha256_after_signing':after,
      'exported_public_certificate':str(public) if public.is_file() else None
    }
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--executable',required=True)
    p.add_argument('--report',required=True)
    p.add_argument('--audit-dir',required=True)
    ns=p.parse_args()
    try:
        report=sign(Path(ns.executable).resolve(),Path(ns.audit_dir).resolve(),Path(__file__).resolve().parent)
        Path(ns.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('[sign] SUCCESS: Capture-style SignTool Authenticode. Trusted publisher NOT claimed.',flush=True)
        return 0
    except Exception as exc:
        print('[sign] FAILED:',str(exc),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':sys.exit(main())
