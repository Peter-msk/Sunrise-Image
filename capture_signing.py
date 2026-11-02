"""Capture-style Windows code signing: certreq/certutil/signtool, no PowerShell cmdlets.

Private keys never leave the Windows CurrentUser\\My store. No .venv, no persistent
policy changes, no TrustedRoot changes and no required timestamp service.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys
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


def _run(argv, cwd):
    cmd = [str(x) for x in argv]
    print('[sign cmd] ' + subprocess.list2cmdline(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=100, check=False)
    out = r.stdout.decode('utf-8', errors='replace')
    if out:
        print(out.rstrip(), flush=True)
    if r.returncode:
        raise RuntimeError(f'Code-signing tool {Path(cmd[0]).name} failed with exit {r.returncode}')
    return out


def _thumbprints(text):
    """Only parse hash-labelled line data; never include the label's sha1 digits."""
    values=[]
    for line in text.splitlines():
        label=line.lower()
        if not ('sha1' in label or 'hash' in label):
            continue
        payload=line.rsplit(':',1)[-1]
        found=re.search(r'(?<![0-9a-fA-F])([0-9a-fA-F]{40})(?![0-9a-fA-F])',payload)
        if found:
            values.append(found.group(1).upper())
            continue
        compact=re.sub(r'[^0-9a-fA-F]', '',payload)
        if len(compact)==40:
            values.append(compact.upper())
    return list(dict.fromkeys(values))


def _find_cert(certutil, root):
    # Capture uses the subject-filtered CurrentUser/My certutil store, not root trust.
    # Missing cert is normal on first run; certutil may exit nonzero for empty store.
    proc=subprocess.run([str(certutil),'-user','-store','My',SUBJECT],cwd=root,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,check=False)
    content=proc.stdout.decode('utf-8',errors='replace')
    values=_thumbprints(content)
    if len(values)>1:
        raise RuntimeError('More than one Sunrise Group certificate; select/reconcile without silently replacing an existing key.')
    return values[0] if values else ''


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
    _run([certutil,'-user','-f','-addstore','My',cert],root)
    return cert


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
    existing=_find_cert(certutil,root)
    created=False
    newcert=None
    if not existing:
        print('[sign] Existing Sunrise Group certificate missing; provisioning once.',flush=True)
        newcert=_create_certificate(certreq,certutil,audit,root)
        existing=_find_cert(certutil,root)
        created=True
    if not re.fullmatch('[0-9A-F]{40}',existing):
        raise RuntimeError('Cannot identify Sunrise Group signing certificate SHA1 thumbprint.')
    args=[signtool,'sign','/sha1',existing,'/fd','SHA256','/v']
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
    public=audit/CERT_FILE
    if newcert and newcert.is_file():
        shutil.copy2(newcert,public)
    else:
        try:
            _run([certutil,'-user','-store','My',existing,public],root)
        except RuntimeError:
            # Public .cer is supplementary; a reused cert may not support old certutil export syntax.
            public.unlink(missing_ok=True)
    report={
      'signing_mode':'CAPTURE_STYLE_SELF_SIGNED_AUTHENTICODE',
      'signer_subject':SUBJECT,
      'signer_thumbprint':existing,
      'signature_type':'Authenticode',
      'windows_signature_status':'SignedCertificateTablePresent',
      'certificate_created':created,
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
