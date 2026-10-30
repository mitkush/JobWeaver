# JobWeaver - Domain Glossary

Capitalised terms in the PRD, ADRs, code and UI mean exactly what this file says. The UI uses the same words (UX rule: one name per concept).

## User

A person with a JobWeaver account, signed in with Google (ADR-0015). The unit of tenancy: every user-owned record carries `user_id` (ADR-0001). There is no organization or workspace layer. One User has the **Admin** role (the founder), who can see Source Status and the Credit Budget.

## Fact Bank

Everything a User has said about themselves, taken from the documents they uploaded: resume, detailed portfolio or cover letter, short summary. Stored as reviewable **Facts** (a skill, a project, an experience bullet, a metric, a link). The Fact Bank is the **only** allowed source of content for a Tailored Resume, Cover Letter or Application Email (ADR-0005). Nothing outside it may appear in a Draft.

## Base Resume

The User's own resume as uploaded. The reference that the Tailored Resume's diff is shown against.

## Preferences

What a User wants: target titles and keywords, locations (India cities, other countries and cities), and work modes (onsite, hybrid, remote). Preferences decide which Jobs enter the User's Feed and shape the queries sent to paid Sources. Keywords marked **Core** are must-have skills: every Job in the Feed must have a job description that names one, title matches without a description wait under Needs review, and differently titled Jobs whose description names enough keywords enter the Feed's keyword section (FR-A3 AC4).

Location selection is optional: Global means no country/city restriction, including India. India and other-country selections can optionally name cities. Work mode is independent of job location: remote means WFH, hybrid means some days in the office, and onsite means office. A remote advert can still have a listed location ("India (Remote)"): it is the office location, shown on the card and matched by country only, since the city does not matter to someone working from home. Onsite and hybrid Jobs must match the chosen city too.

## Source

One external provider of job data, reached through one **Source Adapter**: LinkedIn via Bright Data, Naukri via Apify, Greenhouse, Lever, JSearch, Remotive, Hacker News "Who is hiring", and so on. Each Source has a priority (1 = highest) used only to choose the Primary Posting of a Job.

## Source Adapter

The module that fetches from one Source and converts its raw data into Postings. All adapters implement the same interface and register themselves; nothing else in the codebase knows which Sources exist (ADR-0003). Each adapter has one of two modes: **Windowed** (returns new Postings for a query and time window; cannot see jobs close) or **Snapshot** (returns every open job on one ATS Board; compared with stored Postings to detect new and closed jobs).

## Fetch Run

One scheduled or manual execution of one Source Adapter. Records its window (since/until), result (healthy, degraded, failed), Postings found and credits spent. A failed Fetch Run never stops the other Sources (ADR-0003).

## Backfill

The first Fetch Run of a windowed Source, or for a new set of Preferences: the last 14 days. Not capped; its cost shows in the Credit Budget (ADR-0009).

## Source Status

The current health of each Source: **Healthy**, **Degraded** (last run failed or hit a limit; will retry next run) or **Disabled** (turned off by the Admin). Visible to the Admin on Sources, including failure reasons and recent Fetch Runs. Source health notices are kept off the Feed; the Feed shows when it was last updated.

## Standby

A second provider for the same jobs as a Source (LinkedIn through Apify for LinkedIn through Bright Data; SerpApi for JSearch). It runs only while that Source is Degraded or Disabled, and it shares the Source's search windows so nothing is paid for twice (ADR-0016).

## Credit Budget

The monthly allowance of a paid-by-credits Source (Bright Data: 5,000 credits, 1 credit = 1 record). Sources billed from one account share one Credit Budget (Naukri and LinkedIn through Apify: $5). Shared by all Users, never used to silently cut results, and tracked per query with a month-end projection (ADR-0009).

## Company

A normalised employer identity ("Google LLC", "Google India Pvt Ltd" and "Google" resolve to one Company). Used for duplicate detection and the "Already applied to this Company" warning.

## ATS Board

A Company's public job board on an applicant tracking system, identified by ATS type plus slug (e.g. `greenhouse:stripe`). Discovered from apply URLs of Postings found on other Sources, or added by hand (ADR-0013).

## Posting

One job advert as seen on one Source: title, Company, description, locations, work mode, apply URL, contact email (if any), posted date, Source-specific ID. Postings are shared data with no owner (ADR-0002).

## Job

The real-world opening that one or more Postings describe. A Job has exactly one **Primary Posting** (from the highest-priority Source) and merged fields from all its Postings, so information found only on a lower-priority Posting (e.g. a contact email) is never lost (ADR-0004). One Job may list several locations.

## Match Pair

A claim that two Postings describe the same Job, with a confidence band: **Exact**, **High**, **Medium** or **Low** (ADR-0004). Exact and High pairs group automatically. Medium pairs become a **Possible Duplicate**. Low pairs are ignored.

## Possible Duplicate

