"""Cookie plumbing around Supabase Auth sessions — no network calls here,
those live behind httpx and are exercised through the running server."""

from jobs_agent.web import auth


def test_parse_cookies_reads_both_session_cookies():
    header = f"{auth.ACCESS_COOKIE}=abc; {auth.REFRESH_COOKIE}=xyz; other=1"
    cookies = auth.parse_cookies(header)
    assert cookies[auth.ACCESS_COOKIE] == "abc"
    assert cookies[auth.REFRESH_COOKIE] == "xyz"


def test_parse_cookies_handles_no_header():
    assert auth.parse_cookies(None) == {}


def test_set_cookie_headers_are_http_only_and_carry_both_tokens():
    session = auth.Session(access_token="a", refresh_token="r",
                           user_id="u1", email="a@b.com")
    headers = auth.set_cookie_headers(session)
    assert any(h.startswith(f"{auth.ACCESS_COOKIE}=a;") and "HttpOnly" in h for h in headers)
    assert any(h.startswith(f"{auth.REFRESH_COOKIE}=r;") and "HttpOnly" in h for h in headers)


def test_secure_flag_only_set_on_vercel(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    session = auth.Session(access_token="a", refresh_token="r", user_id="u1", email="")
    assert not any("Secure" in h for h in auth.set_cookie_headers(session))

    monkeypatch.setenv("VERCEL", "1")
    assert all("Secure" in h for h in auth.set_cookie_headers(session))


def test_clear_cookie_headers_expire_both_tokens():
    headers = auth.clear_cookie_headers()
    assert any(h.startswith(f"{auth.ACCESS_COOKIE}=;") and "Max-Age=0" in h for h in headers)
    assert any(h.startswith(f"{auth.REFRESH_COOKIE}=;") and "Max-Age=0" in h for h in headers)
