param (
    [string]$Title = "SortMeDown",
    [string]$Message = "A file has been moved."
)

try {
    # Load required Windows Runtime assemblies
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

    # Get the toast notification template
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)

    # Set the title and message text
    $xml = $template.GetElementsByTagName("text")
    $xml[0].AppendChild($template.CreateTextNode($Title)) | Out-Null
    $xml[1].AppendChild($template.CreateTextNode($Message)) | Out-Null

    # Create the toast notification from the XML
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)

    # Show the notification
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SortMeDown")
    $notifier.Show($toast)
}
catch {
    # Write any errors to a log file in the temp directory to avoid polluting the main console
    $errorLogPath = Join-Path $env:TEMP "SortMeDown_Notification_Error.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] Error sending notification: $($_.Exception.Message)" | Out-File -FilePath $errorLogPath -Append
}