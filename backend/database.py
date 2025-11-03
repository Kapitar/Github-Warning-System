import os
from sqlmodel import SQLModel, Field, Column, JSON, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta


class EventSummary(SQLModel, table=True):
    __tablename__ = "event_summaries"
    
    id: int | None = Field(default=None, primary_key=True)
    payload: dict = Field(sa_column=Column(JSON))
    summary: str = Field()
    created_at: datetime = Field(default_factory=datetime.now)
    

class Accident(SQLModel, table=True):
    __tablename__ = "accidents"
    
    id: int | None = Field(default=None, primary_key=True)
    accident_type: str = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
    repo_name: str = Field(index=True)
    

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./event_summary.db")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        
        
async def save_accident(
    accident_type: str, 
    repo_name: str
)-> Accident:
    async with async_session_maker() as session:
        accident = Accident(accident_type=accident_type, repo_name=repo_name)
        session.add(accident)
        await session.commit()
        await session.refresh(accident)
        return accident
    

async def get_accidents(
    accident_type: str,
    repo_name: str,
    hours: int | None = None
) -> list[Accident]:
    async with async_session_maker() as session:
        statement = select(Accident).where(
            Accident.accident_type == accident_type,
            Accident.repo_name == repo_name
        )
        
        if hours is not None:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            statement = statement.where(Accident.timestamp >= cutoff_time)
        
        statement = statement.order_by(Accident.timestamp.desc())
        
        result = await session.execute(statement)
        return result.scalars().all()


async def save_event_summary(
    payload: dict, 
    summary: str
) -> EventSummary:
    async with async_session_maker() as session:
        event = EventSummary(payload=payload, summary=summary)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event
    

async def get_event_summaries(
    since: int = 0, 
    limit: int = 50, 
    offset: int = 0
) -> list[EventSummary]:
    async with async_session_maker() as session:
        statement = select(EventSummary).where(
            EventSummary.created_at > datetime.fromtimestamp(since)
        ).order_by(EventSummary.created_at.desc()).limit(limit).offset(offset)
        
        result = await session.execute(statement)
        return result.scalars().all()