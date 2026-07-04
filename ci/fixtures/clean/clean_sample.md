# Clean fixture: must produce zero violations

Model routing uses the placeholder {{MODEL_HIGH}} instead of a concrete name.
The credential is masked as password=*** which is a placeholder, not a leak.
A tunable is written as api_key: {{API_KEY}} so no real token appears.
Reasoning level xhigh — только ручная эскалация (escalation), never a default.
Example of an allowed reference to BKI on this line. airules:allow domain-names
