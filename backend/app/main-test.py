import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.renderer import render_analysis


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="ReverseEngineer-SDLC Renderer Test",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RendererTestRequest(BaseModel):
    provider: str
    model: str
    api_key: str


DUMMY_RAW_ANALYSIS = """
I'll perform the Business Purpose phase by first loading the relevant skill, then analyzing the repository.
{"phase": "business-purpose", "documentation": "# NetworkPro - Business Purpose Analysis\n\n## Executive Summary\n\nNetworkPro is a career development and professional networking application that enables individuals to leverage their LinkedIn profile data to receive personalized recommendations for career growth, professional networking expansion, and skill development.\n\n---\n\n## 1. Real-World Problem Addressed\n\nThe software addresses the challenge faced by professionals who want to advance their careers but lack a systematic, data-driven approach to understanding their market position, identifying growth opportunities, and building strategic professional networks.\n\nThe core problem is threefold:\n\n1. **Career Positioning Uncertainty**: Professionals struggle to understand how their skills and experience compare to market demands and what roles they should target.\n\n2. **Networking Blind Spots**: Individuals find it difficult to identify the most relevant professionals to connect with for career advancement, often relying on random or reactive networking strategies.\n\n3. **Skill Development Misalignment**: Professionals invest time learning skills that may not be strategically valuable for their career goals, lacking personalized guidance based on current market trends and their specific profile.\n\n**Evidence**: README.md (`README.md:1-12`) explicitly states the application is \"a career and networking app that analyzes LinkedIn profile data to provide personalized AI-powered recommendations for career growth, networking, and skill development.\"\n\n---\n\n## 2. Apparent Users and Consumers\n\nThe repository indicates the following user personas:\n\n| User Type | Evidence | Description |\n|-----------|----------|-------------|\n| **Job Seekers** | API endpoints for job recommendations (`/api/recommendations/jobs`) | Professionals actively seeking new employment opportunities |\n| **Career Advancers** | Career goals functionality (`/api/career-goals`) | Individuals aiming for promotions or role transitions |\n| **Skill Developers** | Skills recommendations and learning resources | Professionals wanting to acquire new competencies |\n| **Network Builders** | Networking recommendations (`/api/recommendations/networking`) | Users seeking to expand their professional connections |\n\n**Evidence**: The application maintains user-specific data stores for profiles (`profiles` table), interests (`interests` table), career goals (`career_goals` table), and saved items (`saved_items` table) in `shared/schema.ts:5-52`.\n\nThe current implementation uses a single hardcoded user ID (1) for all operations, suggesting single-user mode or early-stage development without multi-user authentication (`server/routes.ts:526,556,574,614,644,700,730,754,791`).\n\n---\n\n## 3. Core Workflow Enabled\n\nThe application guides users through a four-stage career development workflow:\n\n### Stage 1: Profile Upload and Analysis\n\n**Entry Point**: Home page (`client/src/pages/HomeTab.tsx:215-216`) with file uploader component\n\n**Process**:\n- User uploads their LinkedIn profile as a PDF\n- Backend receives file via `/api/profile/upload` endpoint (`server/routes.ts:513-550`)\n- PDF text is extracted using the `pdf-parse` library (`package.json:63`)\n- Profile data is parsed using regex patterns for name, headline, location, industry, company, job title, skills, education, and experience (`server/routes.ts:359-442`)\n- Profile is stored in PostgreSQL database\n\n**Outcome**: Structured professional profile extracted and saved\n\n### Stage 2: Interest and Goal Setting\n\n**Entry Point**: Interests tab (`client/src/pages/InterestsTab.tsx`)\n\n**Process**:\n- System suggests topics and skills based on profile analysis (`/api/interests/suggestions`)\n- User selects and saves career interests (`/api/interests`)\n- User defines career goals including desired role, industry, location, and salary range (`/api/career-goals`)\n\n**Evidence**: Schema defines `interests` table with `topics` and `skills` arrays, and `career_goals` table with `desiredRole`, `industry`, `location`, and `salaryRange` fields (`shared/schema.ts:24-52`).\n\n**Outcome**: Personalized career context established\n\n### Stage 3: Networking Recommendations\n\n**Entry Point**: Networking tab (`client/src/pages/NetworkingTab.tsx`)\n\n**Process**:\n- Backend generates mock recommendations for professionals to follow (`generatePeopleToFollow`) and connect with (`generatePeopleToConnect`)\n- Trending industry posts are surfaced (`generateTrendingPosts`)\n- User can save professionals or posts to their profile\n\n**Evidence**: Recommendation generation functions in `server/routes.ts:22-306` return hardcoded mock data including professional profiles, connection reasons, and post content.\n\n**Outcome**: Actionable networking opportunities presented\n\n### Stage 4: Job and Learning Opportunities\n\n**Entry Point**: Jobs tab (`client/src/pages/JobsTab.tsx`)\n\n**Process**:\n- Job openings are recommended based on user profile and goals (`generateJobOpenings`)\n- Relevant courses and learning resources are suggested (`generateCourses`)\n- Skills to develop are highlighted with market value indicators (`generateSkills`)\n\n**Evidence**: API endpoint `/api/recommendations/jobs` in `server/routes.ts:679-695` returns job listings, courses, and skill recommendations.\n\n**Outcome**: Personalized opportunity pipeline for career advancement\n\n---\n\n## 4. Domain Model Analysis\n\nThe core domain entities and their relationships reveal the problem space:\n\n```\n┌─────────────┐     ┌──────────────┐     ┌───────────────┐\n│   Profile   │────>│   Interests  │     │  CareerGoals  │\n├─────────────┤     ├──────────────┤     ├───────────────┤\n│ name        │     │ topics[]     │     │ desiredRole   │\n│ headline    │     │ skills[]      │     │ industry      │\n│ location    │     └──────────────┘     │ location      │\n│ industry    │                          │ salaryRange   │\n│ currentJob  │     ┌──────────────┐     └───────────────┘\n│ experience  │     │  SavedItems  │\n│ education   │     ├──────────────┤\n│ skills[]    │     │ itemType     │\n│ certifications│    │ itemId       │\n└─────────────┘     │ itemData     │\n                    └──────────────┘\n```\n\n**Evidence**: All entity definitions in `shared/schema.ts:5-52`.\n\n### Key Domain Concepts\n\n| Concept | Definition | Evidence |\n|---------|------------|----------|\n| **Profile** | Professional identity comprising work history, education, skills | `shared/schema.ts:5-22` |\n| **Interests** | Career-related topics and skill preferences | `shared/schema.ts:24-31` |\n| **Career Goals** | Target professional outcomes | `shared/schema.ts:43-52` |\n| **Saved Items** | Bookmarked networking/content opportunities | `shared/schema.ts:33-41` |\n| **Recommendations** | AI-suggested professional connections, jobs, courses | `server/routes.ts:22-306` |\n\n---\n\n## 5. Implementation Verification\n\n### Documentation vs. Implementation Alignment\n\n| Stated Feature | Implementation Status | Evidence |\n|---------------|---------------------|----------|\n| LinkedIn Profile PDF Analysis | **Implemented** (mock extraction) | `server/routes.ts:308-356, 513-550` |\n| Smart Recommendations | **Implemented** (mock data) | `server/routes.ts:22-306` |\n| Career Interest Mapping | **Implemented** | `server/routes.ts:592-609` |\n| Interactive Dashboard | **Implemented** | UI components in `client/src/pages/*` |\n| Dark/Light Mode | **Implemented** | `theme.json`, `client/src/lib/theme-provider.tsx` |\n\n### Discrepancies Identified\n\n1. **Mock Data Mode**: All recommendation functions (`generatePeopleToFollow`, `generateJobOpenings`, `generateCourses`, `generateSkills`) return hardcoded mock data rather than AI-generated or algorithmically matched results (`server/routes.ts:22-306`).\n\n2. **Single-User Hardcoding**: All API endpoints hardcode `userId = 1` instead of extracting user identity from authentication (`server/routes.ts:526,556,574,614,644,700,730,754,791`).\n\n3. **PDF Parsing Limitations**: The `extractTextFromPdf` function returns a static mock LinkedIn profile rather than actually parsing uploaded PDFs (`server/routes.ts:309-356`).\n\n4. **Profile Extraction Simplification**: The `extractProfileFromText` function uses basic regex matching that would not reliably parse real-world LinkedIn PDFs (`server/routes.ts:359-442`).\n\n---\n\n## 6. Supporting Evidence Summary\n\n### Explicit Documentation\n\n- **README.md** (`README.md:1-71`): States application is a \"career and networking app that analyzes LinkedIn profile data to provide personalized AI-powered recommendations\"\n\n### Technical Implementation\n\n- **Package Manifest** (`package.json`): Reveals technology choices consistent with a full-stack web application (React, TypeScript, Express, PostgreSQL, Drizzle ORM, PDF parsing libraries)\n\n- **API Routes** (`server/routes.ts`): 804 lines of Express route handlers implementing profile management, interest tracking, networking recommendations, and job matching\n\n- **Database Schema** (`shared/schema.ts`): Defines five tables (users, profiles, interests, career_goals, saved_items) that model the career development domain\n\n- **Client Pages** (`client/src/pages/*.tsx`): Four-tab interface (Home, Interests, Networking, Jobs) implementing the documented workflow\n\n---\n\n## 7. Unknowns and Limitations\n\nThe repository does not provide sufficient evidence to determine:\n\n| Unknown | Limitation | Rationale |\n|---------|------------|-----------|\n| **Target Deployment Environment** | Not determinable | While Vercel deployment is mentioned, the Express server setup suggests self-hosted or Replit deployment as well |\n| **Authentication Strategy** | Not fully implemented | Schema includes `users` table, but no authentication endpoints exist; all operations use hardcoded userId |\n| **Real AI/ML Integration** | Not implemented | Recommendations use mock data; no actual machine learning or AI API integration |\n| **Multi-Tenancy Support** | Unknown | Single-user mode prevents understanding of multi-user architecture |\n| **External Service Integrations** | Not visible | No LinkedIn API, job board API, or course provider API integrations found in code |\n| **Business Model** | Not stated | No monetization features, subscription tiers, or paid premium capabilities observed |\n\n---\n\n## 8. Business Purpose Statement\n\n**NetworkPro exists to help individual professionals advance their careers by providing a unified platform that ingests their LinkedIn profile data, establishes their career interests and goals, recommends relevant professionals to network with, and surfaces personalized job opportunities and skill development resources.**\n\nThe application serves a clearly identified user need: the desire to make strategic, data-informed career decisions rather than relying on intuition or limited professional networks. The workflow—from profile upload through interest setting to networking and job exploration—mirrors established career development methodologies.\n\nThe implementation demonstrates this purpose through:\n\n- A four-stage guided workflow that users follow sequentially\n- Persistent storage of user profile, interests, and goals\n- Recommendation systems for networking and job opportunities\n- A bookmarking mechanism for saving interesting content\n\n**Calibrated Confidence**: This conclusion is strongly supported by documentation (`README.md`) and confirmed by implementation evidence (API endpoints, database schema, UI pages). The stated \"AI-powered\" capabilities are not genuinely AI-driven in the current implementation, as all recommendations are generated from mock data rather than algorithmic analysis.\n\n---\n\n## 9. Key Repository Artifacts Referenced\n\n| Artifact | Path | Purpose |\n|----------|------|---------|\n| README | `README.md` | Explicit product description |\n| Package Manifest | `package.json` | Technology stack confirmation |\n| Database Schema | `shared/schema.ts` | Domain entity definitions |\n| API Routes | `server/routes.ts` | Backend behavior implementation |\n| App Component | `client/src/App.tsx` | UI navigation structure |\n| Home Tab | `client/src/pages/HomeTab.tsx` | Profile upload and analysis UI |\n| Interests Tab | `client/src/pages/InterestsTab.tsx` | Interest selection UI |\n| Networking Tab | `client/src/pages/NetworkingTab.tsx` | Networking recommendations UI |\n| Jobs Tab | `client/src/pages/JobsTab.tsx` | Job and learning opportunities UI |\n| Theme Configuration | `theme.json` | Visual customization |\n"}""".strip()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "renderer-test",
    }


@app.post("/api/render-test")
def render_test(request: RendererTestRequest):
    try:
        logger.info(
            "Renderer test requested: provider=%s model=%s key_present=%s",
            request.provider,
            request.model,
            bool(request.api_key and request.api_key.strip()),
        )

        rendered = render_analysis(
            phase="business-purpose",
            analysis=DUMMY_RAW_ANALYSIS,
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            timeout=300,
        )

        return {
            "success": True,
            "phase": "business-purpose",
            "raw_analysis": rendered,
        }

    except ValueError as exc:
        logger.exception("Renderer validation failed")

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        logger.exception("Renderer test failed")

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )