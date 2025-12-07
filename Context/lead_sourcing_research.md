# Lead Sourcing Research: YouTube for EulaIQ

**Objective:** Efficiently source high-quality leads (Math/Physics/Chemistry YouTube creators) for EulaIQ's animation services.

## 1. The "Scrapetube" Strategy
`scrapetube` is a lightweight Python library that scrapes the YouTube frontend. It is excellent for **discovery** (finding channels) but **cannot** directly extract emails (which are protected by CAPTCHAs).

### Proposed Procedure
This workflow uses `scrapetube` for the heavy lifting of finding candidates, followed by a targeted manual or semi-automated step for contact info.

#### **Phase 1: Discovery (Automated)**
1.  **Define Keywords:** Generate a list of search terms based on the ICP.
    *   *Examples:* "Physics explainer", "Calculus tutorial", "Chemistry concepts", "3Blue1Brown style", "Math animation".
2.  **Run Scrapetube Search:**
    *   Use `scrapetube.get_search(query)` to fetch video results for each keyword.
    *   Extract `ownerId` (Channel ID) and `ownerText` (Channel Name) from the results.
3.  **Deduplicate & Filter:**
    *   Remove duplicate Channel IDs.
    *   *Optional:* Filter by "upload date" (check if they posted recently) to ensure the channel is active.

#### **Phase 2: Qualification (Manual/Fast)**
1.  **Generate Links:** Construct the "About" page URL for each channel: `https://www.youtube.com/channel/<ChannelID>/about`.
2.  **Quick Review:** Open these links (can batch open 10-20 at a time).
    *   Check Subscriber Count (fit ICP range?).
    *   Check Content Style (is it relevant?).

#### **Phase 3: Contact Extraction (The "Human" Step)**
*   **Challenge:** YouTube hides emails behind a "View Email Address" button and a reCAPTCHA. `scrapetube` cannot bypass this.
*   **Action:**
    *   **Option A (Manual):** While reviewing the channel, click "View Email Address", solve captcha, and copy email.
    *   **Option B (Description Search):** Many creators put their email in the *text* of their "About" description or video descriptions. You can programmatically search the description text for email patterns (e.g., `regex for email`) which `scrapetube` *can* retrieve if it grabs video details.

---

## 2. Tool Comparison

| Feature | **Scrapetube** | **YouTube Data API** | **Selenium / Puppeteer** | **Paid Tools (e.g., Apify)** |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Use** | Scraping video lists, search results. | Official data access, analytics. | Browser automation, complex interactions. | Full-service lead gen. |
| **Cost** | Free (Open Source). | Free (up to quota), then Paid. | Free (Open Source). | Paid ($$$). |
| **Speed** | Fast (HTTP requests). | Very Fast. | Slow (Loads full browser). | Fast. |
| **Get Emails?** | **No** (unless in text description). | **No** (Private field). | **Yes** (can click buttons), but brittle & slow. | **Yes** (often have databases). |
| **Risk** | Medium (YouTube can rate limit IP). | Low (Official). | High (Easy to detect/block). | Low (Managed by vendor). |
| **Technical Difficulty** | Low (Python script). | Medium (OAuth, Quotas). | High (DOM handling, Captchas). | Low (UI based). |

## 3. Recommendation
**Use `scrapetube` for building the "Hit List".**
It is the best free tool to quickly generate a list of 100-500 potential channels without API quotas.

**Workflow:**
1.  Write a Python script using `scrapetube` to search keywords and save a CSV of `Channel Name`, `Channel URL`, and `Latest Video Title`.
2.  Manually process the top candidates to find emails (highest accuracy, lowest ban risk).
