import os
from sqlmodel import SQLModel, Field, Column, JSON, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime


class EventSummary(SQLModel, table=True):
    __tablename__ = "event_summaries"
    
    id: int | None = Field(default=None, primary_key=True)
    payload: dict = Field(sa_column=Column(JSON))
    summary: str = Field()
    created_at: datetime = Field(default_factory=datetime.now)
    

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./event_summary.db")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def save_event_summary(payload: dict, summary: str) -> EventSummary:
    async with async_session_maker() as session:
        event = EventSummary(payload=payload, summary=summary)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event
    

async def get_event_summaries(since: int) -> list[EventSummary]:
    async with async_session_maker() as session:
        statement = select(EventSummary).where(
            EventSummary.created_at >= datetime.fromtimestamp(since)
        ).order_by(EventSummary.created_at.desc())
        
        result = await session.execute(statement)
        return result.scalars().all()