# ============================================================================
# MACCRE TELEMETRY: AI Studio Delta-Sync Extractor
# ============================================================================

$sourceDir = "G:\My Drive\Google AI Studio"
$backupDir = "B:\AIStudio-Backups"

if (!(Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

# .NET List for O(1) memory appending (replaces the memory-leaking += array)
$global:fullOutputList =[System.Collections.Generic.List[string]]::new()

function Get-ConversationData {
    param($Object,[System.Collections.Generic.List[PSCustomObject]]$ResultsList)
    
    if ($Object -is [PSCustomObject]) {
        # Check if this object is a conversation "chunk"
        if ($Object.text -and $Object.role) {
            $ResultsList.Add([PSCustomObject]@{
                Role      = $Object.role
                Text      = $Object.text
                IsThought = $Object.isThought -eq $true
                Time      = if ($Object.createTime) { $Object.createTime } elseif ($Object.updateTime) { $Object.updateTime } else { $null }
            })
        }
        # Continue drilling down
        foreach ($p in $Object.PSObject.Properties) {
            Get-ConversationData -Object $p.Value -ResultsList $ResultsList
        }
    }
    elseif ($Object -is [Array]) {
        foreach ($item in $Object) { 
            Get-ConversationData -Object $item -ResultsList $ResultsList 
        }
    }
}

# AI Studio files have no extension. Filter out directories.
$files = Get-ChildItem -Path $sourceDir | Where-Object { !$_.PSIsContainer -and [string]::IsNullOrEmpty($_.Extension) }

foreach ($sourceFile in $files) {
    $destinationPath = Join-Path $backupDir ($sourceFile.Name + ".md")
    
    # THE DELTA-SYNC ENGINE: Only overwrite if the Drive file is newer than the Markdown backup
    if (Test-Path $destinationPath) {
        $destFile = Get-Item $destinationPath
        if ($sourceFile.LastWriteTimeUtc -le $destFile.LastWriteTimeUtc) {
            # File is perfectly synced. Skip parsing entirely.
            continue 
        } else {
            Write-Host "Update Detected: $($sourceFile.Name) (Overwriting with new data)" -ForegroundColor Cyan
        }
    } else {
        Write-Host "New Conversation: $($sourceFile.Name) (Creating backup)" -ForegroundColor Magenta
    }

    try {
        $rawJSON = Get-Content $sourceFile.FullName -Raw | ConvertFrom-Json
        $global:fullOutputList.Clear()

        # Metadata Header
        $modelName = $rawJSON.runSettings.model -or $rawJSON.fullContent.runSettings.model -or "Gemini-Unknown"
        $global:fullOutputList.Add("# SOURCE: $($sourceFile.Name)")
        $global:fullOutputList.Add("> **Model:** $modelName`n---`n")

        # Surgical Extraction using .NET Lists
        $chatData = [System.Collections.Generic.List[PSCustomObject]]::new()
        Get-ConversationData -Object $rawJSON -ResultsList $chatData

        if ($chatData.Count -gt 0) {
            foreach ($entry in $chatData) {
                $timeLabel = if ($entry.Time) { " - " + $entry.Time } else { "" }
                
                if ($entry.IsThought) {
                    $global:fullOutputList.Add("### [AI THOUGHT]$timeLabel`n> $($entry.Text -replace '`n', '`n> ')`n")
                } elseif ($entry.Role -eq "user") {
                    $global:fullOutputList.Add("## USER$timeLabel`n$($entry.Text)`n")
                } else {
                    $global:fullOutputList.Add("## AI RESPONSE$timeLabel`n$($entry.Text)`n")
                }
                $global:fullOutputList.Add("---")
            }
        }

        if ($global:fullOutputList.Count -gt 3) {
            # Write to disk in one rapid I/O operation
            [System.IO.File]::WriteAllLines($destinationPath, $global:fullOutputList.ToArray())
            Write-Host "  -> Successfully Synced: $($sourceFile.Name)" -ForegroundColor Green
        }
    }
    catch {
        Write-Warning "Failed to parse $($sourceFile.Name): $_"
    }
}

Write-Host "`n✅ AI Studio Delta-Sync Complete." -ForegroundColor Green