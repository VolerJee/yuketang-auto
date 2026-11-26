# one-click: browser -> monitor -> wait login -> python core

param(
  [string]$Root = (Split-Path $PSScriptRoot -Parent),
  [int]$Port = 9340
)

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Find-Browser([string]$Prefer = '') {
  $list = @(
    @{ Name = 'Chrome'; Path = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" },
    @{ Name = 'Chrome'; Path = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe" },
    @{ Name = 'Chrome'; Path = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" },
    @{ Name = 'Edge';   Path = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" },
    @{ Name = 'Edge';   Path = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe" }
  )
  if ($Prefer) {
    foreach ($c in $list) {
      if ($c.Name -eq $Prefer -and (Test-Path $c.Path)) { return [pscustomobject]@{ Name = $c.Name; Path = $c.Path } }
    }
  }
  foreach ($c in $list) {
    if ($c.Path -and (Test-Path $c.Path)) { return [pscustomobject]@{ Name = $c.Name; Path = $c.Path } }
  }
  foreach ($reg in 'chrome.exe', 'msedge.exe') {
    $r = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\$reg" -ErrorAction SilentlyContinue).'(default)'
    if ($r -and (Test-Path $r)) {
      $n = if ($reg -like 'msedge*') { 'Edge' } else { 'Chrome' }
      return [pscustomobject]@{ Name = $n; Path = $r }
    }
  }
  return $null
}

function Resolve-Python([string]$Base) {
  $local = Join-Path $Base 'runtime\python\python.exe'
  if (Test-Path $local) { return $local }
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    try {
      $major = & $cmd.Source -c "import sys;print(sys.version_info[0])" 2>$null
      if ("$major".Trim() -eq '3') { return $cmd.Source }
    } catch { }
  }
  return $null
}

function Install-Python([string]$Base) {
  $dir = Join-Path $Base 'runtime\python'
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $zip = Join-Path $Base 'runtime\python-embed.zip'
  Write-Host "      没有找到 Python，下载一个便携版（约 11 MB，只需一次）…"
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip' -OutFile $zip -UseBasicParsing
  Expand-Archive -Path $zip -DestinationPath $dir -Force
  Remove-Item $zip -Force -ErrorAction SilentlyContinue
  $exe = Join-Path $dir 'python.exe'
  if (-not (Test-Path $exe)) { return $null }
  return $exe
}

$browserFile = Join-Path $Root 'data\browser.txt'
$prefer = ''
if (Test-Path $browserFile) { try { $prefer = (Get-Content $browserFile -Raw -Encoding UTF8).Trim() } catch { } }

$browser = Find-Browser $prefer
if (-not $browser) {
  Write-Host "没有找到可用的浏览器，请安装 Edge 或 Chrome"
  Read-Host "按回车退出"
  exit 1
}
if (-not $prefer) {
  try { [IO.File]::WriteAllText($browserFile, $browser.Name, (New-Object Text.UTF8Encoding($false))) } catch { }
}

$ProfileDir = Join-Path $Root 'data\cdp-profile'

function Test-Cdp {
  try { Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

# ---------- notice ----------
Write-Host ""
Write-Host "============ 雨课堂自动刷课 ============"
Write-Host "  等待确认使用须知…"
Add-Type -AssemblyName System.Windows.Forms | Out-Null
Add-Type -AssemblyName System.Drawing | Out-Null
$notice = (@(
  '使用须知',
  '',
  '继续使用即代表你已知晓并接受：',
  '',
  '1. 本工具会代替你完成课程学习，平台会记录学习行为，',
  '   学校可能据此认定异常，后果由使用者自行承担。',
  '',
  '2. AI 答题不保证正确，可能影响作业成绩。',
  '',
  '3. 考试不会自动作答，需要你本人完成。',
  '',
  '是否继续？'
) -join "`r`n")
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $true
$owner.FormBorderStyle = 'FixedToolWindow'
$owner.Text = '雨课堂自动刷课 - 使用须知'
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.StartPosition = 'CenterScreen'
$owner.Show()
$owner.Activate()
try {
  $ans = [System.Windows.Forms.MessageBox]::Show(
    $owner, $notice, '雨课堂自动刷课 - 使用须知',
    [System.Windows.Forms.MessageBoxButtons]::OKCancel,
    [System.Windows.Forms.MessageBoxIcon]::Warning,
    [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
} catch {
  $owner.Close()
  Write-Host "  无法显示确认窗口，已中止"
  exit 1
}
$owner.Close()
if ($ans -ne [System.Windows.Forms.DialogResult]::OK) {
  Write-Host "  已取消，程序退出"
  Start-Sleep -Seconds 2
  exit 1
}

# ---------- python ----------
$py = Resolve-Python $Root
if (-not $py) { $py = Install-Python $Root }
if (-not $py -or -not (Test-Path $py)) {
  Write-Host "      Python 运行时不可用，无法继续"
  Read-Host "按回车退出"
  exit 1
}
$env:PYTHONIOENCODING = 'utf-8'
$Cli = Join-Path $Root 'core\cli.py'

# ---------- browser ----------
Write-Host ("[1/4] 打开浏览器（{0}）" -f $browser.Name)
$browserPid = 0
if (Test-Cdp) {
  Write-Host "      浏览器已经在运行，直接用"
} else {
  $proc = Start-Process -FilePath $browser.Path -ArgumentList @(
    "--user-data-dir=$ProfileDir",
    "--remote-debugging-port=$Port",
    "--mute-audio",
    "--window-size=1280,800",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--autoplay-policy=no-user-gesture-required",
    "--no-first-run", "--no-default-browser-check",
    "https://www.yuketang.cn/v2/web/index"
  ) -PassThru
  if ($proc) { $browserPid = $proc.Id }
  $ok = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 800
    if (Test-Cdp) { $ok = $true; break }
  }
  if (-not $ok) {
    Write-Host "      浏览器打不开，可能被杀毒软件拦了"
    Read-Host "按回车退出"
    exit 1
  }
  Write-Host ("      已打开（{0}）" -f $browser.Name)
}

# ---------- monitor ----------
Write-Host "[2/4] 打开监控窗口"
try {
  $monRunning = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
                  Where-Object { $_.CommandLine -like '*监控.ps1*' }).Count
  if ($monRunning -eq 0) {
    Start-Process -FilePath 'powershell' -ArgumentList @(
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
      '-File', (Join-Path $PSScriptRoot '监控.ps1')
    ) | Out-Null
    Start-Sleep -Milliseconds 1200
  }
  Write-Host "      监控窗口就是唯一界面，进度都在那里看"
} catch {
  Write-Host "      监控窗口没起来，不影响刷课"
}

# ---------- login ----------
Write-Host "[3/4] 等你扫码登录"
Write-Host "      【需要你做的只有一件事】在弹出的浏览器里扫码登录"
Write-Host "      登录之后不用再操作，它会自己进课程、自己开始刷"
Write-Host "      最长等 15 分钟…"

$waitArgs = @('-X', 'utf8', $Cli, 'wait-login', '--port', "$Port", '--timeout', '900')
& $py @waitArgs
if ($LASTEXITCODE -ne 0) {
  Write-Host "      等太久了，先退出。登录好之后再双击一次 一键启动.exe"
  Read-Host "按回车退出"
  exit 1
}
Write-Host "      登录成功"

# ---------- key ----------
$cfgPath = Join-Path $Root 'config.json'
$hasKey = $false
if (Test-Path $cfgPath) {
  try {
    $cf = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cf.apiKey -and $cf.apiKey.Length -gt 10 -and $cf.apiKey -ne 'REPLACE_WITH_YOUR_KEY') { $hasKey = $true }
  } catch { }
}
if (-not $hasKey) {
  Write-Host ""
  Write-Host "=================================================="
  Write-Host "  没有找到答题用的 API Key"
  Write-Host "  请打开这个文件："
  Write-Host "    $cfgPath"
  Write-Host "  把 apiKey 那一行改成 sk- 开头的字符串并保存，"
  Write-Host "  下次启动就会自动开启答题功能。"
  Write-Host "  答题功能已关闭，30 秒后先继续刷课…"
  Write-Host "=================================================="
  Write-Host ""
  Start-Sleep -Seconds 30
}

# ---------- run ----------
Write-Host "[4/4] 开始全自动"
Start-Sleep -Seconds 2

$walkArgs = @('-X', 'utf8', $Cli, 'walk', '--root', $Root, '--port', "$Port")
if ($browserPid -gt 0) { $walkArgs += @('--browser-pid', "$browserPid") }
& $py @walkArgs
exit $LASTEXITCODE
