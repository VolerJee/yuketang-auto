# monitor window: status, steps, log, progress

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Root     = Split-Path $PSScriptRoot -Parent
foreach ($d in @('logs', 'data')) { $f = Join-Path $Root $d; if (-not (Test-Path $f)) { New-Item -ItemType Directory -Force -Path $f | Out-Null } }
$RunLog   = Join-Path $Root "logs\run-all.log"
$LogFile  = Join-Path $Root "logs\ykt_walk.log"
$DoneFile = Join-Path $Root "data\ykt_walk_done.json"
$StatusF  = Join-Path $Root "data\status.txt"
$UserF    = Join-Path $Root "data\user.txt"

$form = New-Object System.Windows.Forms.Form
$form.Text = "雨课堂自动刷课"
$form.Size = New-Object System.Drawing.Size(780, 600)
$form.StartPosition = "Manual"
$scr = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Location = New-Object System.Drawing.Point([int]($scr.Width/2 - 390), [int]($scr.Top + 20))
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 26, 32)
$form.ForeColor = [System.Drawing.Color]::FromArgb(220, 228, 240)
$form.Font = New-Object System.Drawing.Font("Microsoft YaHei", 9)

$lblGreet = New-Object System.Windows.Forms.Label
$lblGreet.SetBounds(14, 8, 740, 34)
$lblGreet.Font = New-Object System.Drawing.Font("Microsoft YaHei", 16, [System.Drawing.FontStyle]::Bold)
$lblGreet.ForeColor = [System.Drawing.Color]::FromArgb(120, 220, 255)
$lblGreet.Text = ""
$form.Controls.Add($lblGreet)

$lblGreetSub = New-Object System.Windows.Forms.Label
$lblGreetSub.SetBounds(16, 42, 740, 20)
$lblGreetSub.Font = New-Object System.Drawing.Font("Microsoft YaHei", 9.5)
$lblGreetSub.ForeColor = [System.Drawing.Color]::FromArgb(150, 160, 180)
$lblGreetSub.Text = ""
$form.Controls.Add($lblGreetSub)

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.SetBounds(14, 66, 560, 26)
$lblStatus.Font = New-Object System.Drawing.Font("Microsoft YaHei", 10.5, [System.Drawing.FontStyle]::Bold)
$lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(235, 240, 250)
$lblStatus.Text = "准备工作…"
$form.Controls.Add($lblStatus)

$lblBadge = New-Object System.Windows.Forms.Label
$lblBadge.SetBounds(584, 64, 170, 30)
$lblBadge.Font = New-Object System.Drawing.Font("Microsoft YaHei", 11, [System.Drawing.FontStyle]::Bold)
$lblBadge.TextAlign = "MiddleCenter"
$lblBadge.ForeColor = [System.Drawing.Color]::White
$lblBadge.BackColor = [System.Drawing.Color]::FromArgb(70, 72, 80)
$lblBadge.Text = "待命"
$form.Controls.Add($lblBadge)

$lblAction = New-Object System.Windows.Forms.Label
$lblAction.SetBounds(14, 94, 740, 26)
$lblAction.Font = New-Object System.Drawing.Font("Microsoft YaHei", 10.5, [System.Drawing.FontStyle]::Bold)
$lblAction.ForeColor = [System.Drawing.Color]::FromArgb(255, 206, 84)
$lblAction.Text = "» 正在启动，请稍等…"
$form.Controls.Add($lblAction)

$lblStep = New-Object System.Windows.Forms.Label
$lblStep.SetBounds(14, 120, 740, 40)
$lblStep.Font = New-Object System.Drawing.Font("Microsoft YaHei", 8.5)
$lblStep.ForeColor = [System.Drawing.Color]::FromArgb(150, 200, 160)
$lblStep.Text = ""
$form.Controls.Add($lblStep)

$box = New-Object System.Windows.Forms.TextBox
$box.SetBounds(14, 162, 740, 300)
$box.Multiline = $true
$box.ReadOnly = $true
$box.ScrollBars = "Vertical"
$box.BackColor = [System.Drawing.Color]::FromArgb(16, 18, 22)
$box.ForeColor = [System.Drawing.Color]::FromArgb(190, 200, 214)
$box.BorderStyle = "FixedSingle"
$box.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($box)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.SetBounds(14, 472, 740, 16)
$bar.Style = "Continuous"
$bar.Minimum = 0
$bar.Maximum = 100
$bar.Value = 0
$form.Controls.Add($bar)