A Medium Match Pair shown to the User with two actions: **Confirm** (same Job) or **Not the same Job**.

## Rejected Pair

Two Postings someone marked "Not the same Job", or split out of a group. Stored permanently and never proposed again.

## Correspondence

The stack of all Postings that make up one Job, across every Source, and the screen that shows it. The User can open any Posting in the stack, whatever its priority. Feed cards summarise the Correspondence as **"Available on"** badges.

## Feed

A User's personal list of Jobs that match their Preferences, in two sections: **With email** and **Apply link only**. Title matches and keyword matches are shown apart. A Feed entry is a link between the User and a shared Job (`user_jobs`), never a copy of it (ADR-0002).

## Saved Job

A Job the User bookmarked to come back to. Kept on their link to the Job, so it survives Preferences changes, merges, hiding and expiry until they remove it. Not a Draft or an Application: saving prepares or sends nothing.

## Viewed

A Job whose page the User has opened at least once. Recorded on their link to the Job; a card shown in the Feed does not count.

## Skill Gap

Required skills in a Job's description that are not in the User's Fact Bank, shown on the card as "Missing: Kubernetes, Go". Required skills are extracted from the description by AI once per Job; the comparison is plain code (ADR-0010). There is no match score.

## Expired Job

A Job that is no longer open: its company board (snapshot Source) no longer lists it, or it has no snapshot Posting and its newest Posting is older than the age limit (default 30 days), or its apply link was found closed. Hidden from the Feed; kept for Applications that reference it.

## Draft

The application package a User prepares for one Job: a **Tailored Resume** (PDF), a **Cover Letter**, and, when the Job has a contact email, an **Application Email**. A User has one active Draft per Job; an archived Draft keeps its history. Drafts are saved in versions, each with the job context it was made from, and are never sent by JobWeaver (ADR-0006).

## Replacement

A new resume, cover letter or resume section prepared in the background from one version of a Draft. It changes nothing until the User accepts it, and Undo after accepting restores the version before it (ADR-0017).

## Tailored Resume

A resume built for one Job by selecting, rewriting, reordering and emphasising Facts from the Fact Bank to match the Job's description and ATS keywords. It may include Facts that are in the portfolio but not in the Base Resume; it may never include anything that is not in the Fact Bank (ADR-0005).

## Tailoring Trace

The link from every line of a Tailored Resume, Cover Letter or Application Email back to the Fact(s) it came from. Makes the no-fabrication rule checkable by code and visible to the User.

## Draft Chat

The AI chat panel on the right of the Draft screen. The User asks for changes in plain language ("shorter summary", "lead with the Rails work"); the change is applied to the Draft as a new version, under the same Fact Bank rule.

## Gmail Hand-off

Creating a real draft in the User's Gmail, with the Tailored Resume attached, from a Draft. The User reviews, formats and sends it inside Gmail (ADR-0006). The fallback is a Gmail compose link with the PDF attached by hand.

## Application

A User's record of applying to a Job, one per User and Job, with a status: **Drafted -> Applied -> Replied -> Interview -> Offer** or **Rejected**. Every status change is kept with its time. Updated by the User; JobWeaver does not read Gmail replies.

## Application Extension

The JobWeaver browser extension (FR-E14). It fills an employer's application form from the User's application profile, Saved Answers and a saved Draft version, and attaches its PDFs; the User reviews and submits (ADR-0017). It never submits or applies on its own.

## Saved Answer

An answer the User gave to a form question (notice period, salary, work authorisation, or any answer they chose to keep), reused by the Application Extension when the same question appears again within its scope: general, the same country (and currency for salary), or the same Company. Sensitive questions are only ever filled from Saved Answers.

## Page Description

A job description read from the Job's own careers page through the Application Extension, kept on one User's link to the Job and used for that User's Drafts instead of the Source's text. Each Draft version records the description it was made from. It never changes the shared Job (ADR-0002, ADR-0017).

## Writing Style

How a User writes, taken only from text they wrote themselves (summary, cover letters, answers they edited): sentence length, formality, phrasing and spelling, with a few short excerpts whose names, numbers, dates and technologies are redacted. Used to make Application Extension Suggestions read like the User. It holds no facts about the User; the Fact Bank stays the only source of content (ADR-0005).

## Captured Job

A Job saved from a page the User opened, through the Application Extension, rather than fetched by a Source. Stored as a Posting from the push-only `captured` Source and linked to the capturing User by a link that Feed rebuilds keep (ADR-0017).

## Follow-up Reminder

An in-app reminder when an Application has stayed **Applied** for N days (default 7, set per User), with a one-click follow-up email placed in Gmail Drafts. A reminder only; nothing is sent.

## AI Gateway

The single module through which every AI call passes, with typed task methods, provider fallback for text tasks (Gemini -> Groq -> OpenRouter), Gemini-only versioned embeddings that queue when unavailable (ADR-0014), usage accounting and a recorded mode for tests (ADR-0007).
