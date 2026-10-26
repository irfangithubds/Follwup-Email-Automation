import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import httpx
from bs4 import BeautifulSoup

# In-memory cache to ensure speed and prevent redundant web queries
_RESEARCH_CACHE: Dict[str, Dict[str, Any]] = {}

# Curated benchmark knowledge for key solutions (Ensaan Partner Ecosystem)
CURATED_SOLUTION_UPDATES = {
    "cornerstone": {
        "name": "Cornerstone OnDemand (Cornerstone Learn)",
        "headline": "Cornerstone Workforce AI™ & Galaxy Platform Release",
        "update_summary": "Cornerstone has launched its new Workforce AI intelligence platform and next-gen Galaxy suite, introducing AI-driven skill mapping, personalized learner paths, and automated compliance tracking.",
        "enterprise_benefit": "Specifically designed to help rapidly expanding project teams automate role-based competency tracking and certification renewals without administrative overhead."
    },
    "entomo": {
        "name": "entomo (Skills Assessment & Development)",
        "headline": "entomo Autonomous AI Competency & Skills Matrix",
        "update_summary": "entomo's latest platform release introduces predictive skills benchmarking, autonomous role-gap analytics, and adaptive learning tracks.",
        "enterprise_benefit": "Directly links workforce performance metrics with targeted development actions, accelerating employee readiness and operational time-to-proficiency."
    },
    "kredo": {
        "name": "Kredo (AI Microlearning & Frontline Enablement)",
        "headline": "Kredo GenAI Microlearning Suite & Multilingual Mobile Delivery",
        "update_summary": "Kredo's new generative AI engine allows enterprises to convert complex technical SOPs and manuals into bite-sized 3-minute interactive mobile learning bursts in both English and Arabic.",
        "enterprise_benefit": "Drives over 90% voluntary completion rates for frontline and field engineering teams who need on-the-go enablement without classroom downtime."
    },
    "empuls": {
        "name": "Empuls by Xoxoday",
        "headline": "Empuls AI Pulse Analytics & Automated Milestone Recognition",
        "update_summary": "Empuls has rolled out predictive employee engagement analytics and seamless digital peer-to-peer recognition workflows.",
        "enterprise_benefit": "Enhances cross-departmental culture alignment, employee retention, and transparent reward fulfillment across distributed organizations."
    }
}

# Known enterprise domain and subject mappings in KSA
COMPANY_ALIASES = {
    "albawani": "AlBawani Holding",
    "saudia": "Saudia Airlines",
    "ncgr": "National Center for Government Resources Systems (NCGR)",
    "salam": "Salam Telecom",
    "alrajhi": "Al Rajhi Takaful",
    "xoxoday": "Xoxoday",
    "entomo": "entomo",
    "cornerstone": "Cornerstone OnDemand"
}

def detect_company_and_solution(
    subject: str,
    body: str,
    to_address: str,
    recipient_name: str,
    thread_trail: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    """Detect prospect company name and the solution/partner being discussed."""
    combined_text = f"{subject} {to_address} {recipient_name} {body}".lower()
    if thread_trail:
        for t in thread_trail:
            combined_text += f" {t.get('sender', '')} {t.get('snippet', '')} {t.get('body', '')}".lower()

    # 1. Detect Company
    detected_company = ""
    if "albawani" in combined_text:
        detected_company = "AlBawani"
    elif "saudia" in combined_text or "@saudia.com" in to_address.lower():
        detected_company = "Saudia Airlines"
    elif "ncgr" in combined_text:
        detected_company = "NCGR (National Center for Government Resources)"
    elif "salam" in combined_text:
        detected_company = "Salam Telecom"
    elif "alrajhi" in combined_text or "takaful" in combined_text:
        detected_company = "Al Rajhi Takaful"
    else:
        # Check domain from to_address
        domain_match = re.search(r'@([a-zA-Z0-9.-]+)', to_address)
        if domain_match:
            dom = domain_match.group(1).lower()
            if not any(ign in dom for ign in ["gmail", "yahoo", "outlook", "hotmail", "ensaantech", "squareone"]):
                clean_dom = dom.split('.')[0].capitalize()
                detected_company = clean_dom

    # 2. Detect Solution Partner
    detected_solution_key = ""
    if any(k in combined_text for k in ["cornerstone", "learn demo", "talentlms", "lms features", "lms evaluation"]):
        detected_solution_key = "cornerstone"
    elif "entomo" in combined_text or "skills assessment" in combined_text:
        detected_solution_key = "entomo"
    elif "kredo" in combined_text or "microlearning" in combined_text:
        detected_solution_key = "kredo"
    elif any(k in combined_text for k in ["empuls", "xoxoday", "tawasul"]):
        detected_solution_key = "empuls"
    else:
        # Default based on company context if known
        if detected_company == "AlBawani":
            detected_solution_key = "cornerstone"
        elif detected_company in ["NCGR", "Saudia Airlines"]:
            detected_solution_key = "entomo"
        else:
            detected_solution_key = "cornerstone"

    return {
        "company": detected_company or "your organization",
        "solution_key": detected_solution_key or "cornerstone"
    }

def clean_news_headline(title: str) -> str:
    """Strip media outlet names from Google News RSS titles."""
    if not title:
        return ""
    # Google news titles often end with ' - Outlet Name'
    parts = title.rsplit(" - ", 1)
    if len(parts) > 1 and len(parts[0]) > 20:
        return parts[0].strip()
    return title.strip()

def search_company_news_live(company_name: str, max_results: int = 2) -> List[Dict[str, str]]:
    """Scrape fresh verified news headlines regarding the prospect company."""
    if not company_name or company_name == "your organization":
        return []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    query = f"{company_name} Saudi Arabia news"
    encoded_q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"

    results = []
    try:
        with httpx.Client(timeout=4.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:max_results]:
                    raw_title = item.find("title").text if item.find("title") is not None else ""
                    clean_t = clean_news_headline(raw_title)
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    if clean_t:
                        results.append({
                            "title": clean_t,
                            "date": pub_date
                        })
    except Exception as e:
        print(f"Company news scrape notice for {company_name}: {e}")

    return results

def get_research_intelligence(
    subject: str,
    body: str,
    to_address: str,
    recipient_name: str,
    thread_trail: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Main research intelligence pipeline:
    1. Identifies prospect company & solution.
    2. Scrapes fresh live news for the company.
    3. Retrieves solution innovation updates.
    4. Synthesizes a tailored, executive contextual paragraph for the follow-up email.
    """
    cache_key = f"{to_address}::{subject}"
    if cache_key in _RESEARCH_CACHE:
        return _RESEARCH_CACHE[cache_key]

    meta = detect_company_and_solution(subject, body, to_address, recipient_name, thread_trail)
    company = meta["company"]
    solution_key = meta["solution_key"]

    solution_info = CURATED_SOLUTION_UPDATES.get(solution_key, CURATED_SOLUTION_UPDATES["cornerstone"])
    solution_name = solution_info["name"]

    # 1. Scrape live company news
    news_items = search_company_news_live(company, max_results=2)
    top_news = news_items[0]["title"] if news_items else ""

    # 2. Build synthesis hook tailored to the specific company & solution
    if company == "AlBawani":
        if top_news:
            news_hook = f"I've also been closely following AlBawani's remarkable momentum across the Kingdom—particularly regarding recent major infrastructure and museum project awards."
        else:
            news_hook = "I've also been following AlBawani's strategic expansion across landmark infrastructure projects across the Kingdom."
        
        solution_hook = (
            f"In tandem, as project teams and workforce requirements scale, Cornerstone has recently introduced its "
            f"Workforce AI capabilities, designed specifically to help multi-project organizations automate role-based competency tracking, "
            f"safety certifications, and compliance renewals seamlessly across dispersed sites."
        )

    elif company == "Saudia Airlines":
        news_hook = (
            "With Saudia continuing to advance its fleet expansion and guest experience milestones under Saudi Vision 2030, "
            "workforce readiness remains a critical strategic priority."
        )
        solution_hook = (
            f"In line with this, entomo's latest autonomous AI skills platform now features automated competency mapping "
            f"and personalized frontline learning pathways to accelerate time-to-proficiency."
        )

    elif company.startswith("NCGR"):
        news_hook = (
            "As NCGR continues to spearhead digital platform governance and centralized government resource enablement across the Kingdom,"
        )
        solution_hook = (
            f"entomo has updated its predictive skills intelligence framework to support large-scale public sector capability "
            f"matrices and national workforce development roadmaps."
        )

    elif company == "Salam Telecom":
        news_hook = (
            "Following Salam Telecom's recent strides in digital enterprise services and telecom infrastructure,"
        )
        solution_hook = (
            f"our latest platform updates introduce automated engagement analytics and streamlined license allocation "
            f"to maximize employee platform adoption."
        )

    else:
        # Dynamic generic synthesis
        if top_news:
            news_hook = f"On a related note, I noted {company}'s recent announcement regarding \"{top_news}\"—congratulations on the continued progress."
        else:
            news_hook = f"As {company} continues to advance its key strategic initiatives this year,"
        
        solution_hook = (
            f"we've recently rolled out new product capabilities in {solution_name}—specifically around "
            f"{solution_info['update_summary'].lower()}"
        )

    combined_hook = f"{news_hook}\n\n{solution_hook}"

    data = {
        "company": company,
        "solution_key": solution_key,
        "solution_name": solution_name,
        "top_news": top_news,
        "solution_headline": solution_info["headline"],
        "solution_summary": solution_info["update_summary"],
        "combined_hook": combined_hook
    }

    _RESEARCH_CACHE[cache_key] = data
    return data
