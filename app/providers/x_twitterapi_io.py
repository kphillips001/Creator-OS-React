"""Narrow backend-only TwitterAPI.io profile resolution provider."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TwitterApiIoError(RuntimeError):
    pass


class TwitterApiIoNotFound(TwitterApiIoError):
    pass


@dataclass(frozen=True)
class ResolvedXProfile:
    x_user_id: str
    username: str
    display_name: str | None
    profile_image_url: str | None
    profile_banner_url: str | None
    bio: str | None
    location: str | None
    account_created_at: datetime | None
    verified: bool | None
    verification_type: str | None
    followers_count: int
    following_count: int | None
    statuses_count: int | None
    media_count: int | None
    favorites_count: int | None


@dataclass(frozen=True)
class ResolvedXActivity:
    x_tweet_id: str
    posted_at: datetime
    text: str | None
    is_reply: bool
    is_quote: bool
    is_retweet: bool
    has_media: bool
    language: str | None = None
    conversation_id: str | None = None
    media_metadata: tuple[Mapping[str, Any], ...] = ()
    view_count: int | None = None
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    bookmark_count: int | None = None

@dataclass(frozen=True)
class ResolvedXAudienceUser:
    x_user_id: str
    username: str
    display_name: str | None
    profile_image_url: str | None
    followers_count: int | None
    following_count: int | None
    verified: bool | None
    account_created_at: datetime | None

@dataclass(frozen=True)
class ResolvedXAudienceRecord:
    user: ResolvedXAudienceUser
    interaction_x_tweet_id: str
    occurred_at: datetime | None

@dataclass(frozen=True)
class ResolvedXAudiencePage:
    records: tuple[ResolvedXAudienceRecord, ...]
    next_cursor: str
    has_next_page: bool


class TwitterApiIoProvider:
    BASE_URL = "https://api.twitterapi.io"

    def __init__(self, api_key: str | None = None, *, session: requests.Session | None = None, timeout: tuple[float, float] = (5.0, 30.0), max_retries: int = 3):
        key = (api_key if api_key is not None else os.getenv("TWITTERAPI_API_KEY", "")).strip()
        if not key:
            raise TwitterApiIoError("TwitterAPI.io is not configured.")
        self._session = session or self._build_session(max_retries)
        self._session.headers.update({"X-API-Key": key, "Accept": "application/json"})
        self._timeout = timeout

    @staticmethod
    def _build_session(max_retries: int) -> requests.Session:
        retry = Retry(total=max_retries, connect=max_retries, read=max_retries, status=max_retries, backoff_factor=.5, status_forcelist=(429,500,502,503,504), allowed_methods=frozenset({"GET"}), respect_retry_after_header=True, raise_on_status=False)
        session = requests.Session(); session.mount("https://", HTTPAdapter(max_retries=retry)); return session

    def get_user_by_username(self, username: str) -> ResolvedXProfile:
        submitted = username.strip().lstrip("@")
        if not submitted:
            raise ValueError("username must not be empty")
        try:
            response = self._session.get(f"{self.BASE_URL}/twitter/user/info", params={"userName": submitted}, timeout=self._timeout)
            if response.status_code == 404:
                raise TwitterApiIoNotFound(f"@{submitted} was not found.")
            response.raise_for_status(); payload = response.json()
        except TwitterApiIoNotFound:
            raise
        except requests.Timeout as exc:
            raise TwitterApiIoError("TwitterAPI.io profile lookup timed out.") from exc
        except (requests.RequestException, ValueError) as exc:
            raise TwitterApiIoError("TwitterAPI.io profile lookup failed.") from exc
        if not isinstance(payload, Mapping):
            raise TwitterApiIoError("TwitterAPI.io returned an unexpected profile response.")
        if payload.get("status") == "error" or payload.get("error"):
            message = str(payload.get("message") or payload.get("msg") or "").lower()
            if "not found" in message or "does not exist" in message:
                raise TwitterApiIoNotFound(f"@{submitted} was not found.")
            raise TwitterApiIoError("TwitterAPI.io rejected the profile lookup.")
        data = payload.get("data")
        if not isinstance(data, Mapping) or not data.get("id"):
            raise TwitterApiIoNotFound(f"@{submitted} was not found.")
        return self._normalize(data)

    def get_latest_activity(self, x_user_id: str) -> ResolvedXActivity | None:
        activities=self.get_recent_activities(x_user_id,max_pages=1)
        return max(activities,key=lambda activity:activity.posted_at) if activities else None

    def get_recent_activities(self, x_user_id: str, *, since: datetime | None = None, max_pages: int = 10) -> list[ResolvedXActivity]:
        user_id = str(x_user_id).strip()
        if not user_id:
            raise ValueError("x_user_id must not be empty")
        if max_pages<1: raise ValueError("max_pages must be positive")
        boundary=since.astimezone(timezone.utc) if since and since.tzinfo else since.replace(tzinfo=timezone.utc) if since else None
        cursor="";seen=set();activities=[];self.last_timeline_request_count=0
        for page_index in range(max_pages):
            payload=self._get_timeline_page(user_id,cursor);self.last_timeline_request_count+=1;tweets=payload.get("tweets")
            if not isinstance(tweets,list) and isinstance(payload.get("data"),Mapping): tweets=payload["data"].get("tweets")
            if not isinstance(tweets,list): raise TwitterApiIoError("TwitterAPI.io activity response omitted the tweets list.")
            page=[self._normalize_activity(tweet) for tweet in tweets if isinstance(tweet,Mapping)]
            if tweets and not page: raise TwitterApiIoError("TwitterAPI.io activity response contained no valid activity records.")
            activities.extend(page)
            if not tweets or (boundary and page and min(item.posted_at for item in page)<boundary): break
            if not payload.get("has_next_page"): break
            next_cursor=payload.get("next_cursor")
            if not isinstance(next_cursor,str) or not next_cursor or next_cursor in seen or next_cursor==cursor: raise TwitterApiIoError("TwitterAPI.io activity pagination cursor is invalid.")
            if page_index==max_pages-1: raise TwitterApiIoError("TwitterAPI.io activity refresh exceeded the defensive page limit.")
            seen.add(next_cursor);cursor=next_cursor
        return activities

    def _get_timeline_page(self,user_id:str,cursor:str)->Mapping[str,Any]:
        try:
            response=self._session.get(f"{self.BASE_URL}/twitter/user/last_tweets",params={"userId":user_id,"cursor":cursor},timeout=self._timeout)
            response.raise_for_status();payload=response.json()
        except requests.Timeout as exc: raise TwitterApiIoError("TwitterAPI.io activity lookup timed out.") from exc
        except (requests.RequestException,ValueError) as exc: raise TwitterApiIoError("TwitterAPI.io activity lookup failed.") from exc
        if not isinstance(payload,Mapping) or payload.get("status")=="error" or payload.get("error"): raise TwitterApiIoError("TwitterAPI.io returned an unexpected activity response.")
        return payload

    def get_tweet(self,x_tweet_id:str)->ResolvedXActivity:
        tweet_id=str(x_tweet_id).strip()
        if not tweet_id: raise ValueError("x_tweet_id must not be empty")
        try:
            response=self._session.get(f"{self.BASE_URL}/twitter/tweets",params={"tweet_ids":tweet_id},timeout=self._timeout)
            response.raise_for_status();payload=response.json()
        except requests.Timeout as exc: raise TwitterApiIoError("TwitterAPI.io tweet lookup timed out.") from exc
        except (requests.RequestException,ValueError) as exc: raise TwitterApiIoError("TwitterAPI.io tweet lookup failed.") from exc
        tweets=payload.get("tweets") if isinstance(payload,Mapping) else None
        if not isinstance(tweets,list) or not tweets or not isinstance(tweets[0],Mapping): raise TwitterApiIoError("TwitterAPI.io tweet response omitted the requested tweet.")
        result=self._normalize_activity(tweets[0])
        if result.x_tweet_id!=tweet_id: raise TwitterApiIoError("TwitterAPI.io returned a different tweet than requested.")
        return result

    def get_audience_page(self, signal_type: str, x_tweet_id: str, *, cursor: str = "") -> ResolvedXAudiencePage:
        """Fetch one documented audience page; orchestration owns durable pagination."""
        kind=signal_type.upper(); contracts={"REPLY":("replies","replies"),"RETWEET":("retweeters","users"),"QUOTE":("quotes","tweets")}
        if kind not in contracts: raise ValueError("Unsupported audience signal type.")
        tweet_id=str(x_tweet_id).strip()
        if not tweet_id: raise ValueError("x_tweet_id must not be empty")
        endpoint,list_key=contracts[kind]
        try:
            response=self._session.get(f"{self.BASE_URL}/twitter/tweet/{endpoint}",params={"tweetId":tweet_id,"cursor":cursor},timeout=self._timeout)
            response.raise_for_status();payload=response.json()
        except requests.Timeout as exc: raise TwitterApiIoError(f"TwitterAPI.io {kind.lower()} collection timed out.") from exc
        except (requests.RequestException,ValueError) as exc: raise TwitterApiIoError(f"TwitterAPI.io {kind.lower()} collection failed.") from exc
        if not isinstance(payload,Mapping) or payload.get("status")=="error" or payload.get("error"): raise TwitterApiIoError(f"TwitterAPI.io returned an unexpected {kind.lower()} response.")
        values=payload.get(list_key)
        # The documented key is `replies`; TwitterAPI.io's production replies
        # endpoint also returns the same tweet records under `tweets`. This
        # compatibility shape is already handled by Creator_OS's proven X_Auto
        # reader and retains the identical embedded-author contract.
        if not isinstance(values,list) and kind=="REPLY": values=payload.get("tweets")
        if not isinstance(values,list) and isinstance(payload.get("data"),Mapping):
            values=payload["data"].get(list_key)
            if not isinstance(values,list) and kind=="REPLY": values=payload["data"].get("tweets")
        if not isinstance(values,list): raise TwitterApiIoError(f"TwitterAPI.io {kind.lower()} response omitted {list_key}.")
        records=[]
        invalid_identity_records=0
        for value in values:
            if not isinstance(value,Mapping): continue
            author=value if kind=="RETWEET" else value.get("author")
            if not isinstance(author,Mapping): continue
            # Retweeter pages can contain unavailable/deleted account stubs
            # alongside valid users. Those stubs have no canonical identity
            # and therefore cannot produce an audience signal, but must not
            # discard the other valid identities returned on the same page.
            if kind=="RETWEET" and (not _text(author.get("id")) or not _text(author.get("userName") or author.get("username"))):
                invalid_identity_records+=1;continue
            user=self._normalize_audience_user(author)
            interaction=_text(value.get("id")) if kind!="RETWEET" else None
            interaction=interaction or f"RETWEET:{tweet_id}:{user.x_user_id}"
            records.append(ResolvedXAudienceRecord(user,interaction,_provider_datetime(value.get("createdAt"))))
        if kind=="RETWEET" and values and invalid_identity_records and not records:
            raise TwitterApiIoError("TwitterAPI.io retweeter response contained no usable immutable user identities.")
        next_cursor=_text(payload.get("next_cursor")) or ""
        has_next=bool(payload.get("has_next_page")) and bool(next_cursor) and bool(values)
        if has_next and next_cursor==cursor: raise TwitterApiIoError("TwitterAPI.io audience pagination cursor did not advance.")
        return ResolvedXAudiencePage(tuple(records),next_cursor,has_next)

    @staticmethod
    def _normalize_audience_user(data: Mapping[str, Any]) -> ResolvedXAudienceUser:
        x_user_id=_text(data.get("id"));username=_text(data.get("userName") or data.get("username"))
        if not x_user_id or not username: raise TwitterApiIoError("TwitterAPI.io audience record omitted immutable user identity.")
        return ResolvedXAudienceUser(x_user_id,username,_text(data.get("name")),_text(data.get("profilePicture")),_optional_count(data.get("followers")),_optional_count(data.get("following")),_boolean(data.get("isBlueVerified")),_provider_datetime(data.get("createdAt")))

    @staticmethod
    def _normalize_activity(data: Mapping[str, Any]) -> ResolvedXActivity:
        tweet_id = _text(data.get("id") or data.get("tweetId") or data.get("tweet_id"))
        posted_at = _provider_datetime(data.get("createdAt") or data.get("created_at"))
        if not tweet_id or posted_at is None:
            raise TwitterApiIoError("TwitterAPI.io returned a malformed activity record.")
        quoted = data.get("quoted_tweet") or data.get("quotedTweet")
        retweeted = data.get("retweeted_tweet") or data.get("retweetedTweet")
        media = data.get("media") or data.get("extendedEntities") or data.get("extended_entities")
        if isinstance(media,Mapping): media=media.get("media") or []
        media_items=tuple(item for item in media if isinstance(item,Mapping)) if isinstance(media,list) else ()
        return ResolvedXActivity(
            x_tweet_id=tweet_id,posted_at=posted_at,text=_text(data.get("text") or data.get("fullText") or data.get("full_text")),
            is_reply=bool(data.get("isReply") or data.get("inReplyToId") or data.get("in_reply_to_status_id")),
            is_quote=bool(data.get("isQuote") or quoted),is_retweet=bool(data.get("isRetweet") or retweeted),has_media=bool(media_items),
            language=_text(data.get("lang") or data.get("language")),conversation_id=_text(data.get("conversationId") or data.get("conversation_id")),media_metadata=media_items,
            view_count=_optional_count(data.get("viewCount",data.get("views"))),like_count=_optional_count(data.get("likeCount",data.get("likes"))),
            reply_count=_optional_count(data.get("replyCount",data.get("replies"))),retweet_count=_optional_count(data.get("retweetCount",data.get("retweets"))),
            quote_count=_optional_count(data.get("quoteCount",data.get("quotes"))),bookmark_count=_optional_count(data.get("bookmarkCount",data.get("bookmarks"))),
        )

    @staticmethod
    def _normalize(data: Mapping[str, Any]) -> ResolvedXProfile:
        username = _text(data.get("userName") or data.get("username"))
        followers = _count(data.get("followers", data.get("followers_count")))
        if not username or followers is None:
            raise TwitterApiIoError("TwitterAPI.io profile response omitted required identity or follower data.")
        return ResolvedXProfile(
            x_user_id=str(data["id"]), username=username,
            display_name=_text(data.get("name") or data.get("displayName")),
            profile_image_url=_text(data.get("profilePicture") or data.get("profile_image_url")),
            profile_banner_url=_text(data.get("coverPicture") or data.get("profileBanner") or data.get("profile_banner_url")),
            bio=_text(data.get("description") or data.get("bio")), location=_text(data.get("location")),
            account_created_at=_datetime(data.get("createdAt") or data.get("created_at")),
            verified=_boolean(data.get("isBlueVerified", data.get("verified"))),
            verification_type=_text(data.get("verifiedType") or data.get("verificationType")),
            followers_count=followers, following_count=_count(data.get("following", data.get("following_count"))),
            statuses_count=_count(data.get("statusesCount", data.get("statuses_count"))),
            media_count=_count(data.get("mediaCount", data.get("media_count"))),
            favorites_count=_count(data.get("favouritesCount", data.get("favoritesCount", data.get("favorites_count")))),
        )


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""; return text or None


def _count(value: Any) -> int | None:
    if value is None or value == "": return None
    try: result = int(value)
    except (TypeError, ValueError) as exc: raise TwitterApiIoError("TwitterAPI.io returned an invalid profile count.") from exc
    if result < 0: raise TwitterApiIoError("TwitterAPI.io returned an invalid profile count.")
    return result


def _optional_count(value: Any) -> int | None:
    return _count(value) if value is not None and value!="" else None


def _boolean(value: Any) -> bool | None:
    if value is None: return None
    if isinstance(value, bool): return value
    if str(value).lower() in {"true","1"}: return True
    if str(value).lower() in {"false","0"}: return False
    return None


def _datetime(value: Any) -> datetime | None:
    if not value: return None
    text = str(value).strip()
    try: return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError: return None


def _provider_datetime(value: Any) -> datetime | None:
    parsed = _datetime(value)
    if parsed is not None:
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None
