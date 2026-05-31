# Paths
$sourceDir = "G:\My Drive\Google AI Studio"
$backupDir = "B:\AIStudio-Backups"

if (!(Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir }

# Improved Recursive Function with suppressed boolean output
function Get-ConversationData {
    param($Object)
    $results = @()
    
    if ($Object -is [PSCustomObject]) {
        # Check if this object is a conversation "chunk"
        if ($Object.text -and $Object.role) {
            $null = $results += [PSCustomObject]@{
                Role      = $Object.role
                Text      = $Object.text
                IsThought = $Object.isThought -eq $true
                Time      = $Object.createTime -or $Object.updateTime
            }
        }
        # Continue drilling down
        foreach ($p in $Object.PSObject.Properties) {
            $null = $results += Get-ConversationData -Object $p.Value
        }
    }
    elseif ($Object -is [Array]) {
        foreach ($item in $Object) { $null = $results += Get-ConversationData -Object $item }
    }
    return $results
}

$files = Get-ChildItem -Path $sourceDir | Where-Object { !$_.PSIsContainer -and [string]::IsNullOrEmpty($_.Extension) }

foreach ($file in $files) {
    $destinationPath = Join-Path $backupDir ($file.Name + ".md")
    
    # Informative Skip Logic
    if (Test-Path $destinationPath) { 
        Write-Host "Skipping: $($file.Name) (File already exists in backup)" -ForegroundColor Gray
        continue 
    }

    try {
        $rawJSON = Get-Content $file.FullName -Raw | ConvertFrom-Json
        $fullOutput = @()

        # Metadata Header
        $modelName = $rawJSON.runSettings.model -or $rawJSON.fullContent.runSettings.model -or "Gemini"
        $null = $fullOutput += "# SOURCE: $($file.Name)"
        $null = $fullOutput += "> **Model:** $modelName`n---`n"

        # Surgical Extraction
        $chatData = Get-ConversationData -Object $rawJSON

        if ($chatData) {
            foreach ($entry in $chatData) {
                $timeLabel = if ($entry.Time) { " - " + $entry.Time } else { "" }
                
                if ($entry.IsThought) {
                    $null = $fullOutput += "### [AI THOUGHT]$timeLabel`n> $($entry.Text)`n"
                } elseif ($entry.Role -eq "user") {
                    $null = $fullOutput += "## USER$timeLabel`n$($entry.Text)`n"
                } else {
                    $null = $fullOutput += "## AI RESPONSE$timeLabel`n$($entry.Text)`n"
                }
                $null = $fullOutput += "---"
            }
        }

        if ($fullOutput.Count -gt 3) {
            $fullOutput -join "`n" | Out-File -FilePath $destinationPath -Encoding utf8
            Write-Host "Cleaned & Archived: $($file.Name)" -ForegroundColor Green
        }
    }
    catch {
        Write-Warning "Skipped $($file.Name): JSON parsing error."
    }
}