#!/usr/bin/env python3

import os
import requests
import argparse
import csv
from typing import List, Dict, Any, Optional
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

    def get_coding_standards(self) -> List[Dict[str, Any]]:
        """Fetch all coding standards for the organization"""
        url = f"{self.base_url}/organizations/{self.provider}/{self.organization}/coding-standards"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        standards = response.json()["data"]
        return [s for s in standards if not s.get("isDraft", False)]

    def get_repositories_for_standard(self, standard_id: str) -> List[Dict[str, Any]]:
        """Get repositories attached to a specific coding standard"""
        url = f"{self.base_url}/organizations/{self.provider}/{self.organization}/coding-standards/{standard_id}/repositories"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["data"]

    def get_repository_issues(self, repository: str) -> Dict[str, int]:
        """Get issues for a specific repository"""
        issues_count = {"Critical": 0, "Medium": 0, "Minor": 0}
        cursor = None
        
        while True:
            url = f"{self.base_url}/analysis/organizations/{self.provider}/{self.organization}/repositories/{repository}/issues"
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            for issue in data.get("data", []):
                severity = issue.get("patternInfo", {}).get("severityLevel")
                if severity == "Error":
                    issues_count["Critical"] += 1
                elif severity == "Warning":
                    issues_count["Medium"] += 1
                elif severity == "Info":
                    issues_count["Minor"] += 1
            
            pagination = data.get("pagination", {})
            cursor = pagination.get("cursor")
            if not cursor:
                break
        
        return issues_count

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
        writer.writerow(["Coding Standard", "Repository", "Critical Issues", "Medium Issues", "Minor Issues", "Total Issues"])
        
        for standard in tqdm(standards, desc="Processing coding standards"):
            print(f"\nAnalyzing coding standard: {standard['name']}")
            repositories = api.get_repositories_for_standard(standard['id'])
            
            if not repositories:
                writer.writerow([standard['name'], "No repositories", 0, 0, 0, 0])
                continue
            
            for repo in tqdm(repositories, desc="Processing repositories", leave=False):
                try:
                    issues = api.get_repository_issues(repo['name'])
                    total_issues = sum(issues.values())
                    
                    writer.writerow([
                        standard['name'],
                        repo['name'],
                        issues['Critical'],
                        issues['Medium'],
                        issues['Minor'],
                        total_issues
                    ])
                except Exception as e:
                    print(f"Error processing repository {repo['name']}: {str(e)}")
                    writer.writerow([standard['name'], repo['name'], "Error", "Error", "Error", "Error"])
    
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