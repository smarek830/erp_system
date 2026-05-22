param(
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [switch]$UseHead,
    [int]$TimeoutSec = 8
)

$ErrorActionPreference = 'Stop'

function Test-Endpoint {
    param(
        [string]$Path,
        [int[]]$ExpectedStatusCodes
    )

    $url = "$BaseUrl$Path"
    $methodArgs = if ($UseHead) { '-I' } else { '' }

    $statusRaw = & curl.exe -s -o NUL -w "%{http_code}" --connect-timeout $TimeoutSec $methodArgs $url
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($statusRaw)) {
        Write-Host "FAIL $Path -> curl exit code $LASTEXITCODE"
        return $false
    }

    $statusCode = 0
    if (-not [int]::TryParse(($statusRaw.Trim()), [ref]$statusCode)) {
        Write-Host "FAIL $Path -> invalid HTTP status '$statusRaw'"
        return $false
    }

    if ($ExpectedStatusCodes -contains $statusCode) {
        Write-Host "OK   $Path -> $statusCode"
        return $true
    }

    Write-Host "FAIL $Path -> $statusCode (expected: $($ExpectedStatusCodes -join ','))"
    return $false
}

$allOk = $true

$allOk = (Test-Endpoint -Path '/healthz/' -ExpectedStatusCodes @(200)) -and $allOk
$allOk = (Test-Endpoint -Path '/admin/' -ExpectedStatusCodes @(200, 302)) -and $allOk
$allOk = (Test-Endpoint -Path '/objednavka/import/mrp-pdf/' -ExpectedStatusCodes @(200, 302)) -and $allOk

if ($allOk) {
    Write-Host 'ERP endpoint check PASSED.'
    exit 0
}

Write-Host 'ERP endpoint check FAILED.'
exit 1
