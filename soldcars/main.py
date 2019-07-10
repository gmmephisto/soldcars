import asyncio
import json
import logging

from functools import wraps

import aiohttp

from aiohttp import web
from object_validator import ValidationError, validate
from object_validator import DictScheme

from .db import Car, Motor
from .exceptions import BaseError

routes = web.RouteTableDef()

log = logging.getLogger()


def jsonerror(exc, reason=None, text=None):
    """Instantiate specified error as JSON mediatype."""

    assert isinstance(exc, web.HTTPException)

    info = {
        "reason": reason or exc.reason,
        "error": text or exc.text,
    }

    cls = exc.__class__

    return cls(text=json.dumps(info), content_type="application/json")


def jsonhandler(coro):
    """JSON request wrapper."""

    @wraps(coro)
    async def wrapper(*args, **kwargs):
        try:
            response = await coro(*args, **kwargs)
            return web.json_response(response)
        except BaseError as e:
            raise jsonerror(web.HTTPBadRequest(text=str(e)))
        except web.HTTPException as e:
            raise jsonerror(e)
        except Exception as e:
            log.error("Internal server error: %s", e, exc_info=True)
            raise jsonerror(web.HTTPInternalServerError())
    return wrapper


def jsonvalidate(scheme=None):
    def outer_wrapper(coro):
        @wraps(coro)
        async def inner_wrapper(request, *args, **kwargs):
            try:
                data = await request.json()
            except (ValueError, TypeError):
                raise web.HTTPBadRequest(text="Could not decode JSON object.")

            if scheme:
                try:
                    data = validate("request", data, DictScheme(scheme))
                except ValidationError as e:
                    raise web.HTTPBadRequest(text=e.get_message())
            return await coro(request, data, *args, **kwargs)
        return inner_wrapper
    return outer_wrapper


@routes.get("/api/cars/{serial}")
@jsonhandler
async def get_car(request):
    try:
        serial = int(request.match_info["serial"])
    except ValueError:
        raise web.HTTPBadRequest(text="Parameter 'serial' has invalid type.")

    car = await Car.one(serial)
    return car.asdict()


@routes.post("/api/cars")
@jsonhandler
@jsonvalidate(Car.get_scheme())
async def add_car(request, data):
    car = Car(data)
    await car.insert()
    return {"serial": car["serialNumber"]}


async def init(loop):
    app = web.Application(loop=loop)
    app.add_routes(routes)

    Motor().default(io_loop=loop)
    return app


def main():
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(init(loop))
    web.run_app(app, port=3000)

