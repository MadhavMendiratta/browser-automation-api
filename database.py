from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text, DateTime, func, desc
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from contextlib import contextmanager
import logging

# 1. Setup Database Connection
# We rely on config, but to avoid circular imports, we'll pass the URL dynamically or default it
# For simplicity in this module, we will define the Base here.
Base = declarative_base()

# 2. Define the Table Model
class ScrapingRequest(Base):
    __tablename__ = "scraping_requests"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    endpoint = Column(String)  # e.g., "browse", "screenshot"
    status_code = Column(Integer)
    response_time = Column(Float)  # Seconds
    cache_hit = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

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
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

# 3. Database Engine & Session Setup
# We will initialize these when the app starts
engine = None
SessionLocal = None

def init_db(database_url: str):
    """
    Called on app startup to create tables and connection engine.
    connect_args={"check_same_thread": False} is needed for SQLite in multi-threaded FastAPI.
    """
    global engine, SessionLocal
    engine = create_engine(
        database_url, 
        connect_args={"check_same_thread": False} 
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logging.info(f"Database initialized at {database_url}")

# 4. Helper: Get DB Session
# Use this with 'with get_db_session() as db:'
@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# 5. Helper: Log Request
def log_request_to_db(url: str, endpoint: str, status_code: int, response_time: float, cache_hit: bool, error_message: str = None):
    """
    Inserts a new request record into the database.
    Designed to be run in a BackgroundTask so it doesn't slow down the response.
    """
    if SessionLocal is None:
        logging.error("Database not initialized!")
        return

    try:
        with get_db_session() as db:
            new_record = ScrapingRequest(
                url=url,
                endpoint=endpoint,
                status_code=status_code,
                response_time=response_time,
                cache_hit=cache_hit,
                error_message=error_message
            )
            db.add(new_record)
            # Commit happens automatically due to contextmanager
    except Exception as e:
        logging.error(f"Failed to log request to DB: {e}")

# 6. Analytics: Get History
def get_request_history(limit: int = 50):
    try:
        with get_db_session() as db:
            requests = db.query(ScrapingRequest).order_by(desc(ScrapingRequest.created_at)).limit(limit).all()
            return [req.to_dict() for req in requests]
    except Exception as e:
        logging.error(f"Error fetching history: {e}")
        return []

# 7. Analytics: Get Stats
def get_stats():
    """Returns aggregated statistics about usage."""
    try:
        with get_db_session() as db:
            total_requests = db.query(ScrapingRequest).count()
            
            # Average response time
            avg_time = db.query(func.avg(ScrapingRequest.response_time)).scalar() or 0
            
            # Cache Hit Rate
            cache_hits = db.query(ScrapingRequest).filter(ScrapingRequest.cache_hit == True).count()
            cache_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
            
            # Success Rate (Status 200-299)
            success_count = db.query(ScrapingRequest).filter(
                ScrapingRequest.status_code >= 200, 
                ScrapingRequest.status_code < 300
            ).count()
            success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0

            # Requests per endpoint
            endpoint_stats = db.query(
                ScrapingRequest.endpoint, func.count(ScrapingRequest.id)
            ).group_by(ScrapingRequest.endpoint).all()
            
            # Top Domains (Python processing for simplicity)
            # We fetch all URLs and parse them in Python to find top domains
            # (Note: For massive datasets, this should be done via SQL logic or a separate column)
            recent_urls = db.query(ScrapingRequest.url).limit(1000).all()
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
        logging.error(f"Error fetching stats: {e}")
        return {"error": str(e)}