$lblCount = New-Object System.Windows.Forms.Label
$lblCount.SetBounds(14, 492, 740, 22)
$lblCount.Font = New-Object System.Drawing.Font("Microsoft YaHei", 9.5)
$lblCount.ForeColor = [System.Drawing.Color]::FromArgb(160, 200, 240)
$lblCount.Text = ""
$form.Controls.Add($lblCount)

$lblWarn = New-Object System.Windows.Forms.Label
$lblWarn.SetBounds(14, 518, 740, 46)
$lblWarn.Font = New-Object System.Drawing.Font("Microsoft YaHei", 10.5, [System.Drawing.FontStyle]::Bold)
$lblWarn.ForeColor = [System.Drawing.Color]::FromArgb(255, 150, 70)
  $cfgP = Join-Path $Root 'config.json'
  $keyOk = $false
  if (Test-Path $cfgP) {
    try {
      $cf = Get-Content $cfgP -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($cf.apiKey -and $cf.apiKey.Length -gt 10 -and $cf.apiKey -ne 'REPLACE_WITH_YOUR_KEY') { $keyOk = $true }
    } catch { }
  }
  if ($keyOk) {
    $lblWarn.Text = "⚠ 考试不会自动作答，需你自己完成"
    $lblWarn.ForeColor = [System.Drawing.Color]::FromArgb(255, 150, 70)
  } else {
    $lblWarn.Text = "⚠ 未配置答题 Key：请编辑 config.json 里的 apiKey`r`n    30 秒后自动继续刷课，答题功能关闭"
    $lblWarn.ForeColor = [System.Drawing.Color]::FromArgb(255, 96, 96)
  }
$form.Controls.Add($lblWarn)

# {0} = user name
$script:dow = (Get-Date).DayOfWeek.ToString()
$h0 = (Get-Date).Hour
$script:subPool = @(
  '学什么学，先摸会儿鱼',
  '刷课哪有摸鱼快乐',
  '别学了，{0}，出去走走',
  '这课不刷也毕得了业',
  '反正也记不住，别学了',
  '人生苦短，先喝杯咖啡'
)
switch ($script:dow) {
  'Friday' {
    $script:subPool = @(
      '快乐星期五，{0}翘个班吧！',
      '周五了，摸鱼是正当权利',
      '再撑一撑，下班就跑',
      '这个点儿还学？先走为敬',
      '{0}，周五下午不适合学习'
    )
  }
  'Saturday' {
    $script:subPool = @(
      '都周六了，{0}别学了',
      '周六还去工位？今天歇了吧',
      '工位不缺你一个，翘了吧',
      '周末上班是陋习，{0}别去了',
      '周六刷课？不如刷剧',
      '{0}，组里今天没你也能转'
    )
  }
  'Sunday' {
    $script:subPool = @(
      '周日了，明天又要上班，今天别学',
      '最后一天周末，躺着吧',
      '别学了，{0}，明天再说',
      '周末余额不足，省着花'
    )
  }
  default {
    if ($h0 -ge 23 -or $h0 -lt 5) {
      $script:subPool = @('这个点还在刷课，早点睡吧', '夜里学习效率为零，睡吧', '别学了，{0}，明天再说')
    }
    elseif ($h0 -lt 9) {
      $script:subPool = @('早起已经很努力了，摸会儿鱼', '早饭先吃了，课待会儿再说', '{0}，早上不该用来刷课')
    }
  }
}
$script:subText = $script:subPool | Get-Random

