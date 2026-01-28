# backend/tools/generate_domain.py

import os
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOMAINS_DIR = os.path.join(BASE_DIR, "domains")

SERVICE_TEMPLATE = """\
from services.ai_router import ask_ai
from services.domain_registry import register_domain

DOMAIN_NAME = "{domain_name}"
DOMAIN_META = {{
    "display_name": "{display_name}",
    "description": "{description}",
    "monetized": {monetized},
    "requires_auth": {requires_auth},
    "governance_level": "{governance_level}",
    "created_at": "{created_at}"
}}

def handler(query, user_context=None):
    \"\"\"
    Auto-generated service for {display_name}.
    Governance level: {governance_level}
    \"\"\"

    prompt = f\"\"\"
    You are a {persona}.
    
    Domain: {display_name}
    Description: {description}

    Rules:
    - Be neutral and factual
    - Avoid ideology unless explicitly requested
    - Respect cultural, legal, and ethical boundaries
    - Provide structured, high-quality insight

    User Query:
    {{query}}
    \"\"\"

    return ask_ai(
        prompt=prompt,
        domain=DOMAIN_NAME,
        context=user_context
    )

register_domain(DOMAIN_NAME, handler)
"""

INIT_TEMPLATE = """\
# Auto-generated domain package
"""

def create_domain(
    domain_name,
    display_name,
    description,
    persona,
    monetized=False,
    requires_auth=False,
    governance_level="standard"
):
    domain_path = os.path.join(DOMAINS_DIR, domain_name)

    if os.path.exists(domain_path):
        print(f"❌ Domain '{domain_name}' already exists.")
        return

    os.makedirs(domain_path)

    with open(os.path.join(domain_path, "__init__.py"), "w") as f:
        f.write(INIT_TEMPLATE)

    service_code = SERVICE_TEMPLATE.format(
        domain_name=domain_name,
        display_name=display_name,
        description=description,
        persona=persona,
        monetized=monetized,
        requires_auth=requires_auth,
        governance_level=governance_level,
        created_at=datetime.utcnow().isoformat()
    )

    with open(os.path.join(domain_path, "service.py"), "w") as f:
        f.write(service_code)

    print(f"✅ Domain '{domain_name}' created successfully.")
    print(f"   → {domain_path}/service.py")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("""
Usage:
python generate_domain.py <domain_name> <display_name> <persona> <description>

Optional flags (edit in code or extend CLI later):
- monetized
- requires_auth
- governance_level
""")
        sys.exit(1)

    domain_name = sys.argv[1]
    display_name = sys.argv[2]
    persona = sys.argv[3]
    description = sys.argv[4]

    create_domain(
        domain_name=domain_name,
        display_name=display_name,
        description=description,
        persona=persona,
        monetized=True,
        requires_auth=False,
        governance_level="standard"
    )
