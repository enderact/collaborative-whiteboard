# Export the deck to PDF so slides can be rendered and checked for overflow,
# which python-pptx cannot detect on its own.
$pptx = (Resolve-Path "docs\Review2_Presentation_NS02.pptx").Path
$pdf = [System.IO.Path]::ChangeExtension($pptx, ".pdf")
$pp = New-Object -ComObject PowerPoint.Application
$deck = $pp.Presentations.Open($pptx, $true, $false, $false)
$ppSaveAsPDF = 32
$deck.SaveAs($pdf, $ppSaveAsPDF)
$deck.Close()
$pp.Quit()
"pdf: $pdf"
