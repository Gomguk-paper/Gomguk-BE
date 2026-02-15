from enum import Enum


class AuthProvider(str, Enum):
    google = "google"
    github = "github"


class SummaryStyle(str, Enum):
    plain = "plain"
    detailed = "detailed"
    dc = "dc"
    basic_aggro = "basic_aggro"
    instagram_card_news = "instagram_card_news"


class Site(str, Enum):
    arxiv = "arxiv"
    github = "github"


class EventType(str, Enum):
    view = "view"
    like = "like"
    unlike = "unlike"
    save = "save"
    unsave = "unsave"
    search = "search"
    create_user = "create_user"
    login = "login"
    refresh_token = "refresh_token"
