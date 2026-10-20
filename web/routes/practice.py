"""Practice drills, the family challenge and its share card, and the resilience map."""
from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from core.domain.schemas import Drill
from core.pipelines import challenge, train
from core.storage import model
from web import cardimg
from web.deps import LANG_CODES, limit_expensive, request_lang
from web.pages import page

router = APIRouter()

SESSIONS: "OrderedDict[str, dict[str, Drill]]" = OrderedDict()  # in-memory; answers never leave the server


@router.get("/train", response_class=HTMLResponse)
def train_page(request: Request):
    return page(request, "train.html")


@router.post("/api/train/start", dependencies=[Depends(limit_expensive)])
def train_start(request: Request):
    lang = request_lang(request)
    drills = train.build_session(lang=lang)
    sid = drills[0].id + "s" if drills else "empty"
    SESSIONS[sid] = {d.id: d for d in drills}
    while len(SESSIONS) > 200:
        SESSIONS.popitem(last=False)
    return {"session": sid, "items": [d.public() for d in drills], "map": model.resilience_map(lang)}


class AnswerIn(BaseModel):
    session: str
    item_id: str
    choice: int | None = None
    text: str = ""


@router.post("/api/train/answer")
def train_answer(request: Request, a: AnswerIn):
    drill = SESSIONS.get(a.session, {}).get(a.item_id)
    if not drill:
        raise HTTPException(404, "That practice session expired. Start a new one.")
    before = model.baitproof_score()
    lang = request_lang(request)
    g = train.grade(drill, a.choice, a.text, lang=lang)
    m = model.resilience_map(lang)
    return {"result": g.result, "note": g.note, "correct_index": drill.correct_index, "map": m, "delta": m["score"] - before}


@router.post("/challenge/new", dependencies=[Depends(limit_expensive)])
def challenge_new(request: Request):
    return RedirectResponse(f"/challenge/{challenge.create(lang=request_lang(request))}", status_code=303)


@router.get("/challenge/{cid}", response_class=HTMLResponse)
def challenge_page(request: Request, cid: str):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    return page(request, "challenge.html", cid=cid, items=[{"text": i["text"]} for i in items])


class SubmitIn(BaseModel):
    answers: list[bool | None]


@router.post("/api/challenge/{cid}/submit")
def challenge_submit(request: Request, cid: str, body: SubmitIn):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    res = challenge.score(items, body.answers)
    lang = request_lang(request)
    res["card_url"] = f"/card/{cid}?s={res['right']}" + ("" if lang == "en" else f"&lang={lang}")  # the link carries the language of its preview
    return res


@router.get("/card/{cid}", response_class=HTMLResponse)
def card(request: Request, cid: str, s: int = 0, lang: str | None = Query(None)):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    total = len(items)
    s = max(0, min(s, total))
    og_lang = LANG_CODES.get((lang or "").lower()) or request_lang(request)  # the preview follows the link's language, the page the visitor's
    return page(request, "card.html", cid=cid, pct=round(100 * s / total), right=s, total=total, og_lang=og_lang,
                url=str(request.url_for("challenge_page", cid=cid)),
                image=str(request.url_for("card_image", cid=cid)) + f"?s={s}" + ("" if og_lang == "en" else f"&lang={og_lang}"))


@router.get("/card-image/{cid}.png")
def card_image(cid: str, s: int = 0, lang: str = "en"):
    """Share-card image for link previews (Open Graph). Public: contains only the score, no message content."""
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    s = max(0, min(s, len(items)))
    return Response(cardimg.render(round(100 * s / len(items)), s, len(items), LANG_CODES.get(lang.lower(), "en")), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/api/map")
def api_map(request: Request):
    return model.resilience_map(request_lang(request))
