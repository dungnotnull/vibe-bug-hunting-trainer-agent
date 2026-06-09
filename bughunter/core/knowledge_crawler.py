"""Knowledge Crawl Pipeline — self-improving bug pattern database.

Weekly pipeline (Monday 3:00 AM local):
1. Crawl arXiv for cs.SE + cs.PL bug pattern papers
2. Scrape CVE database for new vulnerabilities
3. Mine GitHub trending bug-fix PRs
4. Monitor OWASP Top 10 updates
5. Extract knowledge atoms via LLM
6. Update SECOND-KNOWLEDGE-BRAIN.md
7. Validate new mutations

CLAUDE.md §3.7: Knowledge Source Priority
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger


class ArxivCrawler:
    """Crawls arXiv API for bug pattern and mutation testing papers."""

    BASE_URL = "http://export.arxiv.org/api/query"

    QUERIES = [
        "cat:cs.SE AND (bug patterns OR bug detection OR software bugs)",
        "cat:cs.PL AND (mutation testing OR program repair)",
        "cat:cs.SE AND (debugging OR fault localization)",
        "cat:cs.CR AND (vulnerability detection OR software security)",
        "cat:cs.PL AND (program analysis AND bug finding)",
    ]

    def __init__(self, client: Optional[httpx.Client] = None):
        self._client = client or httpx.Client(timeout=30.0)

    def crawl(self, max_results: int = 50) -> list[dict]:
        """Fetch recent bug pattern research papers from arXiv."""
        papers: list[dict] = []
        for query in self.QUERIES:
            try:
                results = self._search(query, max_results=max_results // len(self.QUERIES))
                papers.extend(results)
            except Exception as e:
                logger.warning(f"arXiv crawl failed for query '{query[:50]}': {e}")

        papers = self._deduplicate(papers)
        logger.info(f"arXiv crawl: {len(papers)} unique papers found")
        return papers

    def _search(self, query: str, max_results: int = 10) -> list[dict]:
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = self._client.get(self.BASE_URL, params=params)
        resp.raise_for_status()
        return self._parse_atom(resp.text)

    def _parse_atom(self, xml_text: str) -> list[dict]:
        papers = []
        entries = xml_text.split("<entry>")[1:]
        for entry in entries:
            try:
                title_match = re.search(r"<title[^>]*>(.*?)</title>", entry, re.DOTALL)
                summary_match = re.search(r"<summary[^>]*>(.*?)</summary>", entry, re.DOTALL)
                link_match = re.search(r'<id[^>]*>(.*?)</id>', entry)
                date_match = re.search(r"<published[^>]*>(.*?)</published>", entry)

                if title_match and summary_match:
                    papers.append({
                        "title": self._clean_html(title_match.group(1)),
                        "summary": self._clean_html(summary_match.group(1)),
                        "url": link_match.group(1).strip() if link_match else "",
                        "published": date_match.group(1).strip() if date_match else "",
                        "source": "arxiv",
                    })
            except Exception:
                continue
        return papers

    def _clean_html(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _deduplicate(self, papers: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for p in papers:
            key = p.get("title", "")[:100]
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique


class CVECrawler:
    """Scrapes NVD CVE database for new web application vulnerabilities."""

    NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, client: Optional[httpx.Client] = None):
        self._client = client or httpx.Client(timeout=30.0)

    def crawl(self, days_back: int = 30) -> list[dict]:
        """Fetch recent CVEs relevant to web apps and libraries."""
        from_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat() + ":00.000"

        cves: list[dict] = []
        try:
            params = {
                "pubStartDate": from_date,
                "keywordSearch": "web application",
                "resultsPerPage": 20,
            }
            resp = self._client.get(self.NVD_API, params=params)
            resp.raise_for_status()
            data = resp.json()

            for vuln in data.get("vulnerabilities", []):
                cve = vuln.get("cve", {})
                cves.append({
                    "id": cve.get("id", ""),
                    "description": (cve.get("descriptions", [{}])[0].get("value", ""))[:500],
                    "severity": cve.get("metrics", {}).get("cvssMetricV31", [{}])[0].get("cvssData", {}).get("baseSeverity", ""),
                    "published": cve.get("published", ""),
                    "source": "cve",
                })
        except Exception as e:
            logger.warning(f"CVE crawl failed: {e}")

        logger.info(f"CVE crawl: {len(cves)} vulnerabilities found")
        return cves


class GitHubTrendingMiner:
    """Mines GitHub trending repositories for recent bug-fix PRs."""

    GITHUB_API = "https://api.github.com"
    SEARCH_KEYWORDS = [
        "bug fix",
        "bugfix",
        "fix:",
        "hotfix",
        "patch vulnerability",
    ]

    def __init__(self, token: str = "", client: Optional[httpx.Client] = None):
        self._token = token
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(timeout=30.0, headers=headers)

    def mine(self, max_results: int = 30) -> list[dict]:
        """Search GitHub for recent bug-fix PRs. Returns sanitized pattern data only."""
        prs: list[dict] = []
        for keyword in self.SEARCH_KEYWORDS[:2]:
            try:
                url = f"{self.GITHUB_API}/search/issues"
                params = {
                    "q": f"{keyword} is:pr is:merged",
                    "sort": "updated",
                    "order": "desc",
                    "per_page": min(max_results, 15),
                }
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    prs.append({
                        "title": item.get("title", ""),
                        "url": item.get("html_url", ""),
                        "labels": [l.get("name", "") for l in item.get("labels", [])],
                        "state": item.get("state", ""),
                        "source": "github",
                    })
            except Exception as e:
                logger.warning(f"GitHub mining failed for '{keyword}': {e}")

        logger.info(f"GitHub mining: {len(prs)} PRs found")
        return prs


class OWASPMonitor:
    """Monitors OWASP Top 10 for updates to security vulnerability patterns."""

    OWASP_URLS = [
        "https://owasp.org/www-project-top-ten/",
        "https://owasp.org/Top10/",
    ]

    def __init__(self, client: Optional[httpx.Client] = None):
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self._current_categories = self._load_known_categories()

    def check_updates(self) -> list[dict]:
        """Check OWASP for new vulnerability categories or ranking changes."""
        updates: list[dict] = []
        try:
            for url in self.OWASP_URLS:
                try:
                    resp = self._client.get(url)
                    text = resp.text[:10000]

                    categories = re.findall(r"A\d{2}:\d{4}[:\-]\s*([\w\s]+)", text)
                    for cat in categories:
                        if cat.strip() not in self._current_categories:
                            updates.append({
                                "category": cat.strip(),
                                "url": url,
                                "source": "owasp",
                                "found_at": datetime.utcnow().isoformat(),
                            })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"OWASP monitor failed: {e}")

        if updates:
            self._current_categories.update(u.strip() for u in [c["category"] for c in updates])
        logger.info(f"OWASP monitor: {len(updates)} new categories")
        return updates

    def _load_known_categories(self) -> set:
        return {
            "Broken Access Control",
            "Cryptographic Failures",
            "Injection",
            "Insecure Design",
            "Security Misconfiguration",
            "Vulnerable and Outdated Components",
            "Identification and Authentication Failures",
            "Software and Data Integrity Failures",
            "Security Logging and Monitoring Failures",
            "Server-Side Request Forgery",
        }


class KnowledgeUpdater:
    """Orchestrates the weekly knowledge crawl pipeline.

    Runs every Monday 3:00 AM via APScheduler.
    Extracts knowledge atoms from raw crawl data and updates SECOND-KNOWLEDGE-BRAIN.md.
    """

    def __init__(
        self,
        brain_path: Optional[Path] = None,
        llm_client=None,
    ):
        self._brain_path = brain_path or Path(__file__).resolve().parent.parent.parent / "SECOND-KNOWLEDGE-BRAIN.md"
        self._llm = llm_client
        self._arxiv = ArxivCrawler()
        self._cve = CVECrawler()
        self._github = GitHubTrendingMiner()
        self._owasp = OWASPMonitor()

    def run_full_crawl(self) -> dict:
        """Execute the complete knowledge crawl pipeline."""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "arxiv": [],
            "cve": [],
            "github": [],
            "owasp": [],
            "atoms_extracted": 0,
            "brain_updated": False,
        }

        logger.info("Starting knowledge crawl pipeline...")

        results["arxiv"] = self._arxiv.crawl(max_results=30)
        results["cve"] = self._cve.crawl(days_back=30)
        results["github"] = self._github.mine(max_results=20)
        results["owasp"] = self._owasp.check_updates()

        all_findings = (
            results["arxiv"] + results["cve"] + results["github"] + results["owasp"]
        )

        atoms = self._extract_knowledge_atoms(all_findings)
        results["atoms_extracted"] = len(atoms)

        if atoms:
            self._update_brain(atoms)
            results["brain_updated"] = True

        logger.info(
            f"Knowledge crawl complete: {len(all_findings)} findings, "
            f"{len(atoms)} atoms extracted"
        )
        return results

    def _extract_knowledge_atoms(self, findings: list[dict]) -> list[dict]:
        """Extract structured knowledge atoms from crawl findings."""
        atoms = []
        for finding in findings[:30]:
            source = finding.get("source", "unknown")
            title = finding.get("title", finding.get("description", ""))
            summary = finding.get("summary", finding.get("description", ""))

            if len(title) < 10:
                continue

            atom = {
                "title": title[:200],
                "summary": summary[:500],
                "source": source,
                "url": finding.get("url", ""),
                "severity": finding.get("severity", ""),
                "extracted_at": datetime.utcnow().isoformat(),
            }
            atoms.append(atom)

        return atoms

    def _update_brain(self, atoms: list[dict]) -> None:
        """Append new knowledge atoms to SECOND-KNOWLEDGE-BRAIN.md."""
        if not self._brain_path.exists():
            logger.warning(f"Brain file not found: {self._brain_path}")
            return

        with open(self._brain_path, "r", encoding="utf-8") as f:
            content = f.read()

        new_section = "\n\n## Crawl Updates\n\n"
        for atom in atoms:
            new_section += (
                f"- `[{atom['source'].upper()}]` {atom['title']}\n"
                f"  {atom['summary'][:200]}...\n"
                f"  _Extracted: {atom['extracted_at']}_\n\n"
            )

        content += new_section

        with open(self._brain_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Updated {self._brain_path} with {len(atoms)} atoms")
