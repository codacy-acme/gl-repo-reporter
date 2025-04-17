#!/usr/bin/env python3

import os
import requests
import argparse
import csv
import time
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm
from datetime import datetime
from collections import defaultdict

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
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _make_request(self, url: str, method: str = "GET", params: Dict = None, json_data: Dict = None, max_retries: int = 3) -> Dict:
        """Make an API request with retry logic and rate limit handling"""
        retries = 0
        while retries < max_retries:
            try:
                if method == "GET":
                    response = requests.get(url, headers=self.headers, params=params)
                elif method == "POST":
                    response = requests.post(url, headers=self.headers, params=params, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
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
        return [s for s in standards if not s.get("isDraft", False)]

    def get_repositories_for_standard(self, standard_id: str) -> List[Dict[str, Any]]:
        """Get repositories attached to a specific coding standard"""
        url = f"{self.base_url}/organizations/{self.provider}/{self.organization}/coding-standards/{standard_id}/repositories"
        return self._make_request(url)["data"]

    def search_repository_issues(self, repository: str, filters: Dict = None, quick_mode: bool = False) -> Any:
        """Search for issues in a repository with optional filters"""
        url = f"{self.base_url}/analysis/organizations/{self.provider}/{self.organization}/repositories/{repository}/issues/search"
        
        if quick_mode:
            # In quick mode, we only need one API call to get the counts
            params = {"limit": 1}  # Minimal data for counting
            data = self._make_request(url, method="POST", params=params, json_data=filters or {})
            return {
                "total": data.get("pagination", {}).get("total", 0),
                "counts": data.get("counts", {})
            }
        
        # Detailed mode - fetch all issues
        all_issues = []
        cursor = None
        
        while True:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            
            data = self._make_request(url, method="POST", params=params, json_data=filters or {})
            issues = data.get("data", [])
            all_issues.extend(issues)
            
            pagination = data.get("pagination", {})
            cursor = pagination.get("cursor")
            if not cursor:
                break
        
        return all_issues

def generate_quick_report(api: CodacyAPI, filters: Dict = None) -> None:
    """Generate a summary report of issues by severity for each coding standard"""
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
            "Repository",
            "Total Issues",
            "Error",
            "Warning",
            "Info"
        ])
        
        for standard in tqdm(standards, desc="Processing coding standards"):
            print(f"\nAnalyzing coding standard: {standard['name']}")
            repositories = api.get_repositories_for_standard(standard['id'])
            
            if not repositories:
                continue
            
            for repo in tqdm(repositories, desc="Processing repositories", leave=False):
                repo_name = repo.get("name", "")
                if not repo_name:
                    continue
                
                try:
                    result = api.search_repository_issues(repo_name, filters, quick_mode=True)
                    counts = result.get("counts", {})
                    
                    writer.writerow([
                        standard['name'],
                        repo_name,
                        result.get("total", 0),
                        counts.get("Error", 0),
                        counts.get("Warning", 0),
                        counts.get("Info", 0)
                    ])
                except Exception as e:
                    print(f"Error processing repository {repo_name}: {str(e)}")
                    writer.writerow([
                        standard['name'],
                        repo_name,
                        "Error",
                        str(e),
                        "",
                        ""
                    ])
    
    print(f"\nQuick summary report generated: {report_file}")

def generate_detailed_report(api: CodacyAPI, filters: Dict = None) -> None:
    """Generate a detailed report of issues grouped by coding standard"""
    print("Fetching coding standards...")
    standards = api.get_coding_standards()
    
    if not standards:
        print("No coding standards found.")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"detailed_issues_report_{timestamp}.csv"
    
    with open(report_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Coding Standard",
            "Repository",
            "File",
            "Line",
            "Issue ID",
            "Pattern",
            "Category",
            "Level",
            "Message",
            "Author",
            "Created At"
        ])
        
        for standard in tqdm(standards, desc="Processing coding standards"):
            print(f"\nAnalyzing coding standard: {standard['name']}")
            repositories = api.get_repositories_for_standard(standard['id'])
            
            if not repositories:
                continue
            
            for repo in tqdm(repositories, desc="Processing repositories", leave=False):
                repo_name = repo.get("name", "")
                if not repo_name:
                    continue
                
                try:
                    issues = api.search_repository_issues(repo_name, filters, quick_mode=False)
                    
                    for issue in issues:
                        writer.writerow([
                            standard['name'],
                            repo_name,
                            issue.get("filePath", ""),
                            issue.get("lineNumber", ""),
                            issue.get("id", ""),
                            issue.get("patternInfo", {}).get("id", ""),
                            issue.get("patternInfo", {}).get("category", ""),
                            issue.get("patternInfo", {}).get("severityLevel", ""),
                            issue.get("message", ""),
                            issue.get("authorName", ""),
                            issue.get("createdAt", "")
                        ])
                except Exception as e:
                    print(f"Error processing repository {repo_name}: {str(e)}")
                    writer.writerow([
                        standard['name'],
                        repo_name,
                        "Error",
                        "",
                        "",
                        "",
                        "",
                        "",
                        str(e),
                        "",
                        ""
                    ])
    
    print(f"\nDetailed report generated: {report_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate a Codacy issues report grouped by coding standard")
    parser.add_argument("--token", help="Codacy API token (optional if CODACY_API_TOKEN env var is set)")
    parser.add_argument("--provider", default="gh", help="Git provider (gh, gl, bb) (default: gh)")
    parser.add_argument("--organization", required=True, help="Organization name")
    parser.add_argument("--levels", help="Comma-separated list of severity levels (Error,Warning,Info)")
    parser.add_argument("--categories", help="Comma-separated list of categories")
    parser.add_argument("--languages", help="Comma-separated list of languages")
    parser.add_argument("--authors", help="Comma-separated list of author emails")
    parser.add_argument("--branch", help="Branch name to analyze")
    parser.add_argument("--quick", action="store_true", help="Generate a quick summary report instead of detailed report")
    
    args = parser.parse_args()
    
    # Build filters dictionary
    filters = {}
    if args.levels:
        filters["levels"] = [level.strip() for level in args.levels.split(",")]
    if args.categories:
        filters["categories"] = [cat.strip() for cat in args.categories.split(",")]
    if args.languages:
        filters["languages"] = [lang.strip() for lang in args.languages.split(",")]
    if args.authors:
        filters["authorEmails"] = [email.strip() for email in args.authors.split(",")]
    if args.branch:
        filters["branchName"] = args.branch
    
    try:
        api = CodacyAPI(args.token, args.provider, args.organization)
        if args.quick:
            generate_quick_report(api, filters)
        else:
            generate_detailed_report(api, filters)
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main() 