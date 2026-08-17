from unittest.mock import AsyncMock, MagicMock

import pytest

from app.douyin import DouyinChat, PageOperationError
from app.selectors import CHAT_PANEL_MARKERS, MESSAGE_INPUTS


@pytest.mark.asyncio
async def test_search_result_accepts_visible_partial_text() -> None:
    page = MagicMock()
    rows = MagicMock()
    page.locator.return_value.filter.return_value = rows
    rows.count = AsyncMock(return_value=0)
    exact = MagicMock()
    partial = MagicMock()
    page.get_by_text.side_effect = [exact, partial]
    exact.count = AsyncMock(return_value=0)
    partial.count = AsyncMock(return_value=1)
    candidate = MagicMock()
    candidate.is_visible = AsyncMock(return_value=True)
    partial.nth.return_value = candidate

    result = await DouyinChat(page)._search_result("好友")

    assert result is candidate


@pytest.mark.asyncio
async def test_search_result_ignores_hidden_exact_match() -> None:
    page = MagicMock()
    rows = MagicMock()
    page.locator.return_value.filter.return_value = rows
    rows.count = AsyncMock(return_value=0)
    exact = MagicMock()
    partial = MagicMock()
    page.get_by_text.side_effect = [exact, partial]
    exact.count = AsyncMock(return_value=1)
    hidden = MagicMock()
    hidden.is_visible = AsyncMock(return_value=False)
    exact.nth.return_value = hidden
    partial.count = AsyncMock(return_value=1)
    visible = MagicMock()
    visible.is_visible = AsyncMock(return_value=True)
    partial.nth.return_value = visible

    result = await DouyinChat(page)._search_result("好友")

    assert result is visible


@pytest.mark.asyncio
async def test_open_target_retries_after_failed_first_attempt() -> None:
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    chat = DouyinChat(page)
    calls = {"n": 0}

    async def flaky(name: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise PageOperationError("首次失败")

    chat._open_target_once = flaky

    await chat.open_target("好友A", retries=1)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_open_target_raises_after_retries_exhausted() -> None:
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    chat = DouyinChat(page)

    async def fail(name: str) -> None:
        raise PageOperationError("始终失败")

    chat._open_target_once = fail

    with pytest.raises(PageOperationError, match="始终失败"):
        await chat.open_target("好友A", retries=1)

    assert page.wait_for_timeout.await_count == 1


@pytest.mark.asyncio
async def test_open_target_succeeds_without_retry() -> None:
    page = MagicMock()
    chat = DouyinChat(page)

    async def ok(name: str) -> None:
        return None

    chat._open_target_once = ok

    await chat.open_target("好友A", retries=1)

    page.wait_for_timeout.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_opened_polls_until_confirmed() -> None:
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    chat = DouyinChat(page, confirm_timeout_ms=5_000)
    results = iter([PageOperationError("未就绪"), None])

    async def checker(name: str):
        return next(results, None)

    chat._chat_open_error = checker

    await chat._confirm_opened("好友A")

    assert page.wait_for_timeout.await_count == 1


@pytest.mark.asyncio
async def test_confirm_opened_raises_on_timeout() -> None:
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    chat = DouyinChat(page, confirm_timeout_ms=100)

    async def checker(name: str):
        return PageOperationError("一直失败")

    chat._chat_open_error = checker

    with pytest.raises(PageOperationError, match="一直失败"):
        await chat._confirm_opened("好友A")


@pytest.mark.asyncio
async def test_chat_open_error_accepts_panel_marker_with_name() -> None:
    page = MagicMock()
    marker = MagicMock()
    marker.count = AsyncMock(return_value=1)
    marker.is_visible = AsyncMock(return_value=True)
    matches = MagicMock()
    matches.count = AsyncMock(return_value=1)
    matches.nth.return_value = marker
    filtered = MagicMock()
    filtered.count = matches.count
    filtered.nth = matches.nth
    chain = MagicMock()
    chain.filter = MagicMock(return_value=filtered)
    page.locator.return_value = chain

    chat = DouyinChat(page)

    assert await chat._chat_open_error("好友A") is None


def _routed_page(*, input_count: int) -> MagicMock:
    page = MagicMock()
    first_target = MagicMock()
    first_target.count = AsyncMock(return_value=input_count)
    first_target.is_visible = AsyncMock(return_value=True)
    composer = MagicMock()
    composer.first = first_target
    filtered = MagicMock()
    filtered.count = AsyncMock(return_value=0)
    chain = MagicMock()
    chain.filter = MagicMock(return_value=filtered)
    def locator_router(selector: str):
        if selector in MESSAGE_INPUTS:
            return composer
        return chain

    page.locator.side_effect = locator_router
    return page


@pytest.mark.asyncio
async def test_chat_open_error_rejects_composer_when_name_is_only_in_sidebar() -> None:
    assert CHAT_PANEL_MARKERS
    page = _routed_page(input_count=1)

    chat = DouyinChat(page)

    error = await chat._chat_open_error("好友A")

    assert isinstance(error, PageOperationError)
    assert "输入框: 有" in str(error)


@pytest.mark.asyncio
async def test_chat_open_error_rejects_when_name_absent() -> None:
    page = _routed_page(input_count=0)

    chat = DouyinChat(page)

    error = await chat._chat_open_error("好友A")

    assert isinstance(error, PageOperationError)
    assert "无法确认聊天已打开" in str(error)
