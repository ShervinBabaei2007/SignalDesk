"""Seed the database with realistic demo articles and default feeds.

Runs automatically on first startup when the database is empty, so the
dashboard always has something interesting to show — no network required.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import extract_keywords
from .ingestion import add_missing_default_feeds, ingest_all
from .models import Article, Feed

SEED_ARTICLES = [
    # --- Technology ---------------------------------------------------------
    ("AI Chipmaker Hits Record Quarterly Revenue on Surging Data Center Demand",
     "TechDaily", "Technology", 0.72, "-2d",
     "Shares rallied after the company reported quarterly revenue up 48% year over "
     "year, driven by unprecedented demand for its AI accelerators. Analysts called "
     "the results a breakthrough quarter and raised price targets across the board."),
    ("Open Source Robot Framework Wins Prestigious Innovation Award",
     "TechDaily", "Technology", 0.65, "-1d",
     "A community-maintained robotics framework took home this year's innovation "
     "award, beating well-funded commercial rivals. Maintainers say the win proves "
     "open collaboration can outpace proprietary development."),
    ("Major Cloud Provider Suffers Extended Outage, Thousands of Apps Offline",
     "InfraWatch", "Technology", -0.78, "-5h",
     "A configuration error in the network layer took down a core region for more "
     "than four hours. Customers reported failed deployments and mounting losses as "
     "status pages stayed quiet through the crisis."),
    ("Startup Launches Quantum Compiler That Cuts Error Rates in Half",
     "QuantumWire", "Technology", 0.58, "-3d",
     "The startup says its compiler can automatically optimize quantum circuits, "
     "halving error rates in early benchmarks. Independent researchers confirmed "
     "the improvement and called the advance significant for the field."),
    ("Hackers Breach Software Supply Chain, Security Teams Warn of Fallout",
     "CyberBrief", "Technology", -0.82, "-8h",
     "Attackers injected malicious code into a widely used build tool, affecting "
     "hundreds of downstream projects. Investigators warn the breach may take "
     "weeks to fully contain as teams audit their dependencies."),
    ("Browser Makers Agree on Unified Extension Standard",
     "TechDaily", "Technology", 0.35, "-12h",
     "After years of fragmentation, major browser vendors published a joint draft "
     "for a unified web extension API. Developers reacted with cautious optimism, "
     "noting it should finally end duplicate work across platforms."),

    # --- Business -----------------------------------------------------------
    ("Central Bank Holds Interest Rates Steady as Inflation Cools",
     "MarketDesk", "Business", 0.28, "-6h",
     "Policymakers voted unanimously to keep rates unchanged, citing a steady "
     "decline in core inflation. Economists say the improvement clears the path "
     "for cuts later this year if the trend holds."),
    ("Retail Giant Announces Record Holiday Season, Boosts Full-Year Forecast",
     "MarketDesk", "Business", 0.66, "-1d",
     "Strong online growth helped the retailer beat expectations and raise its "
     "full-year guidance. Executives credited an improved logistics network and "
     "successful expansion into new markets."),
    ("Airline Faces Lawsuit Over Canceled Flights and Refund Delays",
     "ConsumerPost", "Business", -0.62, "-2d",
     "Regulators filed a lawsuit alleging the airline systematically delayed "
     "refunds for canceled flights. Consumer groups welcomed the investigation, "
     "while the company called the criticism unfair."),
    ("Merger Creates Largest Renewable Energy Provider in the Region",
     "MarketDesk", "Business", 0.44, "-4d",
     "Two leading utilities completed their merger, creating the region's largest "
     "clean energy provider. Investors reacted positively, though regulators "
     "promised close scrutiny of electricity pricing."),
    ("Chip Shortage Eases as Auto Production Recovers",
     "InfraWatch", "Business", 0.31, "-3d",
     "Automakers reported a strong recovery in output as semiconductor supply "
     "improved. Factory utilization climbed back to pre-crisis levels and several "
     "plants canceled planned shutdowns."),
    ("Retail Chain Announces 12,000 Layoffs Amid Weak Sales",
     "ConsumerPost", "Business", -0.74, "-18h",
     "The company said restructuring would cut roughly 12,000 jobs after a sharp "
     "decline in foot traffic. Analysts warned the move signals deeper trouble "
     "for brick-and-mortar retail."),

    # --- Science ------------------------------------------------------------
    ("Astronomers Discover Earth-Like Exoplanet in Nearby Star System",
     "SciScope", "Science", 0.71, "-1d",
     "Using a new telescope survey, scientists confirmed an Earth-sized planet "
     "orbiting within the habitable zone of a nearby star. Researchers say the "
     "discovery is a milestone for atmospheric follow-up studies."),
    ("Study Links Urban Tree Cover to Significant Drop in Heat Deaths",
     "SciScope", "Science", 0.52, "-2d",
     "A decade-long study across 40 cities found neighborhoods with mature tree "
     "cover saw heat-related deaths fall by up to 30%. The authors urge city "
     "planners to treat canopy expansion as critical health infrastructure."),
    ("Coral Restoration Project Reports Strongest Recovery Since Monitoring Began",
     "SciScope", "Science", 0.63, "-5d",
     "Transplanted coral colonies survived a full bleaching season, with growth "
     "rates exceeding expectations. Marine biologists call the success a strong "
     "argument for scaling restoration programs."),
    ("Glacier Melting Accelerates Faster Than Models Predicted, Study Warns",
     "SciScope", "Science", -0.66, "-3d",
     "Satellite measurements show ice loss running roughly 20% ahead of the "
     "worst-case projections. Researchers warn coastal cities should update "
     "flood risk plans immediately."),

    # --- Politics -----------------------------------------------------------
    ("Parliament Passes Landmark Data Privacy Law With Broad Support",
     "PolicyDaily", "Politics", 0.38, "-1d",
     "The bill passed with an unusually broad coalition, creating a national "
     "data protection authority. Privacy groups called the vote a win for "
     "consumers; business associations asked for a longer transition period."),
    ("Court Rules Against Government in Landmark Surveillance Case",
     "PolicyDaily", "Politics", -0.30, "-4d",
     "The court found the bulk collection program violated privacy protections, "
     "ordering its records deleted. Civil liberties groups celebrated the ruling "
     "while officials warned of operational risks."),
    ("Voters Approve Public Transit Expansion in Decisive Referendum",
     "CityPulse", "Politics", 0.55, "-2d",
     "The measure passed with 63% support, funding two new metro lines and "
     "dozens of bus corridors. Planners say construction could begin within "
     "two years."),

    # --- Health -------------------------------------------------------------
    ("Clinical Trial Shows New Drug Cuts Recovery Time From Severe Infections",
     "MedToday", "Health", 0.68, "-1d",
     "A phase three trial found patients recovered on average two days faster "
     "with the new therapy and suffered fewer complications. Investigators "
     "describe the results as a meaningful advance for critical care."),
    ("Hospital Networks Launch Shared Cyber Defense Center After Attacks",
     "MedToday", "Health", -0.20, "-6h",
     "Following a wave of ransomware attacks, twelve hospital networks created "
     "a shared security operations center. Officials say the partnership should "
     "improve threat detection across the sector."),
    ("FDA Approves First At-Home Test for Early Kidney Disease Detection",
     "MedToday", "Health", 0.47, "-3d",
     "Regulators cleared an at-home test that flags early markers of chronic "
     "kidney disease. Health advocates say the approval should improve early "
     "diagnosis for millions of at-risk patients."),

    # --- Neutral / mixed signals ---------------------------------------------
    ("Chipmakers Report Quarterly Results Largely in Line With Expectations",
     "MarketDesk", "Business", -0.05, "-9h",
     "The three largest chipmakers posted quarterly figures within analyst "
     "estimates, with guidance unchanged for the next quarter. Shares moved "
     "little in after-hours trading as investors awaited the earnings calls."),
    ("Transit Authority Announces Schedule Adjustments Starting Next Month",
     "CityPulse", "Politics", 0.06, "-14h",
     "The authority said several bus routes will shift departure times to match "
     "updated ridership data. Officials noted the changes follow the standard "
     "quarterly review process."),
    ("Company Confirms Leadership Transition Already Announced Last Quarter",
     "TechDaily", "Technology", 0.02, "-20h",
     "The board formalized the previously disclosed leadership transition, with "
     "the incoming chief taking office at the start of the next fiscal year. "
     "Spokespeople declined further comment."),

    # --- World --------------------------------------------------------------
    ("Ceasefire Holds for a Full Week as Aid Convoys Expand",
     "GlobalWire", "World", 0.40, "-10h",
     "Mediators reported the ceasefire held for a seventh consecutive day while "
     "relief convoys doubled their deliveries. Negotiators described the "
     "improvement as fragile but meaningful."),
    ("Historic Floods Prompt Massive Evacuation Effort Along River Delta",
     "GlobalWire", "World", -0.80, "-4h",
     "Record rainfall forced more than 100,000 residents from their homes as "
     "levees failed across the delta. Emergency teams warn that shortages of "
     "clean water raise disease risks in crowded shelters."),
    ("Earthquake Response Praised as Death Toll Stays Low",
     "GlobalWire", "World", 0.33, "-2d",
     "Strict building codes and rapid response kept casualties remarkably low "
     "after a strong earthquake near a major city. Engineers credit tighter "
     "inspection rules introduced a decade ago."),
]


def backfill_keywords(db: Session) -> int:
    """One-time migration: compute keywords for articles ingested before the
    keywords column existed. Idempotent — only touches rows with no keywords."""
    rows = db.execute(
        select(Article).where((Article.keywords.is_(None)) | (Article.keywords == ""))
    ).scalars().all()
    for article in rows:
        article.keywords = ", ".join(extract_keywords(f"{article.title}. {article.summary or ''}"))
    if rows:
        db.commit()
    return len(rows)


def seed_if_empty(db: Session, live: bool = True) -> int:
    """Populate the database on first boot.

    Prefers real articles: creates the default feeds and runs a live
    ingestion so every article has a genuine external URL. Falls back to
    built-in sample articles only when the network is unavailable.
    """
    if db.scalar(select(func.count()).select_from(Article)):
        return 0

    if not db.scalar(select(func.count()).select_from(Feed)):
        add_missing_default_feeds(db)

    if live:
        try:
            feeds = [{"name": f.name, "url": f.url}
                     for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()]
            results = ingest_all(db, feeds)
            added = sum(r["added"] for r in results)
            if added >= 3:
                return added
        except Exception:  # noqa: BLE001 — offline first boot is expected sometimes
            pass

    for number, (title, source, topic, sentiment, age, summary) in enumerate(SEED_ARTICLES, start=1):
        db.add(Article(
            title=title,
            url=f"https://demo.signaldesk.local/{number}",
            source=source,
            summary=summary,
            keywords=", ".join(extract_keywords(f"{title}. {summary}")),
            topic=topic,
            sentiment=sentiment,
            published_at=_relative_published(age),
            is_seed=True,
        ))
    db.commit()
    return len(SEED_ARTICLES)


def _relative_published(age: str) -> datetime:
    """Convert '-2d' / '-5h' style markers into real UTC timestamps."""
    if not age.startswith("-"):
        return datetime.now(timezone.utc)
    unit, amount = age[-1], int(age[:-1])
    delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount),
             "m": timedelta(minutes=amount)}[unit]
    return datetime.now(timezone.utc) - delta
