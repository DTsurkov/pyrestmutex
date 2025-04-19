
$TotalThreads = 10

1..$TotalThreads | ForEach-Object -Parallel {
    $LockName = "test-mutex"
    $TTL = 100
    $TimeoutSec = 30
    $SleepTimeSec = 2
    $UrlBase = "http://localhost:8000"

    function Wait-For-Lock {
        param (
            [string]$LockName,
            [string]$Owner,
            [int]$TTL,
            [int]$TimeoutSec
        )
    
        $Start = Get-Date
        while (
            ((Get-Date) - $Start).TotalSeconds -lt $TimeoutSec
        ) {
            try {
                $response = Invoke-RestMethod -Uri "$UrlBase/lock/$LockName" -Method POST -Body (@{ owner = $Owner; ttl = $TTL } | ConvertTo-Json) -ContentType "application/json"
                if ($response.status -eq "locked") {
                    return $true
                }
            }
            catch {
                Start-Sleep -Milliseconds 200
            }
            Start-Sleep -Milliseconds 500
        }
        return $false
    }
    
    function Start-LockTest {
        param ($ThreadId)
    
        $owner = "thread-$ThreadId"
    
        if (Wait-For-Lock -LockName $LockName -Owner $owner -TTL $TTL -TimeoutSec $TimeoutSec) {
            Start-Sleep -Seconds $SleepTimeSec
            Write-Host "[$owner] acquired lock and did work."
            try {
                Invoke-RestMethod -Uri "$UrlBase/unlock/$LockName" -Method POST -Body (@{ owner = $owner } | ConvertTo-Json) -ContentType "application/json" | Out-Null
            }
            catch {
                Write-Host "[$owner] failed to release lock: $_"
            }
        }
        else {
            Write-Host "[$owner] failed to acquire lock within timeout."
        }
    }

    Start-LockTest -ThreadId $_
} -ThrottleLimit 100