<#
.SYNOPSIS
Auto-sync local library to GitHub Pages
#>

Write-Host "Starting sync process..." -ForegroundColor Cyan

# 1. Check for changes
$gitStatus = git status --porcelain
if ([string]::IsNullOrWhiteSpace($gitStatus)) {
    Write-Host "No changes detected. Sync skipped." -ForegroundColor Yellow
    exit
}

# 2. Stage files
Write-Host "Staging files..." -ForegroundColor Cyan
git add .

# 3. Commit
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$commitMsg = "auto-sync: update library at $timestamp"
Write-Host "Commit message: $commitMsg" -ForegroundColor Cyan
git commit -m "$commitMsg" | Out-Null

# 4. Push to GitHub
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git push origin main

Write-Host "Sync complete!" -ForegroundColor Green
Write-Host "GitHub Actions is building your site in the background." -ForegroundColor Green