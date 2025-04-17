# Codacy Coding Standards Report Generator

This PR adds a Python script that generates a comprehensive CSV report of coding standards and their associated metrics from Codacy.

## Features

- Fetches all non-draft coding standards from an organization
- For each coding standard, retrieves:
  - Basic information (name, default status)
  - Number of enabled tools and patterns
  - Associated repositories and their metrics
- For each repository, includes:
  - Grade (letter and percentage)
  - Total number of issues
  - Lines of Code
  - Coverage percentage
  - Number of complex files
  - Duplication percentage

## Technical Details

- Uses Codacy API v3
- Implements proper error handling and rate limiting
- Handles pagination where necessary
- Generates timestamped CSV reports
- Excludes draft coding standards

## Usage

```bash
python coding_standards_report.py --organization <org> [--token <token>] [--provider <gh|gl|bb>]
```

## Dependencies

Added `requirements.txt` with:
- requests>=2.31.0
- tqdm>=4.66.0

## Testing

The script has been tested with:
- Multiple coding standards
- Repositories with and without analysis
- Various error conditions (rate limiting, API errors)

## Notes

- Generated CSV reports are ignored in git
- Virtual environment files are ignored
- The script requires a Codacy API token (can be provided via environment variable or command line) 