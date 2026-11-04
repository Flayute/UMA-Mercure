from sqlalchemy import create_engine, event, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings

Base = declarative_base()

def make_engine(db_url):
    """Engine SQLite con WAL y busy_timeout: writer único (ticker/filler) y readers
    concurrentes sin 'database is locked'."""
    engine = create_engine(db_url, connect_args={"timeout": 30})
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()
    return engine

class TrackMetadata(Base):
    __tablename__ = 'track_metadata'
    
    id = Column(Integer, primary_key=True)
    file = Column(String, unique=True, nullable=False)
    artist = Column(String)
    title = Column(String)
    album = Column(String)
    genre = Column(String)
    bpm = Column(Float)
    musical_key = Column(String)
    energy = Column(Float)  # 0.0 to 1.0
    mood = Column(String)   # e.g., 'happy', 'chill', 'dark'
    play_count = Column(Integer, default=0)
    last_played = Column(String) # ISO date string
    duration = Column(Float)      # segundos; rellenado por scripts/fill_durations.py

class RadioQueue(Base):
    __tablename__ = 'radio_queue'
    id = Column(Integer, primary_key=True)
    sid = Column(String, default='main', index=True)  # sesión a la que pertenece
    pos = Column(Integer, default=0)                  # posición 0-based dentro de la sesión
    file = Column(String, nullable=False)

class SessionState(Base):
    __tablename__ = 'session_state'          # una fila por sesión; 'main' es la fila original (id=1)
    id = Column(Integer, primary_key=True)
    sid = Column(String, default='main', index=True)
    state = Column(String, default='stop')   # play | pause | stop
    queue_index = Column(Integer, default=0) # 0-based sobre RadioQueue.pos de su sesión
    offset = Column(Float, default=0.0)      # segundos de la pista al fijar started_at
    started_at = Column(Float, default=0.0)  # epoch; posición = offset + now-started_at
    shuffle = Column(Integer, default=1)
    repeat = Column(Integer, default=1)

def init_db():
    engine = make_engine(settings.DB_URL)
    Base.metadata.create_all(engine)
    # migración mínima: añadir duration si la tabla viene de la regen antigua
    with engine.connect() as conn:
        cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(track_metadata)")]
        if 'duration' not in cols:
            conn.exec_driver_sql("ALTER TABLE track_metadata ADD COLUMN duration REAL")
            conn.commit()
        # migración multi-sesión (2026-11-04): sid + pos
        qcols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(radio_queue)")]
        if 'sid' not in qcols:
            conn.exec_driver_sql("ALTER TABLE radio_queue ADD COLUMN sid TEXT NOT NULL DEFAULT 'main'")
            conn.commit()
        if 'pos' not in qcols:
            conn.exec_driver_sql("ALTER TABLE radio_queue ADD COLUMN pos INTEGER NOT NULL DEFAULT 0")
            conn.exec_driver_sql(
                "WITH t AS (SELECT id, row_number() OVER (PARTITION BY sid ORDER BY id) - 1 AS n "
                "FROM radio_queue) UPDATE radio_queue SET pos = (SELECT n FROM t WHERE t.id = radio_queue.id)")
            conn.commit()
        scols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(session_state)")]
        if 'sid' not in scols:
            conn.exec_driver_sql("ALTER TABLE session_state ADD COLUMN sid TEXT NOT NULL DEFAULT 'main'")
            conn.commit()
    return engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
