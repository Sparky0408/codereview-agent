"""SQLAlchemy async Base declaration.

Concrete models will be added in later sprints.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class BotComment(Base):
    __tablename__ = 'bot_comments'
    id = Column(Integer, primary_key=True)
    github_comment_id = Column(BigInteger, unique=True, index=True)
    repo_full_name = Column(String, index=True)
    pr_number = Column(Integer, index=True)
    file_path = Column(String)
    line = Column(Integer)
    severity = Column(String)
    comment_text = Column(Text)
    posted_at = Column(DateTime(timezone=True))

class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True)
    bot_comment_id = Column(Integer, ForeignKey('bot_comments.id'), index=True)
    reaction_type = Column(String)
    user_login = Column(String)
    reacted_at = Column(DateTime(timezone=True))
