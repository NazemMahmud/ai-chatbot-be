"""
Text-to-SQL service — converts natural language questions to SQL queries.

Part of Group C (Database Query APIs). Loaded on demand only when
ENABLE_DB_CONNECTOR=true.
"""

import httpx

from app.config import settings


class Text2SQLService:
    async def generate_sql(self, question: str, schema: dict, db_type: str) -> str:
        """Convert natural language question to SQL query."""
        prompt = self._build_prompt(question, schema, db_type)

        if settings.SQL_PROVIDER == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.SQL_MODEL_NAME,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                return self._extract_sql(response.json()["response"])
        else:
            # TODO: HuggingFace model loaded at startup (app.state.sql_model)
            raise NotImplementedError("HuggingFace SQL provider not yet implemented")

    async def execute_and_answer(self, question: str, db_connection, db) -> str:
        """
        Full flow: question -> SQL -> execute -> natural language answer.

        Steps:
        1. Generate SQL from question + schema
        2. Validate SQL (read-only, no mutations)
        3. Execute against external DB
        4. Format results
        5. Pass results + question to chat LLM for natural language answer
        """
        # TODO: implement
        pass

    def _build_prompt(self, question: str, schema: dict, db_type: str) -> str:
        """Build the prompt for the Text2SQL model."""
        schema_text = ""
        for table_name, columns in schema.items():
            cols = ", ".join([f"{c['name']} {c['type']}" for c in columns])
            schema_text += f"CREATE TABLE {table_name} ({cols});\n"

        return (
            f"### Task\n"
            f"Generate a SQL query to answer the following question:\n"
            f"`{question}`\n\n"
            f"### Database Schema ({db_type})\n"
            f"{schema_text}\n"
            f"### SQL\n"
        )

    def _extract_sql(self, response: str) -> str:
        """Extract SQL from model response, stripping markdown fences etc."""
        sql = response.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        return sql.strip()

    def _validate_sql(self, sql: str) -> bool:
        """Ensure the SQL is read-only (SELECT only, no mutations)."""
        sql_upper = sql.strip().upper()
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]
        for keyword in forbidden:
            if keyword in sql_upper:
                return False
        return sql_upper.startswith("SELECT")
