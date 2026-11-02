# Sunrise Group build-PC Authenticode signer. No persistent policy changes.
# Capture-style: reuse CurrentUser\My certificate, auto-provision once if missing.
param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
$subject = 'CN=Sunrise Group'
$store = 'Cert:\CurrentUser\My'
$now = Get-Date
function Get-UsableGroupCertificate {
    Get-ChildItem -Path $store -CodeSigningCert | Where-Object {
        $_.Subject -eq $subject -and $_.HasPrivateKey -and $_.NotAfter -gt $now -and
        
        
        $_.NotBefore -le $now -and $_.PublicKey.Oid.Value -eq '1.2.840.113549.1.1.1' -and
        ([System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($_).KeySize -ge 3072)
    } | Sort-Object NotAfter -Descending | Select-Object -First 1
}
$certificate = Get-UsableGroupCertificate
$created = $false
if (-not $certificate) {
    Write-Output '[SIGN] Creating first-use, non-exportable Sunrise Group self-signed code-signing certificate.'
    $certificate = New-SelfSignedCertificate -Subject $subject -Type CodeSigningCert `
        -CertStoreLocation $store -KeyAlgorithm RSA -KeyLength 3072 `
        -KeyExportPolicy NonExportable -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(5)
    if (-not $certificate -or -not $certificate.HasPrivateKey) {
        throw 'Self-signed code signing certificate creation failed.'
    }
    $created = $true
} else {
    Write-Output '[SIGN] Reusing existing valid Sunrise Group signing certificate.'
}
$thumb = $certificate.Thumbprint.ToUpperInvariant()
$beforeHash = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
if ($env:SUNRISE_TIMESTAMP_URL) {
    $uri = $null
    if (-not [Uri]::TryCreate($env:SUNRISE_TIMESTAMP_URL, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo) {
        throw 'SUNRISE_TIMESTAMP_URL was provided but is not a valid HTTPS URL.'
    }
    $result = Set-AuthenticodeSignature -LiteralPath $Executable -Certificate $certificate `
        -HashAlgorithm SHA256 -TimestampServer $uri.AbsoluteUri
} else {
    $result = Set-AuthenticodeSignature -LiteralPath $Executable -Certificate $certificate `
        -HashAlgorithm SHA256
}
$signature = Get-AuthenticodeSignature -LiteralPath $Executable
if (-not $signature.SignerCertificate -or
    $signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $thumb -or
    $signature.SignatureType.ToString() -ne 'Authenticode') {
    throw 'Authenticode signer or signature type mismatch.'
}
# A self-signed certificate is not a publicly trusted publisher. Windows may report
# NotTrusted/UnknownError on computers where its root is not in the trust store.
# Reject altered/corrupt/hash-mismatch outcomes; do not silently claim trust.
$status = $signature.Status.ToString()
if ($status -notin @('Valid','NotTrusted','UnknownError')) {
    throw ('Rejected Authenticode verification status: ' + $status)
}
if ($env:SUNRISE_TIMESTAMP_URL -and -not $signature.TimeStamperCertificate) {
    throw 'Timestamp was requested but the signed executable has no timestamp.'
}
$afterHash = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
if ($beforeHash -eq $afterHash) {
    throw 'Signing did not alter the executable bytes; signature may not be embedded.'
}
# Public certificate only; NEVER export private key, PFX or install in Trusted Root.
$pub = Join-Path (Split-Path -Parent $ReportPath) 'SunriseGroup_SelfSigned_CodeSigning.cer'
Export-Certificate -Cert $certificate -FilePath $pub -Force | Out-Null
$selfSigned = ($certificate.Subject -eq $certificate.Issuer)
$report = [ordered]@{
    signing_mode = 'CAPTURE_STYLE_SELF_SIGNED_AUTHENTICODE'
    issuer_subject = $certificate.Issuer
    signer_subject = $signature.SignerCertificate.Subject
    signer_thumbprint = $thumb
    created_certificate = $created
    signature_type = $signature.SignatureType.ToString()
    windows_signature_status = $status
    certificate_self_signed = $selfSigned
    public_trust_claimed = $false
    timestamped = [bool]$signature.TimeStamperCertificate
    executable_sha256_after_signing = $afterHash
    exported_public_certificate = $pub
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Output ('[SIGN] Embedded Authenticode signature; status=' + $status + '; thumbprint=' + $thumb)
Write-Output '[SIGN] Local certificate signature does not establish public trust; SHA256 computed after signing.'
