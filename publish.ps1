# رفع "رادار بايثون" على GitHub وتفعيل GitHub Pages.
# التشغيل:   powershell -ExecutionPolicy Bypass -File publish.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")

$repo = "py-radar"

# 1) تسجيل الدخول (يفتح المتصفح ويطلب رمزاً من مرة واحدة فقط)
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n>> تسجيل الدخول إلى GitHub..." -ForegroundColor Cyan
    gh auth login --hostname github.com --git-protocol https --web --scopes "repo,workflow"
    if ($LASTEXITCODE -ne 0) { throw "فشل تسجيل الدخول." }
}

$owner = (gh api user --jq .login)
Write-Host ">> الحساب: $owner" -ForegroundColor Green

# 2) إنشاء المستودع ورفع الملفات
gh repo view "$owner/$repo" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ">> إنشاء المستودع ورفع الملفات..." -ForegroundColor Cyan
    gh repo create $repo --public --source . --remote origin --push `
        --description "محتوى برمجة بايثون بالعربي والإنجليزي، محدّث يومياً"
} else {
    Write-Host ">> المستودع موجود — رفع آخر التغييرات..." -ForegroundColor Cyan
    git remote get-url origin 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { git remote add origin "https://github.com/$owner/$repo.git" }
    git push -u origin main
}

# 3) تفعيل GitHub Pages
Write-Host ">> تفعيل GitHub Pages..." -ForegroundColor Cyan
try {
    gh api -X POST "repos/$owner/$repo/pages" -f "source[branch]=main" -f "source[path]=/" | Out-Null
} catch {
    gh api -X PUT "repos/$owner/$repo/pages" -f "source[branch]=main" -f "source[path]=/" | Out-Null
}

$url = "https://$owner.github.io/$repo/"
Write-Host "`n===========================================" -ForegroundColor Green
Write-Host " تم الرفع بنجاح"                              -ForegroundColor Green
Write-Host " المستودع : https://github.com/$owner/$repo"
Write-Host " التطبيق  : $url"
Write-Host " (قد يستغرق النشر دقيقة أو دقيقتين أول مرة)"
Write-Host "===========================================`n" -ForegroundColor Green
