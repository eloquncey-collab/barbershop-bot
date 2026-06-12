import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import config

def make_cb(data, user_id=111):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb

@pytest.mark.asyncio
async def test_cb_call_ok():
    from handlers.info import cb_call
    with patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m:
        cb = make_cb("call")
        await cb_call(cb)
    m.assert_called_once()
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_call_exception():
    from handlers.info import cb_call
    with patch("handlers.info.edit_with_retry", side_effect=Exception("err")):
        cb = make_cb("call")
        await cb_call(cb)
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_masters_ok():
    from handlers.info import cb_masters
    with patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m:
        cb = make_cb("masters")
        await cb_masters(cb)
    m.assert_called_once()
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_masters_exception():
    from handlers.info import cb_masters
    with patch("handlers.info.edit_with_retry", side_effect=Exception("err")):
        cb = make_cb("masters")
        await cb_masters(cb)
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_master_detail_by_name():
    from handlers.info import cb_master_detail
    name = list(config.MASTERS.keys())[0]
    cb = make_cb(f"master:{name}")
    with (patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m,
         patch("storage.get_master_work_days", new_callable=AsyncMock, return_value=[1, 2, 3])):
        await cb_master_detail(cb)
    m.assert_called_once()
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_master_detail_by_index():
    from handlers.info import cb_master_detail
    cb = make_cb("master:0")
    with (patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m,
         patch("storage.get_master_work_days", new_callable=AsyncMock, return_value=[1, 3, 5])):
        await cb_master_detail(cb)
    m.assert_called_once()
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_master_not_found():
    from handlers.info import cb_master_detail
    cb = make_cb("master:NOMASTER_XYZ")
    await cb_master_detail(cb)
    cb.answer.assert_called_once()
    assert cb.answer.call_args[1].get("show_alert") is True

@pytest.mark.asyncio
async def test_cb_master_out_of_range():
    from handlers.info import cb_master_detail
    cb = make_cb("master:9999")
    await cb_master_detail(cb)
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_master_exception():
    from handlers.info import cb_master_detail
    name = list(config.MASTERS.keys())[0]
    cb = make_cb(f"master:{name}")
    with (patch("storage.get_master_work_days", new_callable=AsyncMock, return_value=[1]),
         patch("handlers.info.edit_with_retry", side_effect=Exception("err"))):
        await cb_master_detail(cb)
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_contacts_ok():
    from handlers.info import cb_contacts
    cb = make_cb("contacts")
    with patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m:
        await cb_contacts(cb)
    m.assert_called_once()
    assert config.BARBERSHOP_ADDRESS in m.call_args[0][1]
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_contacts_exception():
    from handlers.info import cb_contacts
    cb = make_cb("contacts")
    with patch("handlers.info.edit_with_retry", side_effect=Exception("err")):
        await cb_contacts(cb)
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_prices_ok():
    from handlers.info import cb_prices
    cb = make_cb("prices")
    with patch("handlers.info.edit_with_retry", new_callable=AsyncMock) as m:
        await cb_prices(cb)
    m.assert_called_once()
    text = m.call_args[0][1]
    price = list(config.SERVICES.values())[0]
    price_str = f"{price:,}".replace(",", " ")
    assert price_str in text
    cb.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cb_prices_exception():
    from handlers.info import cb_prices
    cb = make_cb("prices")
    with patch("handlers.info.edit_with_retry", side_effect=Exception("err")):
        await cb_prices(cb)
    cb.answer.assert_called_once()
