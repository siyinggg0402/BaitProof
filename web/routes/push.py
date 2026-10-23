"""Web Push endpoints: is it on, subscribe this browser, unsubscribe it, send a test. Only for people with a profile, only to browsers' own push services."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.storage import links, push
from web.deps import limit_expensive, request_lang

router = APIRouter()


class Keys(BaseModel):
    p256dh: str
    auth: str


class SubIn(BaseModel):
    endpoint: str
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str


@router.get("/api/push/config")
def config():
    me = links.current_profile()
    return {"enabled": push.enabled(), "key": push.public_key(), "devices": push.count(me) if push.enabled() else 0}


@router.post("/api/push/subscribe")
def subscribe(request: Request, body: SubIn):
    if not push.enabled():
        raise HTTPException(404, "Notifications are not switched on for this site.")
    try:
        push.subscribe(links.current_profile(), body.endpoint, body.keys.p256dh, body.keys.auth, request_lang(request))
    except push.PushError as e:
        raise HTTPException(400, str(e))
    return {"devices": push.count(links.current_profile())}


@router.post("/api/push/unsubscribe")
def unsubscribe(body: EndpointIn):
    push.unsubscribe(links.current_profile(), body.endpoint)
    return {"devices": push.count(links.current_profile())}


@router.post("/api/push/test", dependencies=[Depends(limit_expensive)])
def test():
    return {"sent": push.send_test(links.current_profile())}
