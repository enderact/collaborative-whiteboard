# Reports the page each Heading 1 lands on, so the page budget can be cut where
# the pages actually are rather than where they feel like they are.
$path = (Resolve-Path "docs\Review2_Design_and_Implementation_NS02.docx").Path
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Open($path, $false, $true)
$doc.Repaginate()

$wdActiveEndPageNumber = 3
$marks = @()
foreach ($p in $doc.Paragraphs) {
    if ($p.OutlineLevel -eq 1) {
        $marks += [pscustomobject]@{
            Page = $p.Range.Information($wdActiveEndPageNumber)
            Head = $p.Range.Text.Trim()
        }
    }
}
$total = $doc.ComputeStatistics(2)

for ($i = 0; $i -lt $marks.Count; $i++) {
    $end = if ($i + 1 -lt $marks.Count) { $marks[$i + 1].Page } else { $total }
    $span = $end - $marks[$i].Page + 1
    "{0,3}  span~{1,2}  {2}" -f $marks[$i].Page, $span, $marks[$i].Head
}
"total pages: $total"

$doc.Close($false)
$word.Quit()
