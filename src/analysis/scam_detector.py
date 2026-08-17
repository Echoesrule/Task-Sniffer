"""Scam/Risk Detector - identifies suspicious job listings."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ScamRiskDetector:
    """Detect potentially scammy or high-risk job listings."""

    RED_FLAG_PATTERNS: list[tuple[str, float, str]] = [
        (r"earn\s+\$?\d+[\s,]*(?:per|a)\s+(?:day|week|hour)", 80, "Unrealistic earnings promise"),
        (r"no\s+experience\s+required.*?(\$?\d{2,}k?\+?)", 60, "High pay with no experience"),
        (r"work\s+from\s+home.*?(\$?\d{3,}k?\s*(?:per|a)\s*(?:day|week))", 70, "Too-good-to-be-true WFH pay"),
        (r"send\s+(?:money|payment|fee|deposit|investment)", 95, "Asks for upfront payment"),
        (r"pay\s+(?:a\s+)?(?:fee|deposit|training|starter\s+kit)", 95, "Requires fee/deposit"),
        (r"wire\s+transfer|western\s+union|money\s+gram", 90, "Suspicious payment method"),
        (r"crypto(?:currency)?\s*(?:invest|send|transfer|wallet)", 85, "Crypto-related financial request"),
        (r"mlm|multi[\s-]*level|pyramid|recruit.*?team", 80, "MLM/pyramid scheme indicators"),
        (r"guaranteed\s+(?:income|earnings|returns|money)", 75, "Guaranteed income claim"),
        (r"click\s+here\s+to\s+(?:apply|start|earn|join)", 50, "Generic clickbait phrasing"),
        (r"(?:social\s+security|ssn|national\s+id)\s*(?:number|num|no\.?)", 85, "Asks for SSN/national ID"),
        (r"bank\s+(?:account|details|info).*?(?:password|pin|login)", 95, "Asks for banking credentials"),
        (r"whatsapp|telegram|signal.*?(?:group|chat|channel).*?(?:join|link)", 40, "Redirects to messaging apps"),
        (r"(?:crypto|bitcoin|eth).*?(?:wallet|address|seed\s+phrase)", 90, "Asks for crypto wallet info"),
        (r"vacancy\s*:\s*.*?@", 30, "Spam-style email formatting"),
    ]

    TRUSTED_DOMAINS = {
        "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
        "indeed.com", "linkedin.com", "glassdoor.com",
        "jobicy.com", "adplist.org",
    }

    SUSPICIOUS_TITLE_KEYWORDS = [
        "mystery shopper", "data entry specialist", "payment processor",
        "financial agent", "invoice processor", "refund specialist",
        "cash manager", "currency exchange",
    ]

    def analyze(self, job: dict[str, Any]) -> dict[str, Any]:
        """Analyze a job for scam risk. Returns risk assessment."""
        flags = []
        risk_score = 0

        text = f"{job.get('title', '')} {job.get('description', '')} {job.get('company', '')}"
        url = job.get("url", "")

        pattern_flags = self._check_patterns(text)
        flags.extend(pattern_flags)

        url_flags = self._check_url(url)
        flags.extend(url_flags)

        title_flags = self._check_title(job.get("title", ""))
        flags.extend(title_flags)

        desc_flags = self._check_description(job.get("description", ""))
        flags.extend(desc_flags)

        company_flags = self._check_company(job.get("company", ""))
        flags.extend(company_flags)

        if flags:
            risk_score = min(100, sum(f["severity"] for f in flags) // max(1, len(flags)))

        return {
            "risk_score": risk_score,
            "risk_level": self._classify_risk(risk_score),
            "flags": flags,
            "is_suspicious": risk_score >= 60,
        }

    def _check_patterns(self, text: str) -> list[dict]:
        flags = []
        text_lower = text.lower()
        for pattern, severity, reason in self.RED_FLAG_PATTERNS:
            if re.search(pattern, text_lower):
                flags.append({"severity": severity, "reason": reason, "category": "pattern"})
        return flags

    def _check_url(self, url: str) -> list[dict]:
        flags = []
        if not url:
            flags.append({"severity": 40, "reason": "No URL provided", "category": "url"})
            return flags

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            if not any(td in domain for td in self.TRUSTED_DOMAINS):
                suspicious_tlds = [".xyz", ".top", ".buzz", ".click", ".link", ".fun"]
                if any(domain.endswith(tld) for tld in suspicious_tlds):
                    flags.append({"severity": 50, "reason": f"Suspicious TLD: {domain}", "category": "url"})

                if re.search(r"\d{4,}", domain):
                    flags.append({"severity": 30, "reason": "Domain contains many digits", "category": "url"})
        except Exception:
            pass

        return flags

    def _check_title(self, title: str) -> list[dict]:
        flags = []
        title_lower = title.lower()

        for keyword in self.SUSPICIOUS_TITLE_KEYWORDS:
            if keyword in title_lower:
                flags.append({"severity": 60, "reason": f"Suspicious title keyword: {keyword}", "category": "title"})
                break

        if title_lower.count("$") > 0 or re.search(r"\$\d{3,}k?", title_lower):
            if any(phrase in title_lower for phrase in ["earn", "make", "get paid", "income"]):
                flags.append({"severity": 50, "reason": "Title emphasizes money/earnings", "category": "title"})

        return flags

    def _check_description(self, desc: str) -> list[dict]:
        flags = []
        if not desc:
            flags.append({"severity": 20, "reason": "Empty job description", "category": "description"})
            return flags

        desc_lower = desc.lower()

        word_count = len(desc.split())
        if word_count < 20:
            flags.append({"severity": 30, "reason": "Very short description", "category": "description"})

        urgency_phrases = ["act now", "limited time", "hurry", "dont miss", "last chance", "urgently needed"]
        for phrase in urgency_phrases:
            if phrase in desc_lower:
                flags.append({"severity": 40, "reason": f"Urgency language: '{phrase}'", "category": "description"})
                break

        vague_phrases = ["flexible hours", "unlimited earning potential", "be your own boss",
                         "no boss", "no manager", "work on your own terms"]
        for phrase in vague_phrases:
            if phrase in desc_lower:
                flags.append({"severity": 35, "reason": f"Vague promises: '{phrase}'", "category": "description"})
                break

        contact_outside = re.search(
            r"(?:email|call|text|whatsapp|telegram)\s+(?:at\s+)?[\w@.]+\s+for\s+(?:more|details|info)",
            desc_lower,
        )
        if contact_outside:
            flags.append({"severity": 45, "reason": "Contact outside platform detected", "category": "description"})

        return flags

    def _check_company(self, company: str) -> list[dict]:
        flags = []
        if company == "Unknown" or not company.strip():
            flags.append({"severity": 25, "reason": "Unknown company name", "category": "company"})
        return flags

    def _classify_risk(self, score: float) -> str:
        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 40:
            return "medium"
        elif score >= 20:
            return "low"
        else:
            return "minimal"
