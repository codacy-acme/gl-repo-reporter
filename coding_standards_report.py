#!/usr/bin/env python3

import os
import requests
import argparse
import csv
import time
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm
from datetime import datetime

class CodacyAPI:
    """Class to handle Codacy API interactions"""
    
    def __init__(self, api_token: Optional[str] = None, provider: str = "gh", organization: str = None):
        self.api_token = api_token or os.environ.get("CODACY_API_TOKEN")
        self.provider = provider
        self.organization = organization
        self.base_url = "https://app.codacy.com/api/v3"
        
        if not self.api_token:
            raise ValueError("Codacy API token not provided. Set CODACY_API_TOKEN environment variable or pass it as an argument.")
        
        self.headers = {
            "api-token": self.api_token,
            "Accept": "application/json"
        }

    def _make_request(self, url: str, params: Dict = None, max_retries: int = 3) -> Dict:
        """Make an API request with retry logic and rate limit handling"""
        retries = 0
        while retries < max_retries:
            try:
                response = requests.get(url, headers=self.headers, params=params)
                
                if response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"\nRate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries == max_retries:
                    raise Exception(f"API request failed after {max_retries} retries: {str(e)}")
                print(f"\nRequest failed, retrying ({retries}/{max_retries}): {str(e)}")
                time.sleep(2 ** retries)  # Exponential backoff
        
        raise Exception("Maximum retries exceeded")

    def get_coding_standards(self) -> List[Dict[str, Any]]:
        """Fetch all coding standards for the organization"""
        url = f"{self.base_url}/organizations/{self.provider}/{self.organization}/coding-standards"
        standards = self._make_request(url)["data"]
        return [s for s in standards if not s.get("isDraft", False)]  # Always exclude drafts

    def get_repositories_for_standard(self, standard_id: str) -> List[Dict[str, Any]]:
        """Get repositories attached to a specific coding standard"""
        url = f"{self.base_url}/organizations/{self.provider}/{self.organization}/coding-standards/{standard_id}/repositories"
        return self._make_request(url)["data"]

    def get_repository_analysis(self, repository: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """Get repository analysis information"""
        try:
            url = f"{self.base_url}/analysis/organizations/{self.provider}/{self.organization}/repositories/{repository}"
            response = self._make_request(url)
            data = response.get("data", {})
            
            # Calculate coverage percentage
            coverage_data = data.get("coverage", {})
            total_files = coverage_data.get("numberTotalFiles", 0)
            uncovered_files = coverage_data.get("filesUncovered", 0)
            low_coverage_files = coverage_data.get("filesWithLowCoverage", 0)
            coverage_percentage = 0 if total_files == 0 else ((total_files - uncovered_files - low_coverage_files) / total_files) * 100
            
            # Extract metrics from the response
            metrics = {
                "grade": f"{data.get('gradeLetter', 'N/A')} ({data.get('grade', 0)}%)",
                "issues": {
                    "Critical": 0,  # These are not broken down by severity in the response
                    "Medium": 0,
                    "Minor": 0,
                    "Total": data.get("issuesCount", 0)
                },
                "coverage": round(coverage_percentage, 2),
                "complexity": data.get("complexFilesCount", 0),
                "duplication": data.get("duplicationPercentage", 0),
                "loc": data.get("loc", 0)
            }
            
            return metrics, None
        except Exception as e:
            if "404" in str(e):
                return {}, "Repository not analyzed"
            return {}, str(e)

def generate_report(api: CodacyAPI) -> None:
    """Generate a report of coding standards and their associated repositories and issues"""
    print("Fetching coding standards...")
    standards = api.get_coding_standards()
    
    if not standards:
        print("No coding standards found.")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"coding_standards_report_{timestamp}.csv"
    
    with open(report_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Coding Standard",
            "Is Default",
            "Enabled Tools",
            "Enabled Patterns",
            "Repository",
            "Grade",
            "Total Issues",
            "Lines of Code",
            "Coverage %",
            "Complex Files",
            "Duplication %",
            "Error"
        ])
        
        for standard in tqdm(standards, desc="Processing coding standards"):
            print(f"\nAnalyzing coding standard: {standard['name']}")
            repositories = api.get_repositories_for_standard(standard['id'])
            
            if not repositories:
                writer.writerow([
                    standard['name'],
                    standard.get('isDefault', False),
                    standard.get('meta', {}).get('enabledToolsCount', 0),
                    standard.get('meta', {}).get('enabledPatternsCount', 0),
                    "No repositories",
                    "N/A", 0, 0, 0, 0, 0,
                    ""
                ])
                continue
            
            for repo in tqdm(repositories, desc="Processing repositories", leave=False):
                repo_name = repo.get("name", "")
                if not repo_name:
                    continue
                    
                metrics, error = api.get_repository_analysis(repo_name)
                
                if error:
                    writer.writerow([
                        standard['name'],
                        standard.get('isDefault', False),
                        standard.get('meta', {}).get('enabledToolsCount', 0),
                        standard.get('meta', {}).get('enabledPatternsCount', 0),
                        repo_name,
                        "N/A", "Error", "Error", "Error", "Error", "Error",
                        error
                    ])
                else:
                    writer.writerow([
                        standard['name'],
                        standard.get('isDefault', False),
                        standard.get('meta', {}).get('enabledToolsCount', 0),
                        standard.get('meta', {}).get('enabledPatternsCount', 0),
                        repo_name,
                        metrics.get("grade", "N/A"),
                        metrics.get("issues", {}).get("Total", 0),
                        metrics.get("loc", 0),
                        metrics.get("coverage", 0),
                        metrics.get("complexity", 0),
                        metrics.get("duplication", 0),
                        ""
                    ])
    
    print(f"\nReport generated: {report_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate a Codacy coding standards report")
    parser.add_argument("--token", help="Codacy API token (optional if CODACY_API_TOKEN env var is set)")
    parser.add_argument("--provider", default="gh", help="Git provider (gh, gl, bb) (default: gh)")
    parser.add_argument("--organization", required=True, help="Organization name")
    
    args = parser.parse_args()
    
    try:
        api = CodacyAPI(args.token, args.provider, args.organization)
        generate_report(api)
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main() 