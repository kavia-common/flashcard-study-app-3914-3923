from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import sqlite3
import os

# Database path (placed inside container for persistence)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "flashcards.db"))

# --- Database Utilities ---

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cursor = con.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            known_count INTEGER DEFAULT 0,
            unknown_count INTEGER DEFAULT 0,
            last_reviewed_at TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    con.commit()
    con.close()


# --- Pydantic Models ---

class FlashcardBase(BaseModel):
    question: str = Field(..., description="The question side of the flashcard.")
    answer: str = Field(..., description="The answer side of the flashcard.")

class FlashcardCreate(FlashcardBase):
    pass

class FlashcardUpdate(BaseModel):
    question: Optional[str] = Field(None, description="The updated question.")
    answer: Optional[str] = Field(None, description="The updated answer.")

class Flashcard(FlashcardBase):
    id: int
    known_count: int
    unknown_count: int
    last_reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class ReviewBody(BaseModel):
    known: bool = Field(..., description="Whether the user marked this card as known (true) or unknown (false).")

# --- FastAPI App ---

app = FastAPI(
    title="Flashcard Backend API",
    description="Backend API for flashcard CRUD and review with spaced repetition stats.",
    version="1.0.0",
    openapi_tags=[
        {"name": "health", "description": "Health check endpoint"},
        {"name": "flashcards", "description": "CRUD operations and review on flashcards"},
    ]
)

# CORS for frontend on port 3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Ensure DB exists and table is created
    init_db()


# PUBLIC_INTERFACE
@app.get("/health", tags=["health"])
def health_check():
    """
    API health check endpoint.

    Returns {"status": "ok"} if the service is running.
    """
    return {"status": "ok"}


# PUBLIC_INTERFACE
@app.get("/flashcards", response_model=List[Flashcard], tags=["flashcards"])
def list_flashcards():
    """
    List all flashcards stored in the database.
    """
    con = get_db()
    cards = [dict(row) for row in con.execute("SELECT * FROM flashcards ORDER BY created_at DESC")]
    con.close()
    for card in cards:
        # Parse datetime fields
        card["created_at"] = datetime.fromisoformat(card["created_at"])
        card["updated_at"] = datetime.fromisoformat(card["updated_at"])
        card["last_reviewed_at"] = datetime.fromisoformat(card["last_reviewed_at"]) if card["last_reviewed_at"] else None
    return cards

# PUBLIC_INTERFACE
@app.post("/flashcards", response_model=Flashcard, status_code=status.HTTP_201_CREATED, tags=["flashcards"])
def create_flashcard(card: FlashcardCreate):
    """
    Create a new flashcard record.
    """
    now = datetime.utcnow().replace(microsecond=0)
    values = (card.question, card.answer, now.isoformat(), now.isoformat())
    con = get_db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO flashcards (question, answer, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        values,
    )
    con.commit()
    new_id = cur.lastrowid
    row = cur.execute("SELECT * FROM flashcards WHERE id=?", (new_id,)).fetchone()
    con.close()
    result = dict(row)
    result["created_at"] = datetime.fromisoformat(result["created_at"])
    result["updated_at"] = datetime.fromisoformat(result["updated_at"])
    result["last_reviewed_at"] = datetime.fromisoformat(result["last_reviewed_at"]) if result["last_reviewed_at"] else None
    return result

# PUBLIC_INTERFACE
@app.get("/flashcards/{id}", response_model=Flashcard, tags=["flashcards"])
def get_flashcard(id: int):
    """
    Retrieve a single flashcard by its ID.
    """
    con = get_db()
    row = con.execute("SELECT * FROM flashcards WHERE id=?", (id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    result = dict(row)
    result["created_at"] = datetime.fromisoformat(result["created_at"])
    result["updated_at"] = datetime.fromisoformat(result["updated_at"])
    result["last_reviewed_at"] = datetime.fromisoformat(result["last_reviewed_at"]) if result["last_reviewed_at"] else None
    return result

# PUBLIC_INTERFACE
@app.put("/flashcards/{id}", response_model=Flashcard, tags=["flashcards"])
def update_flashcard(id: int, card: FlashcardUpdate):
    """
    Update the question or answer for a flashcard.
    """
    con = get_db()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM flashcards WHERE id=?", (id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="Flashcard not found")
    curr = dict(row)
    updated_question = card.question if card.question is not None else curr['question']
    updated_answer = card.answer if card.answer is not None else curr['answer']
    now = datetime.utcnow().replace(microsecond=0)
    cur.execute(
        """
        UPDATE flashcards SET question=?, answer=?, updated_at=? WHERE id=?
        """,
        (updated_question, updated_answer, now.isoformat(), id),
    )
    con.commit()
    new_row = cur.execute("SELECT * FROM flashcards WHERE id=?", (id,)).fetchone()
    con.close()
    result = dict(new_row)
    result["created_at"] = datetime.fromisoformat(result["created_at"])
    result["updated_at"] = datetime.fromisoformat(result["updated_at"])
    result["last_reviewed_at"] = datetime.fromisoformat(result["last_reviewed_at"]) if result["last_reviewed_at"] else None
    return result

# PUBLIC_INTERFACE
@app.delete("/flashcards/{id}", status_code=status.HTTP_204_NO_CONTENT, tags=["flashcards"])
def delete_flashcard(id: int):
    """
    Delete a flashcard from the database.
    """
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM flashcards WHERE id=?", (id,))
    con.commit()
    con.close()
    return

# PUBLIC_INTERFACE
@app.post("/flashcards/{id}/review", response_model=Flashcard, tags=["flashcards"])
def review_flashcard(id: int, data: ReviewBody):
    """
    Review a flashcard: If 'known'=true, increment known_count; if 'known'=false, increment unknown_count.
    Always update last_reviewed_at.
    """
    con = get_db()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM flashcards WHERE id=?", (id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="Flashcard not found")
    if data.known:
        cur.execute(
            """
            UPDATE flashcards
            SET known_count = known_count + 1, last_reviewed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (datetime.utcnow().replace(microsecond=0).isoformat(), datetime.utcnow().replace(microsecond=0).isoformat(), id),
        )
    else:
        cur.execute(
            """
            UPDATE flashcards
            SET unknown_count = unknown_count + 1, last_reviewed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (datetime.utcnow().replace(microsecond=0).isoformat(), datetime.utcnow().replace(microsecond=0).isoformat(), id),
        )
    con.commit()
    new_row = cur.execute("SELECT * FROM flashcards WHERE id=?", (id,)).fetchone()
    con.close()
    result = dict(new_row)
    result["created_at"] = datetime.fromisoformat(result["created_at"])
    result["updated_at"] = datetime.fromisoformat(result["updated_at"])
    result["last_reviewed_at"] = datetime.fromisoformat(result["last_reviewed_at"]) if result["last_reviewed_at"] else None
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=3001, reload=True)
