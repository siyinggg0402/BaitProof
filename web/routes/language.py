"""Choosing the website's language."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from web.deps import LANG_CODES, LANG_COOKIE, safe_next

router = APIRouter()


@router.get("/lang/{code}")
def set_language(request: Request, code: str, next: str = "/"):
    """Remember the visitor's language (a cookie, no account) and go back to where they were."""
    lang = LANG_CODES.get(code.lower())
    if lang is None:
        raise HTTPException(404, "Unknown language")
    resp = RedirectResponse(safe_next(next), status_code=303)
    resp.set_cookie(LANG_COOKIE, lang, max_age=31536000, path="/", samesite="lax", secure=request.url.scheme == "https")
    return resp
