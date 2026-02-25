from sqlalchemy import create_engine, text, Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, func, desc
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Base declaration for all ORM models
Base = declarative_base()

# User Model
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    requests = relationship("ScrapingRequest", back_populates="user")


# ScrapingRequest Model
class ScrapingRequest(Base):
    __tablename__ = "scraping_requests"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    endpoint = Column(String)
    status_code = Column(Integer)
    response_time = Column(Float)
    cache_hit = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="requests")

    def to_dict(self):
        """Convert database row to dictionary for JSON response"""
        return {
            "id": self.id,
            "url": self.url,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "response_time": self.response_time,
            "cache_hit": self.cache_hit,
            "error_message": self.error_message,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

# Database Engine & Session Setup
engine = None
SessionLocal = None

def init_db(database_url: str):
    """
    Called on app startup to create the PostgreSQL engine, session factory,
    and all tables. Raises on missing URL or connection failure.
    """
    global engine, SessionLocal

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Please configure a PostgreSQL connection string in your environment."
        )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Verify the connection is reachable
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"PostgreSQL connection verified: {_mask_url(database_url)}")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise RuntimeError(f"Cannot connect to database: {e}") from e

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logger.info("All database tables created / verified.")


def _mask_url(url: str) -> str:
    """Mask password in database URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username}:****@{parsed.hostname}"
                       + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(masked)
    except Exception:
        pass
    return url

@contextmanager
def get_db_session():
    """Provide a transactional database session scope."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def log_request_to_db(url: str, endpoint: str, status_code: int, response_time: float, cache_hit: bool, error_message: str = None, user_id: int = None):
    """
    Inserts a new request record into the database.
    Designed to be run in a BackgroundTask so it doesn't slow down the response.
    """
    if SessionLocal is None:
        logger.error("Database not initialized!")
        return

    try:
        with get_db_session() as db:
            new_record = ScrapingRequest(
                url=url,
                endpoint=endpoint,
                status_code=status_code,
                response_time=response_time,
                cache_hit=cache_hit,
                error_message=error_message,
                user_id=user_id,
            )
            db.add(new_record)
    except Exception as e:
        logger.error(f"Failed to log request to DB: {e}")

def get_request_history(limit: int = 50, user_id: int = None):
    try:
        with get_db_session() as db:
            query = db.query(ScrapingRequest)
            if user_id is not None:
                query = query.filter(ScrapingRequest.user_id == user_id)
            requests = query.order_by(desc(ScrapingRequest.created_at)).limit(limit).all()
            return [req.to_dict() for req in requests]
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return []

def get_stats(user_id: int = None):
    """Returns aggregated statistics about usage, scoped to a specific user when user_id is provided."""
    try:
        with get_db_session() as db:
            base_query = db.query(ScrapingRequest)
            if user_id is not None:
                base_query = base_query.filter(ScrapingRequest.user_id == user_id)

            total_requests = base_query.count()
            
            # Average response time
            avg_time = base_query.with_entities(func.avg(ScrapingRequest.response_time)).scalar() or 0
            
            # Cache Hit Rate
            cache_hits = base_query.filter(ScrapingRequest.cache_hit == True).count()
            cache_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
            
            # Success Rate (Status 200-299)
            success_count = base_query.filter(
                ScrapingRequest.status_code >= 200, 
                ScrapingRequest.status_code < 300
            ).count()
            success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0

            # Requests per endpoint
            ep_query = db.query(
                ScrapingRequest.endpoint, func.count(ScrapingRequest.id)
            )
            if user_id is not None:
                ep_query = ep_query.filter(ScrapingRequest.user_id == user_id)
            endpoint_stats = ep_query.group_by(ScrapingRequest.endpoint).all()
            
            # Top Domains
            url_query = db.query(ScrapingRequest.url)
            if user_id is not None:
                url_query = url_query.filter(ScrapingRequest.user_id == user_id)
            recent_urls = url_query.limit(1000).all()
            domain_counts = {}
            for row in recent_urls:
                try:
                    domain = row.url.split("//")[-1].split("/")[0]
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                except:
                    pass
            
            top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            return {
                "total_requests": total_requests,
                "average_response_time_seconds": round(avg_time, 2),
                "cache_hit_rate_percent": round(cache_rate, 1),
                "success_rate_percent": round(success_rate, 1),
                "endpoints": {e: count for e, count in endpoint_stats},
                "top_domains": top_domains
            }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {"error": str(e)}