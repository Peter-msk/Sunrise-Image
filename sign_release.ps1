param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference = 'Stop'
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq 'CN=Sunrise Group' -and $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $cert) { throw 'Valid Sunrise Group code signing certificate is required on this build PC.' }
if (-not $env:SUNRISE_TIMESTAMP_URL -or $env:SUNRISE_TIMESTAMP_URL -notmatch '^https://') {
    throw 'Set SUNRISE_TIMESTAMP_URL to the approved HTTPS timestamp service.'
}
$result = Set-AuthenticodeSignature -FilePath $Executable -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $env:SUNRISE_TIMESTAMP_URL
$verified = Get-AuthenticodeSignature -LiteralPath $Executable
if (-not $verified.SignerCertificate -or $verified.SignerCertificate.Subject -ne 'CN=Sunrise Group' -or -not $verified.TimeStamperCertificate) {
    throw 'Sunrise Group signature or timestamp missing.'
}
# An existing self-signed group certificate may be untrusted on a build PC.
# Hash mismatch, invalid signatures, and every other state still fail closed.
if ($verified.Status -notin @('Valid', 'NotTrusted')) { throw ('Signature verification failed: ' + $verified.Status) }
Write-Output 'Sunrise Group signature and timestamp verified.'
