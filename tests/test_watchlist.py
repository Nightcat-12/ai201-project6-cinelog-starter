"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service, following the patterns in test_collection.py.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyOnWatchlistError,
    NotOnWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a WatchlistEntry in the database.
    """
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film
        assert entry.public is True

        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyOnWatchlistError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyOnWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── Nonexistent film (Comment 3) ─────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.
    Modeled on test_add_to_collection_nonexistent_film_raises.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── Visibility toggle (stretch) ──────────────────────────────────────────────

def test_add_to_watchlist_respects_public_flag(app, sample_user, sample_film):
    """
    Callers should be able to set public=False explicitly rather than
    relying on the default.
    """
    with app.app_context():
        entry = add_to_watchlist(
            user_id=sample_user, film_id=sample_film, public=False
        )
        assert entry.public is False


# ── remove_from_watchlist (stretch) ──────────────────────────────────────────

def test_remove_from_watchlist_deletes_entry(app, sample_user, sample_film):
    """
    remove_from_watchlist should delete the matching entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        assert remove_from_watchlist(user_id=sample_user, film_id=sample_film) is True

        remaining = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert remaining is None


def test_remove_from_watchlist_missing_raises(app, sample_user, sample_film):
    """
    Removing a film that isn't on the watchlist should raise NotOnWatchlistError.
    Chosen as an extra edge case: mirrors NotInCollectionError and guards the
    DELETE endpoint against silent success on a no-op.
    """
    with app.app_context():
        with pytest.raises(NotOnWatchlistError):
            remove_from_watchlist(user_id=sample_user, film_id=sample_film)


# ── Alphabetical sort (Comment 5) ────────────────────────────────────────────

def test_get_watchlist_returns_alphabetical(app, sample_user):
    """
    get_watchlist() should return films sorted by title ascending.
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta

        film_z = Film(title="Zodiac", year=2007, genre="Thriller")
        film_a = Film(title="Arrival", year=2016, genre="Sci-Fi")
        db.session.add_all([film_z, film_a])
        db.session.commit()

        later = datetime.now(timezone.utc)
        earlier = datetime.now(timezone.utc) - timedelta(days=5)

        # Zodiac added more recently — if we sorted by date_added desc it would win
        entry_z = WatchlistEntry(
            user_id=sample_user, film_id=film_z.id, date_added=later
        )
        entry_a = WatchlistEntry(
            user_id=sample_user, film_id=film_a.id, date_added=earlier
        )
        db.session.add_all([entry_z, entry_a])
        db.session.commit()

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        assert titles[0] == "Arrival"
        assert titles[1] == "Zodiac"
