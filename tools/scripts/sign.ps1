# Sign release binaries with the Certum "Standard Code Signing in the Cloud" certificate (SimplySign).
# Before running: open SimplySign Desktop and unlock it with the code from the SimplySign phone app, so the
# certificate shows up in the Windows "Personal" store. Then:
#   powershell -File tools\scripts\sign.ps1 build\sse3\DragonlandsGP.asi [more files...]
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files)

$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName | Select-Object -Last 1
if (-not $signtool) { throw "signtool.exe not found (Windows SDK)" }

# the Certum code-signing certificate: issued by Certum, valid now, with a private key, for code signing
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Issuer -match 'Certum' -and $_.NotAfter -gt (Get-Date) -and $_.HasPrivateKey } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $cert) { throw "No unlocked Certum code-signing certificate found. Open SimplySign Desktop and log in first." }
Write-Host "Signing with: $($cert.Subject) (valid until $($cert.NotAfter.ToString('yyyy-MM-dd')))"

foreach ($f in $Files) {
    & $signtool.FullName sign /sha1 $cert.Thumbprint /fd sha256 /tr http://time.certum.pl /td sha256 /d "Dragon-lands Grand Prix" $f
    if ($LASTEXITCODE -ne 0) { throw "signing failed: $f" }
    $sig = Get-AuthenticodeSignature $f
    Write-Host ("{0}: {1} ({2})" -f $f, $sig.Status, $sig.SignerCertificate.Subject)
}
