"""
Amazon Bestseller Cover Search
===============================
Searches Amazon for current bestsellers in a book niche and extracts
cover image URLs. Uses Playwright headless browser to handle Amazon's
JavaScript-heavy pages and avoid scraping blocks.

Usage:
    results = await search_bestseller_covers("large print word search")
    for r in results:
        print(r.title, r.cover_image_url)
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BestsellerCover:
    """A single Amazon bestseller cover result."""
    title: str
    asin: str
    cover_image_url: str          # High-res cover
    price: Optional[float] = None
    reviews: Optional[int] = None
    rating: Optional[float] = None


def _upgrade_image_url(url: str, size: int = 1500) -> str:
    """
    Upgrade an Amazon image URL to high resolution.
    Amazon image URLs contain size codes like _SL300_, _SX300_, _SY300_, etc.
    Replace with the requested size for a higher resolution version.
    """
    # Replace any size indicator with the requested size
    upgraded = re.sub(r'\._[A-Z]{2}\d+_', f'._SL{size}_', url)
    if upgraded == url:
        # If no size indicator found, try appending before extension
        upgraded = re.sub(r'\.(_[^.]*)?\.jpg', f'._SL{size}_.jpg', url)
    return upgraded


async def search_bestseller_covers(
    keyword: str,
    max_results: int = 5,
) -> list[BestsellerCover]:
    """
    Search Amazon for bestselling book covers using Playwright.

    Launches a headless Chromium browser, navigates to Amazon search
    for the given keyword in the Books department, and extracts
    product data from the search results.

    Args:
        keyword: Search term (e.g., "large print word search puzzle books")
        max_results: Maximum number of results to return (default 5)

    Returns:
        List of BestsellerCover objects with title, ASIN, cover image URL,
        price, reviews, and rating.
    """
    from playwright.async_api import async_playwright

    search_url = f"https://www.amazon.com/s?k={quote_plus(keyword)}&i=stripbooks"
    results: list[BestsellerCover] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()

            # Navigate to Amazon search
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for search results to load
            try:
                await page.wait_for_selector(
                    '[data-component-type="s-search-result"]',
                    timeout=15000,
                )
            except Exception:
                logger.warning("Search results selector not found, trying fallback")
                await page.wait_for_timeout(3000)

            # Extract product cards
            cards = await page.query_selector_all(
                '[data-component-type="s-search-result"]'
            )

            for card in cards[:max_results * 2]:  # Fetch extra in case some fail
                if len(results) >= max_results:
                    break

                try:
                    result = await _extract_product_card(card)
                    if result and result.asin and result.cover_image_url:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"Failed to extract product card: {e}")
                    continue

            await browser.close()

    except Exception as e:
        logger.error(f"Amazon search failed: {e}")
        raise RuntimeError(f"Amazon search failed: {e}")

    return results


async def _extract_product_card(card) -> Optional[BestsellerCover]:
    """Extract product data from a single Amazon search result card."""
    # ASIN from data-asin attribute
    asin = await card.get_attribute("data-asin")
    if not asin or len(asin) != 10:
        return None

    # Title from h2 > a > span
    title = ""
    title_el = await card.query_selector("h2 a span")
    if title_el:
        title = (await title_el.text_content() or "").strip()
    if not title:
        return None

    # Cover image URL from .s-image
    cover_url = ""
    img_el = await card.query_selector("img.s-image")
    if img_el:
        cover_url = await img_el.get_attribute("src") or ""
    if not cover_url or "m.media-amazon.com" not in cover_url:
        return None

    # Upgrade to high-res
    cover_url = _upgrade_image_url(cover_url, 1500)

    # Price
    price = None
    price_el = await card.query_selector(".a-price .a-offscreen")
    if price_el:
        price_text = (await price_el.text_content() or "").strip()
        try:
            price = float(price_text.replace("$", "").replace(",", ""))
        except ValueError:
            pass

    # Review count
    reviews = None
    reviews_el = await card.query_selector(
        'span[aria-label*="stars"] + span a span, '
        '.a-size-base.s-underline-text'
    )
    if reviews_el:
        reviews_text = (await reviews_el.text_content() or "").strip()
        reviews_text = reviews_text.replace(",", "").replace("(", "").replace(")", "")
        try:
            reviews = int(reviews_text)
        except ValueError:
            pass

    # Rating
    rating = None
    rating_el = await card.query_selector('span[aria-label*="out of 5 stars"]')
    if rating_el:
        rating_label = await rating_el.get_attribute("aria-label") or ""
        match = re.search(r'([\d.]+)\s+out of', rating_label)
        if match:
            try:
                rating = float(match.group(1))
            except ValueError:
                pass

    return BestsellerCover(
        title=title,
        asin=asin,
        cover_image_url=cover_url,
        price=price,
        reviews=reviews,
        rating=rating,
    )


async def fetch_cover_image(image_url: str) -> bytes:
    """
    Download a cover image from Amazon's CDN.

    Args:
        image_url: Full URL to the cover image on Amazon's CDN

    Returns:
        Raw image bytes (JPEG)

    Raises:
        RuntimeError: If download fails
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(image_url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise RuntimeError(f"Failed to download cover image: {e}")
