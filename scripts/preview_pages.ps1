# Export the built document to PDF so pages can be rendered and eyeballed.
$docx = (Resolve-Path "docs\Review2_Design_and_Implementation_NS02.docx").Path
$pdf = [System.IO.Path]::ChangeExtension($docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Open($docx, $false, $true)
$wdExportFormatPDF = 17
$doc.ExportAsFixedFormat($pdf, $wdExportFormatPDF)
$doc.Close($false)
$word.Quit()
"pdf: $pdf"
