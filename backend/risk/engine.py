"""Deterministic risk analysis engine for job postings."""

import re
from urllib.parse import urlparse


class RiskEngine:
    """Rule-based risk analysis engine for job postings.

    All analysis is deterministic - no LLM calls involved.
    """

    RED_FLAG_PATTERNS: list[tuple[str, int, str]] = [
        (r"(?i)wire\s+transfer", 3, "Mentions wire transfer"),
        (r"(?i)western\s+union", 3, "Mentions Western Union"),
        (r"(?i)money\s+order", 3, "Mentions money order"),
        (r"(?i)bitcoin|crypto|ethereum", 2, "Requests cryptocurrency payment"),
        (r"(?i)send\s+money\s+to", 3, "Asks to send money"),
        (r"(?i)cash\s+app|venmo|zelle", 2, "Requests payment via consumer apps"),
        (r"(?i)upfront\s+(fee|payment|cost)", 3, "Requests upfront payment"),
        (r"(?i)pay\s+to\s+(apply|start)", 3, "Pay-to-apply scam indicator"),
        (r"(?i)training\s+fee", 3, "Charging for training"),
        (r"(?i)kit\s+fee|supplies?\s+fee", 2, "Kit or supplies fee"),
        (r"(?i)guaranteed\s+(income|earnings?)", 2, "Guaranteed income claims"),
        (r"(?i)unlimited\s+(income|earnings?|potential)", 2, "Unlimited income claims"),
        (r"(?i)be\s+your\s+own\s+boss", 1, "MLM-style language"),
        (r"(?i)financial\s+freedom", 1, "MLM-style language"),
        (r"(?i)passive\s+income", 1, "Passive income claims"),
        (r"(?i)act\s+now|limited\s+time|expires?\s+soon", 2, "Urgency language"),
        (r"(?i)don'?t\s+miss\s+(this|out)|last\s+chance", 2, "Urgency language"),
        (r"(?i)immediate(ly)?\s+start", 1, "Pressure to start immediately"),
        (r"(?i)opportunity\s+of\s+a\s+lifetime", 2, "Hyperbolic language"),
        (r"(?i)change\s+your\s+life\s+forever", 2, "Hyperbolic language"),
        (r"(?i)whatsapp|telegram|signal", 2, "Redirects to messaging apps"),
        (r"(?i)text\s+me\s+at|message\s+me\s+on", 1, "Informal contact channel"),
        (r"(?i)mystery\s+shopper", 3, "Known scam type"),
        (r"(?i)personal\s+assistant|executive\s+assistant", 1, "Common fake job title"),
        (r"(?i)payment\s+processing\s+agent", 3, "Fake payment agent scam"),
        (r"(?i)reshipping|reship\s+per?", 3, "Reshipping scam"),
        (r"(?i)ssn|social\s+security|tax\s+id", 3, "Requests sensitive ID"),
        (r"(?i)bank\s+(account|routing)|account\s+number", 3, "Requests banking details"),
        (r"(?i)credit\s+card|debit\s+card", 3, "Requests card details"),
        (r"(?i)copy\s+of\s+(driver|your)\s+license", 2, "Requests government ID"),
        (r"(?i)background\s+check\s+fee", 2, "Charging for background check"),
        (r"(?i)verify\s+identity\s+by\s+sending", 2, "Fake identity verification"),
        (r"(?i)\$\d{2,3},?\d{3}\s*(/\s*year|annual|per\s+year)", 0, "High salary reference"),
        (r"(?i)no\s+experience\s+needed.*\$\d{3,}", 2, "No experience with high pay"),
        (r"(?i)earn\s+\$?\d{3,}.*per\s+(day|week|hour)", 1, "Specific earnings claim"),
        (r"(?i)free\s+(laptop|computer|phone|equipment)", 1, "Free equipment offers"),
        (r"(?i)we\s+supply|we\s+provide\s+everything", 1, "Overly generous claims"),
    ]

    SUSPICIOUS_TLDS: frozenset[str] = frozenset({
        ".xyz", ".top", ".buzz", ".club", ".work", ".click",
        ".loan", ".racing", ".date", ".faith", ".review",
        ".accountant", ".science", ".gdn", ".win", ".cricket",
        ".party", ".stream", ".download", ".racing", ".webcam",
        ".tk", ".ml", ".ga", ".cf", ".gq", ".pw", ".cc",
    })

    TRUSTED_DOMAINS: frozenset[str] = frozenset({
        "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
        "monster.com", "careerbuilder.com", "simplyhired.com",
        "github.com", "stackoverflow.com", "lever.co", "greenhouse.io",
        "workday.com", "ashbyhq.com", "jobs.lever.co", "boards.greenhouse.io",
        "bamboohr.com", "smartrecruiters.com", "icims.com", "taleo.net",
    })

    def analyze(self, job: dict) -> dict:
        """Analyze a job posting for risk factors.

        Args:
            job: Job posting dictionary with keys like title, description,
                 company, url, salary, experience.

        Returns:
            Dictionary with risk_score (0-100), risk_level, risk_flags,
            and recommendation.
        """
        flags: list[dict] = []

        url = job.get("url", "")
        company = job.get("company", "")
        description = job.get("description", "")
        salary = job.get("salary", "")
        title = job.get("title", "")
        experience = job.get("experience", "")

        flags.extend(self._check_domain_suspicion(url))
        flags.extend(self._check_company_identity(company, url))
        flags.extend(self._check_payment_requests(description))
        flags.extend(self._check_unrealistic_compensation(salary, title, experience))
        flags.extend(self._check_vague_description(description))
        flags.extend(self._check_suspicious_contact(description))
        flags.extend(self._check_repeated_content(description))
        flags.extend(self._check_information_requests(description))
        flags.extend(self._check_urgency_language(description))
        flags.extend(self._check_title_credibility(title, description))

        severity_sum = sum(f["severity"] for f in flags)
        raw_score = min(severity_sum * 5, 100)
        risk_score = max(0, min(raw_score, 100))
        risk_level = self.classify(risk_score)
        recommendation = self.recommend(risk_score, flags)

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_flags": flags,
            "recommendation": recommendation,
        }

    def _check_domain_suspicion(self, url: str) -> list[dict]:
        """Check URL domain for suspicious indicators.

        Examines TLD, checks against trusted domains list,
        and looks for suspicious URL patterns.
        """
        flags: list[dict] = []
        if not url:
            return flags

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
        except (ValueError, AttributeError):
            flags.append({
                "check": "domain_suspicion",
                "severity": 3,
                "reason": "Malformed URL",
            })
            return flags

        hostname_lower = hostname.lower()

        for trusted in self.TRUSTED_DOMAINS:
            if hostname_lower == trusted or hostname_lower.endswith("." + trusted):
                return flags

        for tld in self.SUSPICIOUS_TLDS:
            if hostname_lower.endswith(tld):
                flags.append({
                    "check": "domain_suspicion",
                    "severity": 2,
                    "reason": f"Suspicious TLD: {tld}",
                })
                break

        ip_pattern = re.compile(
            r"^(\d{1,3}\.){3}\d{1,3}$"
        )
        if ip_pattern.match(hostname_lower):
            flags.append({
                "check": "domain_suspicion",
                "severity": 3,
                "reason": "Domain is an IP address",
            })

        if hostname_lower.count("-") > 3:
            flags.append({
                "check": "domain_suspicion",
                "severity": 1,
                "reason": "Excessive hyphens in domain",
            })

        if len(hostname_lower) > 50:
            flags.append({
                "check": "domain_suspicion",
                "severity": 1,
                "reason": "Unusually long domain name",
            })

        return flags

    def _check_company_identity(self, company: str, url: str) -> list[dict]:
        """Check company name against known company data.

        Flags missing company names and mismatches between
        company name and URL domain.
        """
        flags: list[dict] = []
        if not company or company.strip() == "":
            flags.append({
                "check": "company_identity",
                "severity": 2,
                "reason": "No company name provided",
            })
            return flags

        if not url:
            return flags

        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
        except (ValueError, AttributeError):
            return flags

        company_words = re.findall(r"[a-z]+", company.lower())
        domain_words = re.findall(r"[a-z]+", hostname.split(".")[0])

        if company_words and domain_words:
            overlap = set(company_words) & set(domain_words)
            shared_title_words = {
                "inc", "llc", "ltd", "corp", "co", "com", "the", "group",
                "solutions", "partners", "enterprises", "services",
            }
            overlap -= shared_title_words
            domain_words_set = set(domain_words) - shared_title_words

            if not overlap and company_words and domain_words_set:
                flags.append({
                    "check": "company_identity",
                    "severity": 1,
                    "reason": "Company name and URL domain show no overlap",
                })

        return flags

    def _check_payment_requests(self, description: str) -> list[dict]:
        """Check if job description requests money or payments."""
        flags: list[dict] = []
        if not description:
            return flags

        for pattern, severity, reason in self.RED_FLAG_PATTERNS:
            if re.search(pattern, description) and severity >= 3:
                flags.append({
                    "check": "payment_requests",
                    "severity": severity,
                    "reason": reason,
                })

        return flags

    def _check_unrealistic_compensation(
        self, salary: str, title: str, experience: str
    ) -> list[dict]:
        """Check for compensation that seems too good to be true."""
        flags: list[dict] = []
        if not salary:
            return flags

        numbers = re.findall(r"\$?([\d,]+(?:\.\d+)?)", salary)
        if not numbers:
            return flags

        max_val = 0.0
        for num_str in numbers:
            try:
                val = float(num_str.replace(",", ""))
                if val > max_val:
                    max_val = val
            except ValueError:
                continue

        if max_val <= 0:
            return flags

        title_lower = title.lower()
        is_entry_level = any(
            kw in title_lower
            for kw in [
                "junior", "entry", "associate", "intern",
                "trainee", "assistant", "helper", "assistant",
            ]
        )

        exp_lower = experience.lower()
        is_no_exp = any(
            kw in exp_lower
            for kw in ["no experience", "none", "0 year", "0+ year"]
        )

        if is_entry_level or is_no_exp:
            if max_val > 150000:
                flags.append({
                    "check": "unrealistic_compensation",
                    "severity": 2,
                    "reason": f"${max_val:,.0f} salary offered for entry-level role",
                })
            elif max_val > 100000:
                flags.append({
                    "check": "unrealistic_compensation",
                    "severity": 1,
                    "reason": f"High salary ${max_val:,.0f} for role requiring no experience",
                })

        if "executive" in title_lower and "assistant" in title_lower:
            if max_val > 80000:
                flags.append({
                    "check": "unrealistic_compensation",
                    "severity": 1,
                    "reason": "Unusually high pay for assistant-level position",
                })

        return flags

    def _check_vague_description(self, description: str) -> list[dict]:
        """Check if description is too short or generic."""
        flags: list[dict] = []
        if not description:
            flags.append({
                "check": "vague_description",
                "severity": 2,
                "reason": "No job description provided",
            })
            return flags

        word_count = len(description.split())
        if word_count < 20:
            flags.append({
                "check": "vague_description",
                "severity": 2,
                "reason": f"Very short description ({word_count} words)",
            })
        elif word_count < 50:
            flags.append({
                "check": "vague_description",
                "severity": 1,
                "reason": f"Brief description ({word_count} words)",
            })

        generic_phrases = [
            "exciting opportunity",
            "dynamic team",
            "fast-paced environment",
            "self-motivated",
            "self-starter",
            "wear many hats",
            "no two days are the same",
            "work hard play hard",
        ]
        generic_count = sum(
            1 for phrase in generic_phrases
            if phrase in description.lower()
        )
        if generic_count >= 3:
            flags.append({
                "check": "vague_description",
                "severity": 1,
                "reason": f"Highly generic language ({generic_count} cliches found)",
            })

        return flags

    def _check_suspicious_contact(self, description: str) -> list[dict]:
        """Check for redirections to messaging apps or informal channels."""
        flags: list[dict] = []
        if not description:
            return flags

        for pattern, severity, reason in self.RED_FLAG_PATTERNS:
            if pattern in [
                r"(?i)whatsapp|telegram|signal",
                r"(?i)text\s+me\s+at|message\s+me\s+on",
            ]:
                if re.search(pattern, description):
                    flags.append({
                        "check": "suspicious_contact",
                        "severity": severity,
                        "reason": reason,
                    })

        return flags

    def _check_repeated_content(self, description: str) -> list[dict]:
        """Check for repeated or duplicated phrases in description."""
        flags: list[dict] = []
        if not description:
            return flags

        sentences = [
            s.strip().lower()
            for s in re.split(r"[.!?\n]", description)
            if len(s.strip()) > 15
        ]

        if len(sentences) < 2:
            return flags

        from collections import Counter
        sentence_counts = Counter(sentences)

        repeated = [
            (sent, count)
            for sent, count in sentence_counts.items()
            if count >= 3
        ]
        if repeated:
            flags.append({
                "check": "repeated_content",
                "severity": 2,
                "reason": f"Content repeated {repeated[0][1]} times: '{repeated[0][0][:60]}...'",
            })

        phrase_pattern = re.compile(r"\b(\w+(?:\s+\w+){5,10})\b", re.IGNORECASE)
        phrases = phrase_pattern.findall(description)
        if phrases:
            phrase_counts = Counter(p.lower() for p in phrases)
            repeated_phrases = [
                (p, c)
                for p, c in phrase_counts.items()
                if c >= 3
            ]
            if repeated_phrases:
                flags.append({
                    "check": "repeated_content",
                    "severity": 1,
                    "reason": f"Phrase repeated {repeated_phrases[0][1]} times",
                })

        return flags

    def _check_information_requests(self, description: str) -> list[dict]:
        """Check if the job requests sensitive personal information."""
        flags: list[dict] = []
        if not description:
            return flags

        sensitive_checks = [
            (r"(?i)ssn|social\s+security\s+number", "SSN"),
            (r"(?i)bank\s+account|routing\s+number", "bank account details"),
            (r"(?i)credit\s+card|debit\s+card\s+number", "card details"),
            (r"(?i)driver'?s?\s+license\s+number", "driver's license"),
            (r"(?i)passport\s+number", "passport"),
            (r"(?i)pin\s+code|pin\s+number", "PIN"),
            (r"(?i)upload\s+.*(id|passport|license|ssn)", "identity documents"),
            (r"(?i)send\s+.*(photo|picture)\s+of\s+.*(id|license|passport)", "ID photos"),
        ]

        for pattern, label in sensitive_checks:
            if re.search(pattern, description):
                flags.append({
                    "check": "information_requests",
                    "severity": 3,
                    "reason": f"Requests sensitive info: {label}",
                })

        return flags

    def _check_urgency_language(self, description: str) -> list[dict]:
        """Check for high-pressure urgency language."""
        flags: list[dict] = []
        if not description:
            return flags

        urgency_count = 0
        for pattern, severity, reason in self.RED_FLAG_PATTERNS:
            if pattern in [
                r"(?i)act\s+now|limited\s+time|expires?\s+soon",
                r"(?i)don'?t\s+miss\s+(this|out)|last\s+chance",
                r"(?i)immediate(ly)?\s+start",
            ]:
                if re.search(pattern, description):
                    urgency_count += 1

        if urgency_count >= 2:
            flags.append({
                "check": "urgency_language",
                "severity": 2,
                "reason": f"Multiple urgency phrases ({urgency_count} found)",
            })
        elif urgency_count == 1:
            flags.append({
                "check": "urgency_language",
                "severity": 1,
                "reason": "Contains urgency language",
            })

        return flags

    def _check_title_credibility(self, title: str, description: str) -> list[dict]:
        """Check if job title matches known scam patterns."""
        flags: list[dict] = []
        if not title:
            flags.append({
                "check": "title_credibility",
                "severity": 1,
                "reason": "No job title provided",
            })
            return flags

        title_lower = title.lower()

        scam_titles = [
            (r"(?i)mystery\s+shopper", "Mystery shopper (known scam)"),
            (r"(?i)payment\s+processing\s+agent", "Payment processing agent scam"),
            (r"(?i)reshipping?\s+agent", "Reshipping agent scam"),
            (r"(?i)package\s+handler\s+agent", "Package handler scam"),
            (r"(?i)financial\s+representative\s+agent", "Fake financial agent"),
            (r"(?i)money\s+transfer\s+agent", "Money transfer scam"),
            (r"(?i)remote\s+data\s+entry\s+clerk", "Common fake job title"),
            (r"(?i)work\s+from\s+home\s+specialist", "Vague remote work scam"),
        ]

        for pattern, reason in scam_titles:
            if re.search(pattern, title_lower):
                flags.append({
                    "check": "title_credibility",
                    "severity": 3,
                    "reason": reason,
                })
                break

        return flags

    def classify(self, score: int) -> str:
        """Classify a risk score into a level.

        Args:
            score: Risk score from 0 to 100.

        Returns:
            Risk level string: LOW, MEDIUM, or HIGH.
        """
        if score <= 30:
            return "LOW"
        elif score <= 60:
            return "MEDIUM"
        else:
            return "HIGH"

    def recommend(self, score: int, flags: list[dict]) -> str:
        """Generate a recommendation based on score and flags.

        Args:
            score: Risk score from 0 to 100.
            flags: List of risk flag dictionaries.

        Returns:
            Recommendation string: APPROVE, REVIEW, or BLOCK.
        """
        high_severity_flags = [
            f for f in flags
            if f.get("severity", 0) >= 3
        ]

        if score >= 60 or len(high_severity_flags) >= 2:
            return "BLOCK"
        elif score >= 30 or len(high_severity_flags) >= 1:
            return "REVIEW"
        else:
            return "APPROVE"
