# Clean fixture: must produce zero violations

Model routing uses the placeholder {{MODEL_HIGH}} instead of a concrete name.
The credential is masked as password=*** which is a placeholder, not a leak.
A tunable is written as api_key: {{API_KEY}} so no real token appears.
Effort step max — только ручная эскалация (escalation), never a default.
Effort xhigh is a normal default and must not trip any rule on its own.
Example of an allowed reference to BKI on this line. airules:allow domain-names
