param(
    [Parameter(Mandatory)]
    [System.Net.IPAddress]$Destination
)

$ErrorActionPreference = "Stop"
if ($Destination.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    [System.Net.IPAddress]::IsLoopback($Destination) -or
    $Destination.Equals([System.Net.IPAddress]::Any)) {
    throw "Set ERMES_VOICE_RTP_BIND to the WSL host's IPv4 address."
}

$port = 5004
$listen = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Loopback, $port)
$target = [System.Net.IPEndPoint]::new($Destination, $port)
$peer = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
$receiver = [System.Net.Sockets.UdpClient]::new($listen)
$sender = [System.Net.Sockets.UdpClient]::new()
try {
    Write-Host "Relaying AudioServer RTP from $listen to $target. Press Ctrl+C to stop."
    while ($true) {
        if ($receiver.Available -eq 0) {
            Start-Sleep -Milliseconds 10
            continue
        }
        $packet = $receiver.Receive([ref]$peer)
        [void]$sender.Send($packet, $packet.Length, $target)
    }
} finally {
    $receiver.Dispose()
    $sender.Dispose()
}
