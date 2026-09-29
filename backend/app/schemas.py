from pydantic import BaseModel, HttpUrl


class AnalyzeRequest(BaseModel):
    company_name: str
    query: str = ""
    provider: str = "openrouter"
    model: str = "openrouter/free"
    api_key: str = ""
    selected_phases: list[str] | None = None
    work_id: str | None = None
    mode: str = "parallel"
    objective: str = "document"


class AnalyzeResponse(BaseModel):
    repo_url: str
    business_purpose: str
    business_requirements: str
    features: str
    software_requirements: str
    technology_architecture: str
    design_pattern: str
    high_level_design: str
    low_level_design: str
    implementation_detail: str
    testing_harness: str
    future_directions: str
