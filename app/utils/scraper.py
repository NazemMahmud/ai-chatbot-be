"""
URL scraper — fetches a web page and extracts text content.
"""

import httpx
from bs4 import BeautifulSoup


async def scrape_url(url: str, timeout: float = 30.0) -> str:
    """Fetch a URL and extract text content."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-Chatbot-Scraper/1.0; "
                    "+https://github.com/yourusername/ai-chatbot)"
                )
            },
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    # Remove non-content elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()

    # Try to get main content area
    main_content = soup.find("main") or soup.find("article") or soup.find("body")
    if main_content:
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    return text