function Refresh-View {
  $name = ''
  if (Test-Path $UserF) { try { $name = (Get-Content $UserF -Raw -Encoding UTF8).Trim() } catch { } }
  $h = (Get-Date).Hour
  if ($h -lt 5) { $greet = '夜深了' }
  elseif ($h -lt 9) { $greet = '早上好' }
  elseif ($h -lt 11) { $greet = '上午好' }
  elseif ($h -lt 13) { $greet = '中午好' }
  elseif ($h -lt 18) { $greet = '下午好' }
  elseif ($h -lt 23) { $greet = '晚上好' }
  else { $greet = '夜深了' }
  $weekMap = @{ Monday='星期一'; Tuesday='星期二'; Wednesday='星期三'; Thursday='星期四'; Friday='星期五'; Saturday='星期六'; Sunday='星期日' }

  $subLine = $script:subText
  $subHasName = $false
  if ($name -and $subLine.Contains('{0}')) {
    try { $subLine = $subLine -f $name; $subHasName = $true } catch { }
  } elseif (-not $name) {
    $subLine = $subLine.Replace('{0}', '你')
  }
  if ($name -and -not $subHasName) { $lblGreet.Text = "$greet，$name" } else { $lblGreet.Text = $greet }
  $lblGreetSub.Text = "$($weekMap[(Get-Date).DayOfWeek.ToString()])  ·  $subLine"

  $runLines = @()
  # ignore run-all.log from a finished run
  $runFresh = $false
  if (Test-Path $RunLog) { $runFresh = ((Get-Date) - (Get-Item $RunLog).LastWriteTime).TotalSeconds -lt 180 }
  if ($runFresh) {
    $runLines = @(Get-Content $RunLog -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_.Trim() })
  }
  $joined = ($runLines -join "`n")
  if ($joined -match '登录成功') { $action = "» 已登录，正在全自动推进，你不用管了" }
  elseif ($joined -match '开始全自动') { $action = "» 准备中，马上自动开始" }
  elseif ($joined -match '等你扫码登录') { $action = "» 请在弹出的浏览器里扫码登录" }
  elseif ($joined -match '打开监控窗口') { $action = "» 马上就好…" }
  else { $action = "» 正在启动，请稍等…" }
    if (-not $runFresh) { $action = "» 正在答题，全自动进行中" }
  $lblAction.Text = $action

  $detail = @()
  foreach ($ln in ($runLines | Select-Object -Last 2)) {
    $t = $ln.Trim()
    if ($t -match '^\d{2}:\d{2}:\d{2}\s+(.*)$') { $t = $Matches[1] }
    $detail += $t
  }
  $lblStep.Text = ($detail -join "`r`n")

  $st = "准备工作…"
  if (Test-Path $StatusF) { try { $st = (Get-Content $StatusF -Raw -Encoding UTF8).Trim() } catch { } }
  if (-not $st) { $st = "准备工作…" }
  $lblStatus.Text = $st

  if ($st -match '正在看视频') {
    $lblBadge.Text = "2× 倍速播放中"
    $lblBadge.BackColor = [System.Drawing.Color]::FromArgb(38, 168, 106)
  } elseif ($st -match '正在') {
    $lblBadge.Text = "运行中"
    $lblBadge.BackColor = [System.Drawing.Color]::FromArgb(52, 96, 160)
  } else {
    $lblBadge.Text = "待命"
    $lblBadge.BackColor = [System.Drawing.Color]::FromArgb(70, 72, 80)
  }

  $body = ""
  $newest = @('ykt_walk.log', 'homework.log', 'exercise.log') | ForEach-Object {
    $f = Join-Path $Root $_
    if (Test-Path $f) { [pscustomobject]@{ path = $f; t = (Get-Item $f).LastWriteTime } }
  } | Sort-Object t -Descending | Select-Object -First 1
  if ($newest) { $LogFile = $newest.path }
  if (Test-Path $LogFile) {
    $body = ((@(Get-Content $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue) | Select-Object -Last 18) -join "`r`n")
  }
  if (-not $body) {
    $body = "还没有记录，正常。`r`n`r`n它现在要按这个顺序做：`r`n  1. 打开浏览器`r`n  2. 等你扫码登录`r`n  3. 登录后自己去读课程、自己开始刷`r`n  4. 一门刷完自动换下一门`r`n`r`n作业会自动作答；期末考试不会动，需要你自己完成。"
  }
  $box.Text = $body
  $box.SelectionStart = $box.Text.Length
  $box.ScrollToCaret()

  $doneIds = @()
  if (Test-Path $DoneFile) {
    # @() must wrap the whole pipeline or -contains breaks
    try { $doneIds = @((Get-Content $DoneFile -Raw -Encoding UTF8 | ConvertFrom-Json)) } catch { $doneIds = @() }
  }
  $uf = Get-ChildItem (Join-Path $Root 'data') -Filter 'ykt_units_*.json' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $items = @()
  if ($uf) {
    try { $items = @((Get-Content $uf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).list) } catch { $items = @() }
  }
  $total = $items.Count
    # chapter rollup
        # chap / sec / leaf
    $chapNames = @($items | ForEach-Object { if ($_.sec) { $_.sec } else { $_.chap } } | Where-Object { $_ } | Select-Object -Unique)
    $chapTotal = $chapNames.Count
    $chapDone = 0
    foreach ($cn in $chapNames) {
      $units = @($items | Where-Object { ($(if ($_.sec) { $_.sec } else { $_.chap })) -eq $cn })
      $allDone = $units.Count -gt 0
      foreach ($u in $units) {
        $uDone = $false
        if ($null -ne $u.prog) { try { if ([double]$u.prog -ge 0.999) { $uDone = $true } } catch { } }
        if (-not $uDone -and ($doneIds -contains $u.id)) { $uDone = $true }
        if (-not $uDone) { $allDone = $false; break }
      }
      if ($allDone) { $chapDone++ }
    }
    # current section
    $curText = ""
    if ($total -gt 0) {
      foreach ($it in $items) {
        $iDone = $false
        if ($null -ne $it.prog) { try { if ([double]$it.prog -ge 0.999) { $iDone = $true } } catch { } }
        if (-not $iDone -and ($doneIds -contains $it.id)) { $iDone = $true }
          if ($it.type -eq 8 -or $it.type -eq 5) { continue }
        if ($iDone) { continue }
        $mNr = [regex]::Match([string]$it.name, '^\s*(\d+)\.(\d+)')
        if ($mNr.Success) { $curText = ("当前 第{0}章第{1}节" -f $mNr.Groups[1].Value, $mNr.Groups[2].Value) }
        else { $nm = [string]$it.name; if ($nm.Length -gt 14) { $nm = $nm.Substring(0, 14) }; $curText = "当前 $nm" }
        break
      }
      if (-not $curText) { $curText = "当前 已全部完成" }
    }
  $n = 0
  if ($total -gt 0) {
    foreach ($it in $items) {
      $isDone = $false
      if ($null -ne $it.prog) { try { if ([double]$it.prog -ge 0.999) { $isDone = $true } } catch { } }
      if (-not $isDone -and ($doneIds -contains $it.id)) { $isDone = $true }
      if ($isDone) { $n++ }
    }
  } else {
      $n = 0
  }

  if ($total -gt 0) {
    # drive the bar by units, not percent
    $bar.Maximum = $total
    $bar.Value = [Math]::Min($n, $total)
    $pct = [int](100 * $n / $total)
  $hwLine = " · 已答 0 题 · 正确率 -"
  $statsF = Join-Path $Root 'data\hw_stats.json'
  if (Test-Path $statsF) {
    try {
      $hst = Get-Content $statsF -Raw -Encoding UTF8 | ConvertFrom-Json
      $ho = [int]$hst.ok; $hb = [int]$hst.bad
        if (($ho + $hb) -gt 0) {
          $hwTotal = [int]$hst.hwTotal; $hwDone = [int]$hst.hwDone; $hwLeft = $hwTotal - $hwDone
          $answered = $ho + $hb
          $hwLine = (" · 已答 {0} 题 · 正确率 {1:P0}" -f $answered, ($ho / $answered))
        }
    } catch { }
  }
    $lblCount.Text = "共 $chapTotal 章 $total 节 · 已完成 $chapDone 章 $n 节（$pct%）" + " · " + $curText + $hwLine
  } else {
    $bar.Maximum = 100
    $bar.Value = 0
    $lblCount.Text = "共 0 章 0 节 · 还没有读到课程结构"
  }
    $form.Text = "雨课堂自动刷课    第 $chapDone/$chapTotal 章 · $n/$total 节"
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({ Refresh-View })
$timer.Start()

Refresh-View
[void]$form.ShowDialog()
