# Copilot Instructions for polar-hrv-automation

## Project Overview
This repository automates the download, processing, and evaluation of Polar HRV (Heart Rate Variability) data, primarily from RR interval CSV files. It is designed for research and QA workflows involving endurance HRV analysis.

## Key Components
- **endurance_hrv.py**: Main script for HRV data processing and analysis.
- **polar_hrv_automation.py**: Likely orchestrates automation tasks or batch processing.
- **polar_api_tester.py, polar_auth_manual.py, polar_diagnostic.py**: Scripts for interacting with the Polar API, authentication, and diagnostics.
- **rr_downloads/**: Directory for raw RR interval CSV files downloaded from Polar devices.
- **ENDURANCE_HRV_*.csv**: Processed or master HRV data files.

## Data Flow
1. **Download**: RR interval files are placed in `rr_downloads/`.
2. **Processing**: Scripts (notably `endurance_hrv.py`) process these files, generating summary and master CSVs.
3. **Evaluation/QA**: Markdown and CSV outputs are used for further analysis or QA.

## Developer Workflows
- **Run Analysis**: Execute `endurance_hrv.py` directly to process new RR files.
- **Automation**: Use `polar_hrv_automation.py` for batch or scheduled processing.
- **Testing**: No formal test suite detected; validate by running scripts and inspecting output files.
- **Debugging**: Print/log statements are used; check output CSVs and markdown for results.

## Conventions & Patterns
- **File Naming**: Output files include timestamps for versioning (e.g., `*_updated_YYYYMMDD_HHMMSS.csv`).
- **No OOP**: Scripts are procedural; functions are defined at the module level.
- **Minimal External Dependencies**: Standard Python libraries and possibly `pandas` for CSV handling.
- **Manual QA**: QA is performed by reviewing generated markdown and CSVs.

## Integration Points
- **Polar API**: Used for authentication and data download (see `polar_api_tester.py`, `polar_auth_manual.py`).
- **CSV/Markdown Outputs**: Used for downstream analysis and reporting.

## Examples
- To process new RR data: `python endurance_hrv.py`
- To automate batch processing: `python polar_hrv_automation.py`

## Key Files
- `endurance_hrv.py`, `polar_hrv_automation.py`, `rr_downloads/`, `ENDURANCE_HRV_*.csv`, `ENDURANCE_HRV_*.md`

---

**Update this file if workflows or file conventions change.**
