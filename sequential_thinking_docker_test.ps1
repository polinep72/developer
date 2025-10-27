# Sends MCP frames to Sequential Thinking server in Docker via stdio
# Requires: Docker

$ErrorActionPreference = 'Stop'

function Send-Frame {
  param(
    [Parameter(Mandatory=$true)][string]$Method,
    [Parameter()][hashtable]$Params=@{},
    [Parameter()][int]$Id=1
  )
  $payload = @{ jsonrpc = '2.0'; id = $Id; method = $Method; params = $Params }
  $json = $payload | ConvertTo-Json -Compress -Depth 10
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $len = $bytes.Length
  $header = "Content-Length: $len`r`nContent-Type: application/vscode-jsonrpc; charset=utf-8`r`n`r`n"
  $hbytes = [Text.Encoding]::UTF8.GetBytes($header)
  [Console]::OpenStandardOutput().Write($hbytes,0,$hbytes.Length)
  [Console]::OpenStandardOutput().Write($bytes,0,$bytes.Length)
}

# Build frames in memory and write once to docker stdin
$tempFile = [System.IO.Path]::GetTempFileName() + '.bin'

$frames = New-Object System.Collections.Generic.List[byte]

function Add-FrameBytes {
  param([string]$Method, [hashtable]$Params, [int]$Id)
  $payload = @{ jsonrpc = '2.0'; id = $Id; method = $Method; params = $Params }
  $json = ($payload | ConvertTo-Json -Compress -Depth 10)
  $jbytes = [Text.Encoding]::UTF8.GetBytes($json)
  $header = "Content-Length: $($jbytes.Length)`r`nContent-Type: application/vscode-jsonrpc; charset=utf-8`r`n`r`n"
  $hbytes = [Text.Encoding]::UTF8.GetBytes($header)
  [void]$frames.AddRange($hbytes)
  [void]$frames.AddRange($jbytes)
}

# 1) initialize
Add-FrameBytes -Method 'initialize' -Params @{ version = '2024-11-05'; capabilities = @{}; clientInfo = @{ name='ps1-docker-test'; version='1.0.0' } } -Id 1
# 2) tools/list
Add-FrameBytes -Method 'tools/list' -Params @{} -Id 2
# 3) tools/call x3 (ASCII-only payloads)
Add-FrameBytes -Method 'tools/call' -Params @{ name='sequential_thinking'; arguments = @{ thought='Step 1: define goal'; nextThoughtNeeded=$true; thoughtNumber=1; totalThoughts=5 } } -Id 3
Add-FrameBytes -Method 'tools/call' -Params @{ name='sequential_thinking'; arguments = @{ thought='Revision of step 1'; isRevision=$true; revisesThought=1; nextThoughtNeeded=$true; thoughtNumber=2; totalThoughts=5 } } -Id 4
Add-FrameBytes -Method 'tools/call' -Params @{ name='sequential_thinking'; arguments = @{ thought='Branch A'; branchFromThought=2; branchId='A'; nextThoughtNeeded=$false; thoughtNumber=3; totalThoughts=5 } } -Id 5

[IO.File]::WriteAllBytes($tempFile, $frames.ToArray())

# Run container and pipe frames to stdin
$dockerArgs = @('run','--rm','-i','mcp/sequentialthinking')
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'docker'
$psi.Arguments = ($dockerArgs -join ' ')
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
$null = $proc.Start()

# async read outputs
$stdOutTask = [System.Threading.Tasks.Task]::Run({
  $sr = $proc.StandardOutput
  while(-not $sr.EndOfStream){
    $line = $sr.ReadLine()
    if($line){ Write-Host $line }
  }
})
$stdErrTask = [System.Threading.Tasks.Task]::Run({
  $sr = $proc.StandardError
  while(-not $sr.EndOfStream){
    $line = $sr.ReadLine()
    if($line){ Write-Host "[server] $line" }
  }
})

# write frames to stdin
$bytes = [IO.File]::ReadAllBytes($tempFile)
$proc.StandardInput.BaseStream.Write($bytes,0,$bytes.Length)
$proc.StandardInput.Close()

# wait up to 45s
if(-not $proc.WaitForExit(45000)){
  try { $proc.Kill() } catch {}
  throw 'Timeout waiting docker process to exit'
}

Remove-Item $tempFile -ErrorAction Ignore

Write-Host "Done. ExitCode=$($proc.ExitCode)"