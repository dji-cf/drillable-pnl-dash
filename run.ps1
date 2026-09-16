# Local dev launcher (Windows): loads .env (connection name override) then starts Streamlit.
#
# Runs from THIS project's .venv on purpose. The global interpreter carries
# Streamlit 1.48, which has no st.components.v2 -- the collapsible section
# headers silently do not work there, so a UI check on the global install is a
# false pass. Never `streamlit run` this app with a bare `streamlit`.
#
# NOTE: runOnSave only re-runs the ENTRY script. Edits to queries.py, data.py,
# transforms.py, table.py, interactive.py, style.py or charts.py need a full
# server restart (Ctrl-C, re-run) before you are looking at your change.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path .env) {
  foreach ($line in Get-Content .env) {
    if ($line -match '^\s*([^#=\s][^=]*)=(.*)$') {
      Set-Item -Path ("env:" + $Matches[1].Trim()) -Value $Matches[2].Trim()
    }
  }
}
& .\.venv\Scripts\streamlit.exe run streamlit_app.py @args
